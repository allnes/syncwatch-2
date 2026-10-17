import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {cpSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {dirname, join, resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {after, test} from 'node:test';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../../..');
const runtime = process.env.SYNCWATCH_DESIGN_RUNTIME;
assert.ok(runtime, 'Build the source component before running its API tests');
const entry = pathToFileURL(resolve(runtime, 'runtime.mjs')).href;
const temporary = mkdtempSync(join(tmpdir(), 'syncwatch-design-'));
after(() => rmSync(temporary, {recursive: true, force: true}));

// Each check gets a clean process: no module cache, loader state, registry cache, or ancestor imports.
function run(body, success = true) {
    const script = `import assert from 'node:assert/strict';\nimport {createDictionary, version} from ${JSON.stringify(entry)};\n${body}`;
    const result = spawnSync(process.execPath, ['--input-type=module', '--eval', script], {
        cwd: temporary, encoding: 'utf8', timeout: 30000,
        env: {PATH: process.env.PATH, SYSTEMROOT: process.env.SYSTEMROOT, HOME: temporary,
            npm_config_offline: 'true', NODE_PATH: '', HTTP_PROXY: 'http://127.0.0.1:9', HTTPS_PROXY: 'http://127.0.0.1:9'},
    });
    assert.equal(result.error, undefined);
    if (success) assert.equal(result.status, 0, result.stderr + result.stdout);
    else assert.notEqual(result.status, 0, 'Controlled invalid input unexpectedly succeeded');
    return result;
}
const config = tokens => ({tokens, log: {verbosity: 'silent', warnings: 'error'}, platforms: {
    flat: {transforms: ['name/camel'], files: [{destination: 'tokens.json', format: 'json/flat'}]},
}});

test('source-built version and actual shared design tokens are deterministic', () => {
    const expected = {};
    const visit = (node, path = []) => {
        if (Object.hasOwn(node, 'value')) {
            const name = path.map((part, i) => i ? part[0].toUpperCase() + part.slice(1) : part).join('');
            expected[name] = node.value;
        } else for (const [name, child] of Object.entries(node)) visit(child, [...path, name]);
    };
    for (const name of readdirSync(join(root, 'packages/design/tokens'))) {
        visit(JSON.parse(readFileSync(join(root, 'packages/design/tokens', name), 'utf8')));
    }
    const source = join(root, 'packages/design/tokens/*.json').replaceAll('\\', '/');
    const settings = {source: [source], log: {verbosity: 'silent', warnings: 'error'}, platforms: {
        flat: {transforms: ['name/camel'], files: [{destination: 'tokens.json', format: 'json/flat'}]},
    }};
    const body = `assert.equal(version, '5.7.0');
const dictionary = await createDictionary(${JSON.stringify(settings)});
const result = await dictionary.formatAllPlatforms();
const output = result.flat[0].output;
const values = JSON.parse(output);
assert.deepEqual(values, ${JSON.stringify(expected)});
console.log(JSON.stringify(values));`;
    const first = run(body).stdout;
    assert.equal(run(body).stdout, first);
    writeFileSync(join(runtime, 'design-values.json'), first);
    console.log('Shared design values SHA-256: ' + createHash('sha256').update(first).digest('hex'));
});

test('references resolve across JSON5 files and nested globs', () => {
    writeFileSync(join(temporary, 'base.json5'), '{palette: {accent: {type: "color", value: "#123456"}}}');
    writeFileSync(join(temporary, 'alias.json'), JSON.stringify({button: {type: 'color', value: '{palette.accent}'}}));
    const settings = config(undefined);
    settings.source = [join(temporary, '*.{json,json5}').replaceAll('\\', '/')];
    const result = run(`const dictionary = await createDictionary(${JSON.stringify(settings)});
const values = JSON.parse((await dictionary.formatAllPlatforms()).flat[0].output);
assert.deepEqual(values, {button: '#123456', paletteAccent: '#123456'});`);
    assert.equal(result.status, 0);
});

test('upstream color transformations and custom native formatter execute', () => {
    run(`const dictionary = await createDictionary({
    tokens: {accent: {type: 'color', value: 'rgb(18, 52, 86)'}},
    log: {verbosity: 'silent', warnings: 'error'},
    hooks: {formats: {'syncwatch/probe': ({dictionary}) => dictionary.allTokens.map(t => t.value).join('\\n')}},
    platforms: {native: {transforms: ['color/hex'], files: [{destination: 'probe.txt', format: 'syncwatch/probe'}]}}
});
assert.equal((await dictionary.formatAllPlatforms()).native[0].output, '#123456');`);
});

test('DTCG color object transformation uses the actual Color.js source', () => {
    run(`const dictionary = await createDictionary({
    tokens: {accent: {$type: 'color', $value: {colorSpace: 'srgb', components: [1, 0, 0], alpha: 1}}},
    log: {verbosity: 'silent', warnings: 'error'},
    platforms: {flat: {transforms: ['color/hex'], files: [{destination: 'out.json', format: 'json/flat'}]}}
});
assert.deepEqual(JSON.parse((await dictionary.formatAllPlatforms()).flat[0].output), {accent: '#ff0000'});`);
});

test('missing and cyclic token references fail generation', () => {
    for (const tokens of [
        {alias: {value: '{missing}', type: 'color'}},
        {first: {value: '{second}', type: 'color'}, second: {value: '{first}', type: 'color'}},
    ]) {
        const result = run(`const dictionary = await createDictionary(${JSON.stringify(config(tokens))});
await dictionary.formatAllPlatforms();`, false);
        assert.match(result.stderr, /reference|Reference/);
    }
});

test('unprovisioned formats and browser conversion cannot enter the native profile', () => {
    for (const format of ['javascript/module', 'typescript/es6-declarations', 'unknown/format']) {
        const settings = config({spacing: {value: 8, type: 'dimension'}});
        settings.platforms.flat.files[0].format = format;
        assert.match(run(`await createDictionary(${JSON.stringify(settings)});`, false).stderr, /outside the native design profile/);
    }
    const utils = pathToFileURL(join(runtime, 'node_modules/style-dictionary/syncwatch-utils.js')).href;
    assert.match(run(`await import(${JSON.stringify(utils)}).then(m => { if (!m.convertZIPToDTCG) throw Error('ZIP conversion excluded'); });`, false).stderr, /ZIP conversion excluded/);
});

test('network and process imports and ambient packages are rejected', () => {
    for (const specifier of ['node:http', 'node:https', 'node:net', 'node:tls', 'node:dns', 'node:child_process', 'node:module', 'unprovisioned-package']) {
        const output = run(`await import(${JSON.stringify(specifier)});`, false);
        assert.match(output.stderr, /Undeclared design builtin|Cannot find package/);
    }
    assert.match(run("await fetch('https://example.invalid');", false).stderr, /offline/);
    assert.match(run("new WebSocket('wss://example.invalid');", false).stderr, /offline/);
    // A real, resolvable ancestor package must fail rather than using ambient node_modules.
    const outside = pathToFileURL(join(root, 'tools/ci/artifact_upload.mjs')).href;
    assert.match(run(`await import(${JSON.stringify(outside)});`, false).stderr, /leaves its source package/);
});

test('every packaged runtime file matches its source correspondence inventory', () => {
    const manifest = JSON.parse(readFileSync(join(runtime, 'source-map.json'), 'utf8'));
    assert.equal(manifest.profile, 'native-node-v1');
    assert.equal(Object.keys(manifest.packages).length, 15);
    for (const [file, metadata] of Object.entries(manifest.files)) {
        assert.equal(createHash('sha256').update(readFileSync(join(runtime, file))).digest('hex'), metadata.sha256, file);
    }
    const walk = directory => readdirSync(directory, {withFileTypes: true}).flatMap(entry => entry.isDirectory()
        ? walk(join(directory, entry.name)) : [join(directory, entry.name)]);
    const files = walk(join(runtime, 'node_modules'));
    assert.equal(files.length, Object.keys(manifest.files).filter(file => file.startsWith('node_modules/')).length);
    assert.ok(files.every(file => !file.endsWith('.ts') && !file.includes('node_modules/prettier')));
});

test('the selected graph excludes wrappers and uses the configured upstream merge predicate', () => {
    const manifest = JSON.parse(readFileSync(join(runtime, 'source-map.json'), 'utf8'));
    for (const name of ['@bundled-es-modules/deepmerge', '@bundled-es-modules/glob', 'path-unified', 'is-mergeable-object']) {
        assert.ok(!Object.hasOwn(manifest.packages, name));
    }
    const deepmerge = pathToFileURL(join(runtime, 'node_modules/deepmerge/index.js')).href;
    run(`const {default: merge} = await import(${JSON.stringify(deepmerge)});
assert.throws(() => merge({a: 1}, {b: 2}), /explicit isMergeableObject/);
assert.deepEqual(merge({a: [1], nested: {x: 1}}, {a: [2], nested: {y: 2}}, {
    isMergeableObject: value => value !== null && typeof value === 'object',
}), {a: [1, 2], nested: {x: 1, y: 2}});`);
});

test('missing licenses and removed modification notices fail the distribution check', () => {
    const checker = join(root, 'tools/design/licenses.mjs');
    const probe = join(temporary, 'license-probe');
    mkdirSync(probe);
    cpSync(runtime, probe, {recursive: true});
    const check = () => spawnSync(process.execPath, [checker, probe], {cwd: root, encoding: 'utf8', timeout: 10000});
    assert.equal(check().status, 0);
    const notice = join(probe, 'node_modules/chalk/license');
    const originalNotice = readFileSync(notice);
    rmSync(notice);
    assert.notEqual(check().status, 0, 'Missing upstream license was accepted');
    writeFileSync(notice, originalNotice);
    const source = join(probe, 'node_modules/style-dictionary/lib/fs.js');
    const originalSource = readFileSync(source, 'utf8');
    writeFileSync(source, originalSource.replace(/^\/\/ Modified by SyncWatch:[^\n]*\n/, ''));
    assert.match(check().stderr, /Prominent modification notice missing/);
    writeFileSync(source, originalSource);
    const metadata = join(probe, 'node_modules/style-dictionary/package.json');
    const packageJson = JSON.parse(readFileSync(metadata, 'utf8'));
    const modification = packageJson.syncwatchModifications;
    delete packageJson.syncwatchModifications;
    writeFileSync(metadata, JSON.stringify(packageJson));
    assert.match(check().stderr, /Prominent modification notice missing/);
    packageJson.syncwatchModifications = modification;
    packageJson.license = 'GPL-3.0-only';
    writeFileSync(metadata, JSON.stringify(packageJson));
    assert.match(check().stderr, /Runtime license declaration differs/);
});
