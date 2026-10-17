import {registerHooks, isBuiltin} from 'node:module';
import {dirname, resolve, sep} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));
const packages = resolve(root, 'node_modules');
const permittedBuiltins = new Set([
    'assert', 'buffer', 'diagnostics_channel', 'events', 'fs', 'fs/promises',
    'os', 'path', 'path/posix', 'path/win32', 'process', 'stream', 'string_decoder', 'tty', 'url', 'util',
]);

// Fail closed instead of resolving a missing source from an ancestor/global node_modules.
// This is a build reproducibility guard, not an operating-system sandbox for untrusted code.
registerHooks({
    resolve(specifier, context, nextResolve) {
        if (isBuiltin(specifier)) {
            if (!permittedBuiltins.has(specifier.replace(/^node:/, ''))) throw new Error('Undeclared design builtin: ' + specifier);
            return nextResolve(specifier, context);
        }
        const result = nextResolve(specifier, context);
        if (!result.url.startsWith('file:')) throw new Error('Design imports must use local source files');
        const path = fileURLToPath(result.url);
        if (!path.startsWith(packages + sep)) throw new Error('Design import leaves its source package: ' + specifier);
        return result;
    },
});
globalThis.fetch = () => { throw new Error('Design generation is offline'); };
globalThis.WebSocket = class { constructor() { throw new Error('Design generation is offline'); } };

const {default: StyleDictionary} = await import('style-dictionary');
export const version = StyleDictionary.VERSION;

export async function createDictionary(config) {
    if (!config || typeof config !== 'object' || Array.isArray(config)) throw new Error('Supply an explicit dictionary configuration');
    for (const format of Object.keys(config.hooks?.formats ?? {})) {
        if (!format.startsWith('syncwatch/')) throw new Error('Custom formats require the syncwatch/ namespace');
    }
    for (const platform of Object.values(config.platforms ?? {})) {
        for (const file of platform.files ?? []) {
            if (!['json/flat', 'json/nested'].includes(file.format) && !Object.hasOwn(config.hooks?.formats ?? {}, file.format)) {
                throw new Error('Format is outside the native design profile: ' + file.format);
            }
        }
    }
    const dictionary = new StyleDictionary(config, {init: false});
    await dictionary.init();
    return dictionary;
}
