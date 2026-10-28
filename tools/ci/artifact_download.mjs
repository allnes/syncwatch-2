import {createHash, randomUUID} from 'node:crypto';
import {link, mkdir, open, unlink} from 'node:fs/promises';
import {dirname} from 'node:path';

import {sdkMaximumBytes as maximumBytes} from './artifact_policy.mjs';

export function archiveMetadata(artifact) {
    if (!/^sha256:[0-9a-f]{64}$/.test(artifact.digest)
        || !Number.isSafeInteger(artifact.size_in_bytes)
        || artifact.size_in_bytes < 4 || artifact.size_in_bytes > maximumBytes) {
        throw new Error('Invalid artifact digest or size');
    }
}

// Both cache and current-run consumers use the same bounded storage transport.
// No repository token is accepted here, so it cannot be forwarded to storage.
export async function downloadArchive({redirect, artifact, destination}, request = fetch) {
    archiveMetadata(artifact);
    if (redirect.status !== 302) throw new Error('Artifact download redirect is missing');
    const location = new URL(redirect.headers.get('location'));
    if (location.protocol !== 'https:' || location.username || location.password) {
        throw new Error('Artifact storage requires HTTPS');
    }
    const response = await request(location, {redirect: 'error', signal: AbortSignal.timeout(180000)});
    if (!response.ok || !response.body
        || Number(response.headers.get('content-length')) > maximumBytes) {
        throw new Error('Artifact storage download failed');
    }
    await mkdir(dirname(destination), {recursive: true});
    const temporary = destination + '.partial-' + randomUUID();
    const file = await open(temporary, 'wx', 0o600);
    try {
        const digest = createHash('sha256');
        let size = 0;
        for await (const chunk of response.body) {
            size += chunk.length;
            if (size > artifact.size_in_bytes) throw new Error('Artifact download exceeds its declared size');
            digest.update(chunk);
            await file.writeFile(chunk);
        }
        if (size !== artifact.size_in_bytes || `sha256:${digest.digest('hex')}` !== artifact.digest) {
            throw new Error('Artifact archive checksum does not match');
        }
        await file.close();
        // An atomic exclusive link publishes only verified bytes, never replacing
        // an existing file or following an existing destination symlink.
        await link(temporary, destination);
    } finally {
        await file.close();
        await unlink(temporary);
    }
}

export async function restoreRunArtifact({repository, repositoryId, token, runId, attempt,
    sourceCommit, prefix, destination}, request = fetch) {
    if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repository)
        || !Number.isSafeInteger(repositoryId) || repositoryId < 1 || !token
        || !Number.isSafeInteger(runId) || runId < 1
        || !Number.isSafeInteger(attempt) || attempt < 1
        || !/^[0-9a-f]{40}$/.test(sourceCommit)
        || !/^syncwatch-[a-z0-9]+(?:-[a-z0-9]+)*$/.test(prefix) || prefix.length > 100) {
        throw new Error('Invalid current-run artifact request');
    }
    const base = `https://api.github.com/repos/${repository}`;
    async function api(path) {
        const result = await request(base + path, {
            redirect: 'manual', signal: AbortSignal.timeout(60000),
            headers: {Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json',
                'X-GitHub-Api-Version': '2026-03-10'},
        });
        if (!result.ok && result.status !== 302) throw new Error('Artifact API request failed');
        return result;
    }
    const run = await (await api(`/actions/runs/${runId}`)).json();
    if (run.id !== runId || run.repository?.id !== repositoryId || run.run_attempt !== attempt
        || run.path !== '.github/workflows/repository.yml') {
        throw new Error('Artifact workflow identity differs');
    }
    // Scope is this exact workflow run, including a PR run. This is NOT a
    // cross-run cache authorization; trusted main cache policy stays separate.
    // PR API head_sha can identify the branch while GITHUB_SHA identifies its
    // merge checkout. The producer name carries the exact checked-out commit.
    const stem = `${prefix}-${sourceCommit}-${runId}-`;
    const matches = [];
    let complete = false;
    for (let page = 1; page <= 5; page++) {
        const listing = await (await api(`/actions/runs/${runId}/artifacts?per_page=100&page=${page}`)).json();
        if (!Array.isArray(listing.artifacts) || listing.artifacts.length > 100) {
            throw new Error('Invalid current-run artifact inventory');
        }
        for (const artifact of listing.artifacts) {
            if (typeof artifact.name !== 'string' || !artifact.name.startsWith(stem) || artifact.expired) continue;
            const suffix = artifact.name.slice(stem.length);
            if (!/^[1-9][0-9]*$/.test(suffix)) continue;
            const producerAttempt = Number(suffix);
            if (!Number.isSafeInteger(producerAttempt) || producerAttempt > attempt) continue;
            if (!Number.isSafeInteger(artifact.id) || artifact.id < 1 || artifact.workflow_run?.id !== runId) {
                throw new Error('Artifact producer identity differs');
            }
            matches.push({artifact, producerAttempt});
        }
        if (listing.artifacts.length < 100) { complete = true; break; }
    }
    if (!complete) throw new Error('Current-run artifact inventory exceeds its bound');
    matches.sort((a, b) => b.producerAttempt - a.producerAttempt);
    if (!matches.length) throw new Error('Required current-run artifact is missing');
    const {artifact, producerAttempt} = matches[0];
    if (matches[1]?.producerAttempt === producerAttempt) throw new Error('Artifact producer is ambiguous');
    archiveMetadata(artifact);
    await downloadArchive({redirect: await api(`/actions/artifacts/${artifact.id}/zip`), artifact, destination}, request);
    return {artifactId: artifact.id, producerAttempt, sourceCommit};
}
