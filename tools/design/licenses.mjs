import {createHash} from 'node:crypto';
import {mkdirSync, readFileSync, writeFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const tools = dirname(fileURLToPath(import.meta.url));
const root = resolve(tools, '../..');
const hash = data => createHash('sha256').update(data).digest('hex');
const json = path => JSON.parse(readFileSync(path, 'utf8'));
const same = (a, b) => JSON.stringify(a.slice().sort()) === JSON.stringify(b.slice().sort());
const terms = {
    'MIT': ['Permission is hereby granted', 'copyright notice', 'THE SOFTWARE IS PROVIDED'],
    'Apache-2.0': ['Apache License', 'Version 2.0', 'Redistribution', 'Grant of Patent License'],
    'BlueOak-1.0.0': ['Blue Oak Model License', 'Version 1.0.0', 'Notices', 'Patent'],
};

export function readLicensePolicy(profile, registry) {
    const policy = json(resolve(tools, 'licenses.json'));
    if (policy.schemaVersion !== 1 || !same(Object.keys(policy.packages), Object.keys(profile.packages))) {
        throw new Error('License inventory must cover every source package');
    }
    for (const [name, pkg] of Object.entries(profile.packages)) {
        const license = policy.packages[name];
        const source = registry.sources[pkg.source];
        if (!terms[license.license] || license.license !== source.license || !license.notices.length
            || !same(license.notices.map(notice => notice.path), source.notices)) {
            throw new Error('Source license requires an explicit review: ' + name);
        }
        for (const notice of license.notices) {
            if (!/^[a-zA-Z0-9_.-]+$/.test(notice.path) || !/^[0-9a-f]{64}$/.test(notice.sha256)) {
                throw new Error('Notice inventory requires safe paths and source digests');
            }
        }
    }
    for (const embedded of policy.embedded) {
        const pkg = policy.packages[embedded.withinPackage];
        if (!embedded.name || !embedded.paths.length || !pkg || pkg.license !== embedded.license
            || (!embedded.inlineHeader && !pkg.notices.some(notice => notice.path === embedded.notice))) {
            throw new Error('Embedded source needs an explicit license/notice association');
        }
    }
    for (const supplement of policy.supplemental) {
        if (!policy.packages[supplement.withinPackage] || supplement.license !== 'MIT'
            || !/^notices\/[A-Za-z0-9_.-]+$/.test(supplement.file)
            || hash(readFileSync(resolve(tools, supplement.file))) !== supplement.sha256) {
            throw new Error('Supplemental license requires an explicit review');
        }
    }
    return policy;
}

export function verifySourceNotices(name, source, declaredLicense, policy) {
    const license = policy.packages[name];
    if (declaredLicense !== license.license) throw new Error('Upstream manifest license changed: ' + name);
    const texts = license.notices.map(notice => {
        const data = readFileSync(resolve(source, notice.path));
        if (hash(data) !== notice.sha256) throw new Error('Unreviewed upstream notice: ' + name);
        return data.toString('utf8');
    }).join('\n').replace(/\s+/g, ' ').replaceAll('`', '');
    if (!terms[license.license].every(term => texts.includes(term))) {
        throw new Error('Incomplete license text: ' + name);
    }
}

export function writeLicenseBundle(destination, profile, registry, policy, inventory) {
    const records = {};
    const text = ['SyncWatch native design tools: third-party notices', '',
        'Original license and attribution texts follow. Package metadata is retained verbatim in each upstream-package.json.',
        'Modified files identify SyncWatch changes in their header or syncwatchModifications field.', ''];
    for (const [name, pkg] of Object.entries(profile.packages)) {
        const source = registry.sources[pkg.source];
        const license = policy.packages[name];
        const files = license.notices.map(notice => ({path: 'node_modules/' + name + '/' + notice.path, sha256: notice.sha256}));
        const modifiedFiles = Object.entries(inventory)
            .filter(([path, file]) => path.startsWith('node_modules/' + name + '/') && file.transform && file.transform !== 'copy')
            .map(([path]) => path);
        records[name] = {version: pkg.version, license: license.license, source: pkg.source, revision: source.revision, notices: files, modifiedFiles};
        text.push('='.repeat(72), name + ' ' + pkg.version, 'Source: ' + pkg.source + '@' + source.revision, 'License: ' + license.license, '');
        for (const notice of files) text.push(notice.path, readFileSync(resolve(destination, notice.path), 'utf8'), '');
    }
    text.push('Embedded sources retained inside their pinned parent module:', '');
    for (const embedded of policy.embedded) {
        text.push(embedded.name + ' inside ' + embedded.withinPackage + ': ' + embedded.paths.join(', '),
            'License: ' + embedded.license + '; notice: node_modules/' + embedded.withinPackage + '/' + embedded.notice,
            'Upstream reference: ' + embedded.upstream, '');
        if (embedded.inlineHeader) {
            const content = readFileSync(resolve(destination, 'node_modules', embedded.withinPackage, embedded.notice), 'utf8');
            const header = content.slice(0, content.indexOf('*/') + 2);
            if (!content.startsWith('/*') || hash(header) !== embedded.sha256) throw new Error('Embedded inline copyright notice changed');
            text.push(header, '');
        }
    }
    for (const supplement of policy.supplemental) {
        const path = 'node_modules/' + supplement.withinPackage + '/' + supplement.file;
        const data = readFileSync(resolve(tools, supplement.file));
        const directory = dirname(resolve(destination, path));
        // The directory is created here so the completed runtime remains standalone.
        mkdirSync(directory, {recursive: true});
        writeFileSync(resolve(destination, path), data);
        inventory[path] = {sha256: hash(data), firstParty: 'tools/design/' + supplement.file};
        text.push(supplement.name + ' inside ' + supplement.withinPackage, supplement.reason,
            'License: ' + supplement.license + '; upstream: ' + supplement.upstream, data.toString('utf8'), '');
    }
    const generated = {
        'THIRD-PARTY-NOTICES.txt': text.join('\n') + '\n',
        'license-inventory.json': JSON.stringify({schemaVersion: 1, packages: records, embedded: policy.embedded, supplemental: policy.supplemental}, null, 2) + '\n',
        'LICENSE': readFileSync(resolve(root, 'LICENSE')),
    };
    for (const [path, data] of Object.entries(generated)) {
        writeFileSync(resolve(destination, path), data);
        inventory[path] = {sha256: hash(data), firstParty: path === 'LICENSE' ? 'LICENSE' : 'tools/design/licenses.mjs'};
    }
}

export function verifyBuiltLicenses(destination) {
    const profile = json(resolve(tools, 'sources.json'));
    const registry = json(resolve(root, 'tools/dependencies/components.json')).components['design-generator'];
    const policy = readLicensePolicy(profile, registry);
    const bundled = json(resolve(destination, 'license-inventory.json'));
    const correspondence = json(resolve(destination, 'source-map.json')).files;
    const aggregate = readFileSync(resolve(destination, 'THIRD-PARTY-NOTICES.txt'), 'utf8');
    if (bundled.schemaVersion !== 1 || !same(Object.keys(bundled.packages), Object.keys(profile.packages))
        || JSON.stringify(bundled.embedded) !== JSON.stringify(policy.embedded)
        || JSON.stringify(bundled.supplemental) !== JSON.stringify(policy.supplemental)) throw new Error('Incomplete bundled license inventory');
    if (hash(readFileSync(resolve(destination, 'LICENSE'))) !== hash(readFileSync(resolve(root, 'LICENSE')))) {
        throw new Error('First-party Apache license missing from runtime');
    }
    for (const [name, pkg] of Object.entries(profile.packages)) {
        const record = bundled.packages[name];
        if (record.version !== pkg.version || record.revision !== registry.sources[pkg.source].revision
            || record.license !== policy.packages[name].license) throw new Error('Bundled license/source identity mismatch');
        const directory = resolve(destination, 'node_modules', name);
        const original = json(resolve(directory, 'upstream-package.json'));
        const distributed = json(resolve(directory, 'package.json'));
        if (original.name !== name || original.version !== pkg.version || original.license !== record.license) {
            throw new Error('Original upstream licensing metadata missing');
        }
        if (distributed.license !== record.license) throw new Error('Runtime license declaration differs from reviewed source');
        verifySourceNotices(name, directory, original.license, policy);
        if (!same(record.notices.map(notice => notice.path), policy.packages[name].notices.map(notice => 'node_modules/' + name + '/' + notice.path))) {
            throw new Error('Bundled notice list does not match license policy');
        }
        for (const notice of record.notices) {
            const content = readFileSync(resolve(destination, notice.path));
            if (hash(content) !== notice.sha256 || !aggregate.includes(content.toString('utf8'))) throw new Error('Bundled notice text missing or changed');
        }
        const modified = Object.entries(correspondence)
            .filter(([path, file]) => path.startsWith('node_modules/' + name + '/') && file.transform && file.transform !== 'copy')
            .map(([path]) => path);
        if (!same(modified, record.modifiedFiles)) throw new Error('Modification notice inventory is incomplete');
        for (const path of modified) {
            const content = readFileSync(resolve(destination, path), 'utf8');
            const marked = path.endsWith('.json') ? JSON.parse(content).syncwatchModifications?.startsWith('Modified by SyncWatch:')
                : content.startsWith('// Modified by SyncWatch:');
            if (!marked) throw new Error('Prominent modification notice missing: ' + path);
        }
    }
    for (const embedded of policy.embedded) {
        for (const path of embedded.paths) {
            if (!correspondence['node_modules/' + embedded.withinPackage + '/' + path]) throw new Error('Embedded source not present in correspondence inventory');
        }
        if (!aggregate.includes(embedded.name + ' inside ' + embedded.withinPackage)) throw new Error('Embedded attribution missing');
        if (embedded.inlineHeader) {
            const content = readFileSync(resolve(destination, 'node_modules', embedded.withinPackage, embedded.notice), 'utf8');
            const header = content.slice(0, content.indexOf('*/') + 2);
            if (hash(header) !== embedded.sha256 || !aggregate.includes(header)) throw new Error('Embedded inline copyright notice missing');
        }
    }
    for (const supplement of policy.supplemental) {
        const data = readFileSync(resolve(destination, 'node_modules', supplement.withinPackage, supplement.file));
        if (hash(data) !== supplement.sha256 || !aggregate.includes(data.toString('utf8'))) throw new Error('Supplemental attribution missing');
        for (const path of supplement.paths) {
            if (!correspondence['node_modules/' + supplement.withinPackage + '/' + path]) throw new Error('Supplemental attribution has no source');
        }
    }
    console.log(`Verified complete notices for ${Object.keys(profile.packages).length} packages and ${policy.embedded.length + policy.supplemental.length} embedded source entries`);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
    if (!process.argv[2]) throw new Error('Supply built runtime directory');
    verifyBuiltLicenses(resolve(process.argv[2]));
}
