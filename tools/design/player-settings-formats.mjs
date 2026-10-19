// First-party typed field metadata. Numeric drafts use locale-independent decimal strings.
import {identifier} from './native-formats.mjs';
const q = value => JSON.stringify(value);
const kq = value => q(value).replace(/\$/g, '\\$');
const sn = value => String(value).replace(/\d{4,}/g, n => n.replace(/\B(?=(\d{3})+(?!\d))/g, '_'));
const same = (a,b) => q(a) === q(b);
export function validPlayerSetting(field, value) {
    if (typeof value !== 'string' || value.length > 64 || /[\x00-\x1f\x7f-\x9f]/.test(value)) return false;
    if (field.kind === 'boolean') return ['true','false'].includes(value);
    if (field.kind !== 'range') return field.options.some(o => o.id === value);
    if (!/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$/.test(value)) return false;
    const n = Number(value), ticks = (n - field.minimum) / field.step;
    return Number.isFinite(n) && n >= field.minimum && n <= field.maximum && Math.abs(ticks - Math.round(ticks)) < 1e-8;
}
export function validatePlayerSettings(s, components, copy, tokens) {
    const contract = components.components.PlayerSettingsDialog;
    if (s.schemaVersion !== 1 || !same(s.sections,contract.sections) || !same(s.states,contract.states)
        || !Array.isArray(s.fields) || !s.fields.length) throw Error('Player settings contract differs');
    const ids = new Set(), colors = new Map();
    for (const f of s.fields) {
        if (!/^[a-z][a-zA-Z0-9]*$/.test(f.id) || ids.has(f.id) || !s.sections.includes(f.section)
            || !['range','choice','boolean','color'].includes(f.kind) || !Object.hasOwn(copy.locales.en, f.label)
            || !Object.hasOwn(copy.locales.en, f.unit) || !Number.isInteger(f.row) || f.row < 0 || f.row > 32
            || !Array.isArray(f.options) || f.options.length > 16 || new Set(f.options.map(o=>o.id)).size !== f.options.length
            || (['choice','color'].includes(f.kind)) !== (f.options.length > 0)
            || ![f.minimum,f.maximum,f.step].every(Number.isFinite) || f.step <= 0 || f.minimum > f.maximum
            || [f.minimum,f.maximum,f.step].some(n => Math.abs(n) > 10000 || Math.abs(n*100-Math.round(n*100)) > 1e-8)
            || (f.kind === 'range' && (f.minimum === f.maximum || Math.abs((f.maximum-f.minimum)/f.step-Math.round((f.maximum-f.minimum)/f.step)) > 1e-8))) throw Error('Invalid player settings field');
        ids.add(f.id);
        for (const o of f.options) {
            if (!/^[a-z0-9]+$/.test(o.id) || !Object.hasOwn(copy.locales.en,o.label)
                || (f.kind === 'color' ? tokens.get(o.colorToken)?.type !== 'color' : o.colorToken !== null)) throw Error('Invalid player settings option');
            if (o.colorToken) {
                if (colors.has(o.id) && colors.get(o.id) !== o.colorToken) throw Error('Conflicting swatch identity');
                colors.set(o.id,o.colorToken);
            }
        }
        if (!validPlayerSetting(f,s.defaults[f.id])) throw Error('Invalid player settings default');
    }
    if (Object.keys(s.defaults).length !== ids.size || Object.keys(s.defaults).some(k=>!ids.has(k))) throw Error('Player settings defaults differ');
    for (const section of s.sections) {
        const fields = s.fields.filter(f=>f.section === section), rows = new Set(fields.map(f=>f.row));
        if (!fields.length || !Object.hasOwn(copy.locales.en,section) || !Object.hasOwn(copy.locales.en,section+'Hint')
            || [...rows].some(r=>fields.filter(f=>f.row===r).length > 2)) throw Error('Invalid player settings section');
    }
}
const swatches = s => [...new Map(s.fields.flatMap(f=>f.options).filter(o=>o.colorToken).map(o=>[o.id,o.colorToken])).entries()];
export function swiftPlayerSettings(s) {
    return '\npublic struct PlayerSettingOption: Sendable {\n    public let id: String\n    public let label: String\n    public let colorToken: String?\n}\n\npublic struct PlayerSettingField: Sendable {\n' +
        ['id: String','section: String','kind: String','label: String','row: Int','minimum: Double','maximum: Double','step: Double','unit: String','options: [PlayerSettingOption]'].map(v=>'    public let '+v+'\n').join('') +
        '}\n\npublic enum SyncWatchPlayerSettings {\n' +
        `    public static let sections = [${s.sections.map(q).join(', ')}]\n` +
        '    public static let states = [\n'+s.states.map(v=>'        '+q(v)+',\n').join('')+'    ]\n'+
        '    public static let defaults: [String: String] = [\n'+Object.entries(s.defaults).map(([k,v])=>`        ${q(k)}: ${q(v)},\n`).join('')+'    ]\n'+
        '    public static let fields: [PlayerSettingField] = [\n'+s.fields.map(f=>'        PlayerSettingField(\n'+
            `            id: ${q(f.id)}, section: ${q(f.section)}, kind: ${q(f.kind)},\n`+
            `            label: ${q(f.label)}, row: ${f.row}, minimum: ${sn(f.minimum)}, maximum: ${sn(f.maximum)}, step: ${sn(f.step)},\n`+
            (f.options.length ? `            unit: ${q(f.unit)},\n            options: [\n`+f.options.map(o=>`                PlayerSettingOption(id: ${q(o.id)}, label: ${q(o.label)}, colorToken: ${o.colorToken ? q(o.colorToken) : 'nil'}),\n`).join('')+'            ]),\n' : `            unit: ${q(f.unit)}, options: []),\n`)).join('')+'    ]\n'+
        '    public static func color(_ id: String) -> Color? {\n        switch id {\n'+swatches(s).map(([k,v])=>`        case ${q(k)}: SyncWatchTokens.${identifier(v)[0].toLowerCase()+identifier(v).slice(1)}\n`).join('')+'        default: nil\n        }\n    }\n}\n';
}
export function csharpPlayerSettings(s) {
    return '\npublic sealed record PlayerSettingOption(string Id, string Label, string? ColorToken);\npublic sealed record PlayerSettingField(string Id, string Section, string Kind, string Label, int Row, double Minimum, double Maximum, double Step, string Unit, PlayerSettingOption[] Options);\n\npublic static class SyncWatchPlayerSettings\n{\n'+
        `    public static string[] Sections => [${s.sections.map(q).join(', ')}];\n    public static string[] States => [${s.states.map(q).join(', ')}];\n`+
        '    public static System.Collections.Generic.IReadOnlyDictionary<string,string> Defaults => new System.Collections.Generic.Dictionary<string,string>\n    {\n'+Object.entries(s.defaults).map(([k,v])=>`        [${q(k)}] = ${q(v)},\n`).join('')+'    };\n'+
        '    public static PlayerSettingField[] Fields =>\n    [\n'+s.fields.map(f=>`        new(${q(f.id)}, ${q(f.section)}, ${q(f.kind)}, ${q(f.label)}, ${f.row}, ${f.minimum}, ${f.maximum}, ${f.step}, ${q(f.unit)}, [${f.options.map(o=>`new(${q(o.id)}, ${q(o.label)}, ${q(o.colorToken)})`).join(', ')}]),\n`).join('')+'    ];\n'+
        '    public static System.Windows.Media.Color? Color(string id) => id switch\n    {\n'+swatches(s).map(([k,v])=>`        ${q(k)} => SyncWatchTokens.${identifier(v)},\n`).join('')+'        _ => null,\n    };\n}\n';
}
export function kotlinPlayerSettings(s) {
    const n=v=>v+(Number.isInteger(v)?'.0':'');
    return '\ndata class PlayerSettingOption(val id: String, val label: String, val colorToken: String?)\ndata class PlayerSettingField(val id: String, val section: String, val kind: String, val label: String, val row: Int, val minimum: Double, val maximum: Double, val step: Double, val unit: String, val options: List<PlayerSettingOption>)\n\nobject SyncWatchPlayerSettings {\n'+
        `    val sections = listOf(${s.sections.map(kq).join(', ')})\n    val states = listOf(${s.states.map(kq).join(', ')})\n`+
        '    val defaults = mapOf(\n'+Object.entries(s.defaults).map(([k,v])=>`        ${kq(k)} to ${kq(v)},\n`).join('')+'    )\n'+
        '    val fields = listOf(\n'+s.fields.map(f=>`        PlayerSettingField(${kq(f.id)}, ${kq(f.section)}, ${kq(f.kind)}, ${kq(f.label)}, ${f.row}, ${n(f.minimum)}, ${n(f.maximum)}, ${n(f.step)}, ${kq(f.unit)}, listOf(${f.options.map(o=>`PlayerSettingOption(${kq(o.id)}, ${kq(o.label)}, ${o.colorToken ? kq(o.colorToken) : 'null'})`).join(', ')})),\n`).join('')+'    )\n'+
        '    fun color(id: String): Long? = when(id) {\n'+swatches(s).map(([k,v])=>`        ${kq(k)} -> SyncWatchTokens.${identifier(v)[0].toLowerCase()+identifier(v).slice(1)}\n`).join('')+'        else -> null\n    }\n}\n';
}
