import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {dirname, join, resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {after, test} from 'node:test';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../../..');
const platform = {'darwin': 'macos-arm64', 'linux': 'linux-x64', 'win32': 'windows-x64'}[process.platform];
const runtime = process.env.SYNCWATCH_DESIGN_RUNTIME ?? join(root, 'artifacts/dependencies/design-generator', platform, 'payload/runtime');
const temporary = mkdtempSync(join(tmpdir(), 'syncwatch-native-design-'));
after(() => rmSync(temporary, {recursive: true, force: true}));
const files = ['apple/SyncWatchTokens.swift', 'windows/SyncWatchTokens.g.cs', 'windows/SyncWatchTheme.g.xaml', 'design-manifest.json'];
function generate(design, output, check = false) {
    const result = spawnSync(process.execPath, [join(root, 'tools/design/generate.mjs'), '--runtime', runtime,
        '--design', design, '--output', output, ...(check ? ['--check'] : [])], {
        cwd: temporary, encoding: 'utf8', timeout: 30000,
        env: {...process.env, NODE_PATH: '', HTTP_PROXY: 'http://127.0.0.1:9', HTTPS_PROXY: 'http://127.0.0.1:9', npm_config_offline: 'true'},
    });
    assert.equal(result.error, undefined);
    return result;
}
const success = result => assert.equal(result.status, 0, result.stderr + result.stdout);
let sequence = 0;
function fixture(change = () => {}) {
    const directory = join(temporary, 'design-' + sequence++);
    cpSync(join(root, 'packages/design'), directory, {recursive: true, filter: source => !source.includes('/.build') && !source.includes('\\.build')});
    const geometry = JSON.parse(readFileSync(join(directory, 'tokens/geometry.json')));
    const palette = JSON.parse(readFileSync(join(directory, 'tokens/palette.json')));
    change(geometry, palette);
    writeFileSync(join(directory, 'tokens/geometry.json'), JSON.stringify(geometry));
    writeFileSync(join(directory, 'tokens/palette.json'), JSON.stringify(palette));
    return directory;
}
const name = id => id.split('.').map(part => part[0].toUpperCase() + part.slice(1)).join('');
function verifyAllOutputs(directory) {
    const manifest = JSON.parse(readFileSync(join(directory, files[3])));
    const swift = readFileSync(join(directory, files[0]), 'utf8');
    const cs = readFileSync(join(directory, files[1]), 'utf8');
    const xaml = readFileSync(join(directory, files[2]), 'utf8');
    for (const {id, type, value} of manifest.tokens) {
        const identifier = name(id);
        const swiftId = identifier[0].toLowerCase() + identifier.slice(1);
        if (type === 'color') {
            const [r, g, b, a] = value.slice(1).match(/../g).map(byte => parseInt(byte, 16));
            assert.ok(swift.includes(`let ${swiftId} = Color(\n        .sRGB, red: ${r}.0 / 255, green: ${g}.0 / 255, blue: ${b}.0 / 255, opacity: ${a}.0 / 255)`), id);
            assert.ok(cs.includes(`Color ${identifier} => Color.FromArgb(${a}, ${r}, ${g}, ${b});`), id);
            assert.ok(xaml.includes(`<Color x:Key="${id}">#${value.slice(7)}${value.slice(1, 7)}</Color>`), id);
            assert.ok(xaml.includes(`<SolidColorBrush x:Key="${id}.brush" Color="{StaticResource ${id}}" />`), id);
        } else {
            assert.ok(swift.includes(`let ${swiftId}: CGFloat = ${value}\n`), id);
            assert.ok(cs.includes(`const double ${identifier} = ${value};`), id);
            assert.ok(xaml.includes(`<sys:Double x:Key="${id}">${value}</sys:Double>`), id);
            assert.ok(xaml.includes(`<Thickness x:Key="${id}.thickness">${value}</Thickness>`), id);
            assert.ok(xaml.includes(`<CornerRadius x:Key="${id}.cornerRadius">${value}</CornerRadius>`), id);
        }
    }
    assert.equal(new Set(manifest.tokens.map(t => t.id)).size, manifest.tokens.length);
    assert.ok(!swift.includes('UIKit'));
    return manifest;
}

test('all shared token IDs and values agree in Swift, typed C#, XAML and manifest', () => {
    const output = join(temporary, 'actual');
    success(generate(join(root, 'packages/design'), output));
    const manifest = verifyAllOutputs(output);
    assert.equal(manifest.tokens.length, 40);
    assert.equal(manifest.schemaVersion, 1);
    assert.equal(manifest.generator.styleDictionary, '5.7.0');
    assert.equal(manifest.units, 'logical');
    assert.deepEqual(manifest.tokens.map(t => t.id), manifest.tokens.map(t => t.id).sort());
    const expected = {};
    function visit(group, prefix = []) {
        if (Object.hasOwn(group, 'value')) expected[prefix.join('.')] = group.value;
        else for (const [key, value] of Object.entries(group)) visit(value, [...prefix, key]);
    }
    for (const file of ['geometry', 'palette']) visit(JSON.parse(readFileSync(join(root, `packages/design/tokens/${file}.json`))));
    for (const token of manifest.tokens) assert.equal(token.value, token.type === 'color' ? expected[token.id].toUpperCase() + (expected[token.id].length === 7 ? 'FF' : '') : expected[token.id]);
});

test('generation is byte-identical across destinations, repetitions and check mode', () => {
    const first = join(temporary, 'first');
    const second = join(temporary, 'second');
    const design = join(root, 'packages/design');
    success(generate(design, first)); success(generate(design, second)); success(generate(design, first, true));
    for (const file of files) assert.deepEqual(readFileSync(join(first, file)), readFileSync(join(second, file)));
    const manifest = JSON.parse(readFileSync(join(first, files[3])));
    const hash = data => createHash('sha256').update(data).digest('hex');
    for (const [file, digest] of Object.entries(manifest.sources)) assert.equal(hash(readFileSync(join(design, file))), digest);
    assert.equal(hash(JSON.stringify(manifest.sources)), manifest.sourceDigest);
    assert.equal(hash(JSON.stringify({files: manifest.generator.files, sourceRevisions: manifest.generator.sourceRevisions})), manifest.generatorRevision);
    assert.ok(!JSON.stringify(manifest).includes(temporary));
});

test('sRGB trailing alpha, logical dimensions, rounding and transitive aliases survive all formats', () => {
    const design = fixture((g, p) => {
        p.color.shared.translucent = {type: 'color', value: '#12345678'};
        p.color.shared.alias = {type: 'color', value: '{color.shared.translucent}'};
        g.layout.fractional = {type: 'number', value: 1.2345678};
        g.layout.alias = {type: 'number', value: '{layout.fractional}'};
        g.layout.secondAlias = {type: 'number', value: '{layout.alias}'};
        g.layout.zero = {type: 'number', value: 0.0000001};
    });
    const output = join(temporary, 'edge'); success(generate(design, output));
    const tokens = verifyAllOutputs(output).tokens;
    assert.equal(tokens.find(t => t.id === 'color.shared.alias').value, '#12345678');
    assert.equal(tokens.find(t => t.id === 'layout.secondAlias').value, 1.234568);
    assert.equal(tokens.find(t => t.id === 'layout.zero').value, 0);
});

test('unknown types, malformed colors and physical-unit strings fail before output', () => {
    for (const token of [{type: 'font', value: 'Arial'}, {type: 'color', value: '#1234'},
        {type: 'color', value: 'red'}, {type: 'number', value: '18px'}, {type: 'number', value: -1},
        {type: 'number', value: 1000001}, {type: 'number', value: null}]) {
        const design = fixture(g => { g.layout.invalid = token; });
        assert.notEqual(generate(design, join(temporary, 'invalid')).status, 0, JSON.stringify(token));
    }
});

test('missing, cross-type and cyclic aliases fail through validation or upstream resolution', () => {
    for (const reference of ['{missing}', '{color.shared.accent}', '{layout.bad}']) {
        const design = fixture(g => { g.layout.bad = {type: 'number', value: reference}; });
        assert.notEqual(generate(design, join(temporary, 'bad-alias')).status, 0, reference);
    }
    const cycle = fixture(g => {
        g.layout.one = {type: 'number', value: '{layout.two}'};
        g.layout.two = {type: 'number', value: '{layout.one}'};
    });
    assert.notEqual(generate(cycle, join(temporary, 'cycle')).status, 0);
});

test('native name collisions and unsafe identifiers are rejected', () => {
    for (const change of [g => { g.a = {bc: {type: 'number', value: 1}}; g.aBc = {type: 'number', value: 2}; },
        g => { g.class = {type: 'number', value: 1}; },
        g => { g.layout['bad-name'] = {type: 'number', value: 1}; }]) {
        const design = fixture(change);
        assert.notEqual(generate(design, join(temporary, 'collision')).status, 0);
    }
});

test('theme references must exist, have color types and have matching roles', () => {
    for (const mutation of [t => { t.themes.dark.text = 'missing'; }, t => { t.themes.light.text = 'layout.panelGap'; },
        t => { delete t.themes.dark.text; }, t => { t.units = 'pixels'; }]) {
        const design = fixture(); const path = join(design, 'themes.json'); const themes = JSON.parse(readFileSync(path));
        mutation(themes); writeFileSync(path, JSON.stringify(themes));
        assert.notEqual(generate(design, join(temporary, 'bad-theme')).status, 0);
    }
});

test('check mode detects stale source, missing output and manual resource edits', () => {
    const design = fixture(); const output = join(temporary, 'check'); success(generate(design, output));
    const path = join(output, files[0]); const original = readFileSync(path);
    writeFileSync(path, '// stale\n'); assert.notEqual(generate(design, output, true).status, 0);
    writeFileSync(path, original); rmSync(join(output, files[1])); assert.notEqual(generate(design, output, true).status, 0);
    success(generate(design, output));
    const palette = join(design, 'tokens/palette.json'); writeFileSync(palette, readFileSync(palette, 'utf8').replace('#2F8CFF', '#123456'));
    assert.notEqual(generate(design, output, true).status, 0);
});
