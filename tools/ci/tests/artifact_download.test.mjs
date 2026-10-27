import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdtemp, readFile, readdir, rm, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import test from 'node:test';
import {downloadArchive, restoreRunArtifact} from '../artifact_download.mjs';

const bytes = Buffer.from('owned SDK ZIP fixture');
const sourceCommit = 'a'.repeat(40);
const prefix = 'syncwatch-dependency-libvlc-linux-x64';
const artifact = {id: 19, name: `${prefix}-${sourceCommit}-12-1`, expired: false,
    workflow_run: {id: 12}, size_in_bytes: bytes.length,
    digest: `sha256:${createHash('sha256').update(bytes).digest('hex')}`};
const run = {id: 12, repository: {id: 123}, run_attempt: 2, path: '.github/workflows/repository.yml'};
const redirect = () => new Response(null, {status: 302,
    headers: {location: 'https://storage.example.invalid/sdk?private-signature'}});

async function fixture(t) {
    const directory = await mkdtemp(join(tmpdir(), 'sw-artifact-download-'));
    t.after(() => rm(directory, {recursive: true, force: true}));
    return {repository: 'salo-group/syncwatch', repositoryId: 123, token: 'private-read-token',
        runId: 12, attempt: 2, sourceCommit, prefix, destination: join(directory, 'sdk.zip')};
}

function service({inventory = [artifact], workflow = run, payload = bytes} = {}) {
    const calls = [];
    return {calls, request: async (url, options) => {
        calls.push({url: String(url), ...options});
        if (String(url).includes('/artifacts?')) return Response.json({artifacts: inventory});
        if (String(url).includes('/actions/runs/')) return Response.json(workflow);
        if (String(url).endsWith('/zip')) return redirect();
        return new Response(payload);
    }};
}

test('a rerun reuses this run exact-commit artifact without trusting it as a main cache', async t => {
    const config = await fixture(t);
    const server = service({workflow: {...run, event: 'pull_request', head_repository: {id: 999}}});
    assert.deepEqual(await restoreRunArtifact(config, server.request),
        {artifactId: 19, producerAttempt: 1, sourceCommit});
    assert.deepEqual(await readFile(config.destination), bytes);
    assert.equal(server.calls.length, 4);
    for (const call of server.calls.slice(0, 3)) assert.equal(call.headers.Authorization, 'Bearer private-read-token');
    assert.equal(server.calls[3].headers, undefined);
    assert.equal(server.calls[3].redirect, 'error');
    assert.deepEqual(await readdir(join(config.destination, '..')), ['sdk.zip']);
});

test('the newest producer attempt wins, while ambiguous producers fail', async t => {
    const config = await fixture(t);
    const newer = {...artifact, id: 20, name: `${prefix}-${sourceCommit}-12-2`};
    const server = service({inventory: [artifact, newer]});
    assert.equal((await restoreRunArtifact(config, server.request)).artifactId, 20);
    const ambiguous = service({inventory: [newer, {...newer, id: 21}]});
    await assert.rejects(restoreRunArtifact(config, ambiguous.request), /ambiguous/);
});

test('other runs, commits, prefixes, attempts, expired artifacts and workflow identities fail closed', async t => {
    const config = await fixture(t);
    for (const delta of [{expired: true}, {name: `${prefix}-${'b'.repeat(40)}-12-1`},
        {name: `syncwatch-other-${sourceCommit}-12-1`}, {name: `${prefix}-${sourceCommit}-13-1`},
        {name: `${prefix}-${sourceCommit}-12-3`}, {workflow_run: {id: 13}}, {id: 0}]) {
        await assert.rejects(restoreRunArtifact(config, service({inventory: [{...artifact, ...delta}]}).request));
    }
    for (const delta of [{id: 13}, {repository: {id: 999}}, {run_attempt: 1}, {path: '.github/workflows/other.yml'}]) {
        const server = service({workflow: {...run, ...delta}});
        await assert.rejects(restoreRunArtifact(config, server.request), /identity/);
        assert.equal(server.calls.length, 1);
    }
    assert.deepEqual(await readdir(join(config.destination, '..')), []);
});

test('pagination is bounded and does not silently omit a later matching producer', async t => {
    const config = await fixture(t);
    const irrelevant = Array.from({length: 100}, () => ({name: 'other'}));
    const server = service();
    const request = async (url, options) => new URL(url).searchParams.get('page') === '1'
        ? Response.json({artifacts: irrelevant}) : server.request(url, options);
    assert.equal((await restoreRunArtifact(config, request)).artifactId, 19);
    await assert.rejects(restoreRunArtifact(config, async url => String(url).includes('/artifacts?')
        ? Response.json({artifacts: irrelevant}) : Response.json(run)), /exceeds its bound/);
});

test('stream corruption, short or excess bodies and interrupted reads leave no partial files', async t => {
    const config = await fixture(t);
    const failure = new ReadableStream({start(controller) {
        controller.enqueue(new Uint8Array([1, 2])); controller.error(new Error('Interrupted storage stream'));
    }});
    for (const payload of [Buffer.from('bad'), Buffer.alloc(bytes.length + 1), Buffer.alloc(bytes.length), failure]) {
        await assert.rejects(downloadArchive({redirect: redirect(), artifact, destination: config.destination},
            async () => new Response(payload)));
        assert.deepEqual(await readdir(join(config.destination, '..')), []);
    }
});

test('exclusive publication preserves existing output and removes its own temporary file', async t => {
    const config = await fixture(t);
    await writeFile(config.destination, 'existing owner data');
    await assert.rejects(downloadArchive({redirect: redirect(), artifact, destination: config.destination},
        async () => new Response(bytes)));
    assert.equal(await readFile(config.destination, 'utf8'), 'existing owner data');
    assert.deepEqual(await readdir(join(config.destination, '..')), ['sdk.zip']);
});

test('invalid request, archive metadata, API failures and unsafe redirects cannot create output', async t => {
    const config = await fixture(t);
    for (const delta of [{runId: 0}, {attempt: 0}, {sourceCommit: 'latest'}, {repositoryId: -1},
        {repository: '../other'}, {token: ''}, {prefix: 'syncwatch-bad/../name'}]) {
        await assert.rejects(restoreRunArtifact({...config, ...delta}, () => {throw new Error('No request');}));
    }
    await assert.rejects(restoreRunArtifact(config, async () => new Response(null, {status: 403})));
    for (const value of [{...artifact, digest: undefined}, {...artifact, size_in_bytes: -1},
        {...artifact, size_in_bytes: 300 * 1024 * 1024}]) {
        await assert.rejects(downloadArchive({redirect: redirect(), artifact: value, destination: config.destination}));
    }
    for (const location of ['http://storage.example.invalid/sdk', 'https://user:secret@storage.example.invalid/sdk']) {
        await assert.rejects(downloadArchive({artifact, destination: config.destination,
            redirect: new Response(null, {status: 302, headers: {location}})}), /HTTPS/);
    }
    assert.deepEqual(await readdir(join(config.destination, '..')), []);
});
