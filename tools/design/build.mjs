import {createHash} from 'node:crypto';
import {cpSync, mkdirSync, readFileSync, readdirSync, writeFileSync} from 'node:fs';
import {stripTypeScriptTypes} from 'node:module';
import {dirname, matchesGlob, relative, resolve, sep} from 'node:path';
import {fileURLToPath} from 'node:url';

const tools = dirname(fileURLToPath(import.meta.url));
const root = resolve(tools, '../..');
const hash = data => createHash('sha256').update(data).digest('hex');
const json = path => JSON.parse(readFileSync(path, 'utf8'));
const within = (root, path) => path === root || path.startsWith(root + sep);

function walk(directory) {
    return readdirSync(directory, {withFileTypes: true}).sort((a, b) => a.name < b.name ? -1 : 1)
        .flatMap(entry => entry.isDirectory() ? walk(resolve(directory, entry.name))
            : entry.isFile() ? [resolve(directory, entry.name)] : []);
}

export function build(sources, destination) {
    sources = resolve(sources);
    destination = resolve(destination);
    const profile = json(resolve(tools, 'sources.json'));
    const registry = json(resolve(root, 'tools/dependencies/components.json')).components['design-generator'];
    if (profile.schemaVersion !== 1 || profile.profile !== 'native-node-v1') throw new Error('Unknown design profile');
    if (readdirSync(destination).length) throw new Error('Build destination must be empty');
    const inventory = {};
    const record = (output, data, source, transform) => {
        mkdirSync(dirname(output), {recursive: true});
        writeFileSync(output, data);
        inventory[relative(destination, output).split(sep).join('/')] = {
            sha256: hash(data), source: relative(sources, source).split(sep).join('/'),
            sourceSha256: hash(readFileSync(source)), transform,
        };
    };
    const declaredSources = new Set(Object.values(profile.packages).map(pkg => pkg.source));
    if (JSON.stringify([...declaredSources].sort()) !== JSON.stringify(Object.keys(registry.sources).sort())) {
        throw new Error('Profile and dependency source inventories differ');
    }
    for (const [name, pkg] of Object.entries(profile.packages)) {
        const source = resolve(sources, pkg.source, pkg.packageRoot);
        const manifestPath = resolve(source, pkg.manifest);
        const original = json(manifestPath);
        if (original.name !== name || original.version !== pkg.version) throw new Error('Source package version mismatch');
        const declared = registry.sources[pkg.source].requires;
        if (JSON.stringify(declared.slice().sort()) !== JSON.stringify(pkg.requires.map(name => profile.packages[name].source).sort())) {
            throw new Error('Profile and dependency edges differ');
        }
        const dependencies = Object.keys(original.dependencies ?? {});
        for (const name of dependencies) {
            if (!pkg.requires.includes(name) && !pkg.excludedDependencies[name]) throw new Error('Undeclared runtime dependency');
        }
        for (const name of pkg.requires) {
            if (!(name in (original.dependencies ?? {})) && !(name in (original.devDependencies ?? {}))) {
                throw new Error('Unexplained source dependency');
            }
        }
        for (const [name, reason] of Object.entries(pkg.excludedDependencies)) {
            if (!dependencies.includes(name) || !reason) throw new Error('Unexplained dependency exclusion');
        }
        const output = resolve(destination, 'node_modules', name);
        if (!within(resolve(destination, 'node_modules'), output)) throw new Error('Invalid package path');
        const metadata = {
            name, version: pkg.version, license: original.license,
            type: name === 'deepmerge' || name === 'is-mergeable-object' || name === 'json5' ? 'commonjs' : 'module',
            exports: pkg.exports,
            ...(original.imports ? {imports: original.imports} : {}),
        };
        record(resolve(output, 'package.json'), JSON.stringify(metadata, null, 2) + '\n', manifestPath, 'local-source-exports');
        let count = 0;
        for (const path of walk(source)) {
            const filename = relative(source, path).split(sep).join('/');
            if (!pkg.files.some(pattern => matchesGlob(filename, pattern))) continue;
            if (/\.(?:d|spec|test)\.ts$/.test(filename)) continue;
            let data = readFileSync(path, 'utf8');
            let transform = 'copy';
            let target = filename;
            if (filename.endsWith('.ts')) {
                // Glob predates verbatimModuleSyntax. Explicit type modifiers preserve tsc's
                // import elision when using Node's compiler, which has no cross-file type checker.
                if (name === 'glob') {
                    for (const type of ['GlobWalkerOpts', 'GlobOptions', 'IgnoreLike', 'MinimatchOptions', 'MMRegExp', 'MMPattern', 'FSOption']) {
                        data = data.replace(/import\s*\{[\s\S]*?\}\s*from\s*['"][^'"]+['"]/g,
                            statement => statement.replace(new RegExp('(?<![\\w$])' + type + '(?![\\w$])', 'g'), 'type ' + type));
                    }
                }
                // Node's own parser emits ES modules; upstream runtime imports already use .js paths.
                data = stripTypeScriptTypes(data, {mode: 'transform'});
                transform = 'node-strip-types-transform';
                target = filename.slice(0, -3) + '.js';
            }
            if (name === 'style-dictionary' && filename === 'lib/StyleDictionary.js') {
                if (data.split('<? version placeholder ?>').length !== 2) throw new Error('Unexpected upstream version injection');
                data = data.replace('<? version placeholder ?>', pkg.version);
                transform = 'inject-source-version';
            }
            if (name === 'style-dictionary' && filename === 'lib/fs.js') {
                const browserImport = "import { fs as memfs } from '@bundled-es-modules/memfs';";
                if (data.split(browserImport).length !== 2) throw new Error('Unexpected upstream filesystem binding');
                data = data.replace(browserImport, "import memfs from 'node:fs';");
                transform = 'bind-node-filesystem';
            }
            record(resolve(output, target), data, path, transform);
            count++;
        }
        if (!count) throw new Error('Source selection is empty');
    }
    for (const [source, target] of [
        ['sd-utils.mjs', 'node_modules/style-dictionary/syncwatch-utils.js'],
        ['runtime.mjs', 'runtime.mjs'],
    ]) {
        cpSync(resolve(tools, source), resolve(destination, target));
        inventory[target] = {sha256: hash(readFileSync(resolve(tools, source))), firstParty: 'tools/design/' + source};
    }
    writeFileSync(resolve(destination, 'source-map.json'), JSON.stringify({
        schemaVersion: 1, profile: profile.profile, packages: profile.packages, files: inventory,
    }, null, 2) + '\n');
    console.log(`Built Style Dictionary ${profile.packages['style-dictionary'].version} from ${declaredSources.size} source modules (${Object.keys(inventory).length} files)`);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
    const [sources, destination] = process.argv.slice(2);
    if (!sources || !destination) throw new Error('Supply source snapshot root and empty output directory');
    build(sources, destination);
}
