import {readFileSync} from 'node:fs';

const policy = JSON.parse(readFileSync(new URL('./artifact-policy.json', import.meta.url), 'utf8'));
if (policy.schemaVersion !== 1 || policy.sdkMaximumBytes !== 256 * 1024 * 1024
    || policy.nativeApplicationMaximumBytes !== 512 * 1024 * 1024) {
    throw new Error('Unsupported artifact transport policy');
}
export const {sdkMaximumBytes, nativeApplicationMaximumBytes} = policy;
