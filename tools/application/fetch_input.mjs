import {resolve} from 'node:path';
import {restoreRunArtifact} from '../ci/artifact_download.mjs';

// The Python consumer verifies the producer receipt and every payload byte.
// Keep the repository token in this transport process, outside build commands.
const [prefix, destination] = process.argv.slice(2);
try {
    const result = await restoreRunArtifact({
        repository: process.env.GITHUB_REPOSITORY,
        repositoryId: Number(process.env.GITHUB_REPOSITORY_ID),
        token: process.env.GITHUB_TOKEN,
        runId: Number(process.env.GITHUB_RUN_ID),
        attempt: Number(process.env.GITHUB_RUN_ATTEMPT),
        sourceCommit: process.env.GITHUB_SHA,
        prefix, destination: resolve(destination),
    });
    console.log(JSON.stringify(result));
} catch {
    console.error('Native application input download failed');
    process.exitCode = 1;
}
