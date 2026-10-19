// Run in a dedicated process: the source-built runtime installs its offline import guard.
import {createHash} from 'node:crypto';
import {mkdirSync, readFileSync, readdirSync, writeFileSync} from 'node:fs';
import {dirname, join, resolve} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {compileLayouts, csharpLayouts, kotlinLayouts, swiftLayouts, validateLayouts} from './layout-formats.mjs';
import {csharp, normalized, swift, validateThemes, validateTokens, xaml} from './native-formats.mjs';
import {csharpSettings, kotlinSettings, swiftSettings, validateSettings} from './settings-formats.mjs';
import {csharpPlayerSettings, kotlinPlayerSettings, swiftPlayerSettings, validatePlayerSettings} from './player-settings-formats.mjs';
import {csharpPlayer, kotlinPlayer, swiftPlayer, validatePlayer} from './player-formats.mjs';
import {csharpCopy, kotlin, swiftCopy, validateCopy} from './presentation-formats.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const options = process.argv.slice(2);
function option(name, fallback) {
    const index = options.indexOf(name);
    if (index < 0) return fallback;
    if (!options[index + 1] || options[index + 1].startsWith('--')) throw Error('Missing ' + name);
    return resolve(options[index + 1]);
}
for (let i = 0; i < options.length; i++) {
    if (['--runtime', '--design', '--output'].includes(options[i])) i++;
    else if (options[i] !== '--check') throw Error('Unknown option: ' + options[i]);
}
const runtime = option('--runtime', process.env.SYNCWATCH_DESIGN_RUNTIME);
if (!runtime) throw Error('Supply --runtime with the verified source-built design runtime');
const design = option('--design', join(root, 'packages/design'));
const output = option('--output', join(root, 'packages/design/generated'));
const hash = data => createHash('sha256').update(data).digest('hex');
const sources = {};
function readSource(name) {
    const contents = readFileSync(join(design, name));
    sources[name] = hash(contents);
    return JSON.parse(contents);
}
const tokens = {};
for (const name of readdirSync(join(design, 'tokens')).sort()) {
    if (!name.endsWith('.json')) throw Error('Token sources must be flat JSON files');
    const file = readSource('tokens/' + name);
    for (const [key, value] of Object.entries(file)) {
        if (Object.hasOwn(tokens, key)) throw Error('Duplicate root token group: ' + key);
        tokens[key] = value;
    }
}
const ids = validateTokens(tokens);
const themes = readSource('themes.json');
validateThemes(themes, ids);
const components = readSource('components.json');
const copy = readSource('copy.json');
validateCopy(copy, components);
const settings = readSource('settings.json');
validateSettings(settings, components, copy);
const player = readSource('player.json');
validatePlayer(player, components, copy);
const playerSettings = readSource('player-settings.json');
validatePlayerSettings(playerSettings, components, copy, ids);
const layouts = readSource('layouts.json');
validateLayouts(layouts, ids, copy, {tokens, themes});
if (components.contractVersion !== 1) throw Error('Unsupported component contract');
for (const component of Object.values(components.components ?? {})) for (const id of component.tokens ?? []) {
    if (!ids.has(id)) throw Error('Unknown component token: ' + id);
}
if (readSource('package.json').license !== 'Apache-2.0') throw Error('Design package license changed');
const generatorFiles = [
    'tools/design/generate.mjs', 'tools/design/native-formats.mjs', 'tools/design/build.mjs',
    'tools/design/runtime.mjs', 'tools/design/sd-utils.mjs', 'tools/design/sources.json', 'tools/design/presentation-formats.mjs', 'tools/design/settings-formats.mjs', 'tools/design/player-formats.mjs', 'tools/design/player-settings-formats.mjs', 'tools/design/layout-formats.mjs',
];
const files = Object.fromEntries(generatorFiles.map(path => [path, hash(readFileSync(join(root, path)))]));
const registry = JSON.parse(readFileSync(join(root, 'tools/dependencies/components.json'))).components['design-generator'];
const sourceRevisions = Object.fromEntries(Object.entries(registry.sources).map(([path, spec]) => [path, spec.revision]));
const generatorRevision = hash(JSON.stringify({files, sourceRevisions}));
// Load all first-party code and Node builtins above before the guard is installed.
const {createDictionary, version} = await import(pathToFileURL(join(resolve(runtime), 'runtime.mjs')).href);
const formats = {
    'syncwatch/swift': ({dictionary}) => swift(normalized(dictionary), themes) + swiftCopy(copy) + swiftSettings(settings) + swiftPlayer(player) + swiftPlayerSettings(playerSettings) + swiftLayouts(compileLayouts(layouts, Object.fromEntries(normalized(dictionary).map(t => [t.id, t.value])), player, themes), hash(JSON.stringify(layouts))),
    'syncwatch/csharp': ({dictionary}) => csharp(normalized(dictionary)) + csharpCopy(copy) + csharpSettings(settings) + csharpPlayer(player) + csharpPlayerSettings(playerSettings) + csharpLayouts(compileLayouts(layouts, Object.fromEntries(normalized(dictionary).map(t => [t.id, t.value])), player, themes), hash(JSON.stringify(layouts))),
    'syncwatch/xaml': ({dictionary}) => xaml(normalized(dictionary), themes),
    'syncwatch/manifest': ({dictionary}) => JSON.stringify({
        schemaVersion: 1, units: 'logical', sourceDigest: hash(JSON.stringify(sources)), sources,
        generatorRevision, generator: {styleDictionary: version, files, sourceRevisions},
        themes: themes.themes, copy, settings, player, playerSettings, layouts, tokens: normalized(dictionary),
    }, null, 2) + '\n',
    'syncwatch/kotlin': ({dictionary}) => kotlin(normalized(dictionary), themes, copy) + kotlinSettings(settings) + kotlinPlayer(player) + kotlinPlayerSettings(playerSettings) + kotlinLayouts(compileLayouts(layouts, Object.fromEntries(normalized(dictionary).map(t => [t.id, t.value])), player, themes), hash(JSON.stringify(layouts))),
};
const destinations = ['apple/SyncWatchTokens.swift', 'windows/SyncWatchTokens.g.cs', 'windows/SyncWatchTheme.g.xaml', 'design-manifest.json', 'linux/SyncWatchTokens.kt'];
const dictionary = await createDictionary({tokens, usesDtcg: false, log: {verbosity: 'silent', warnings: 'error'}, hooks: {formats}, platforms: {
    native: {transforms: ['name/camel'], files: Object.keys(formats).map((format, i) => ({format, destination: destinations[i]}))},
}});
const results = (await dictionary.formatAllPlatforms()).native;
for (const {destination, output: contents} of results) {
    const path = join(output, destination);
    if (options.includes('--check')) {
        if (readFileSync(path, 'utf8') !== contents) throw Error('Stale generated resource: ' + destination);
    } else {
        mkdirSync(dirname(path), {recursive: true});
        writeFileSync(path, contents, 'utf8');
    }
}
console.log(`${options.includes('--check') ? 'Verified' : 'Generated'} ${results.length} native resources from ${ids.size} tokens`);
