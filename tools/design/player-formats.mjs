// First-party polygon geometry and presentation contract; no platform icon/font dependency.
const q = value => JSON.stringify(value);
export function validatePlayer(s, components, copy) {
    const c = components.components.PlayerChrome;
    if (s.schemaVersion !== 1 || q(s.states) !== q(c.states) || q(s.actions) !== q(c.renderedActions)
        || new Set(s.actions).size !== s.actions.length || s.actions.some(a => !c.actions.includes(a))
        || s.maximumPositionMs !== 604800000 || !s.icons || !Object.keys(s.icons).length) throw Error('Player contract differs');
    for (const state of s.states) if (!Object.hasOwn(copy.locales.en, state)) throw Error('Missing player state copy');
    for (const [name, paths] of Object.entries(s.icons)) {
        if (!/^[a-z]+$/.test(name) || !Array.isArray(paths) || !paths.length || paths.length > 8
            || paths.some(p => !Array.isArray(p) || p.length < 6 || p.length > 64 || p.length % 2
                || p.some(v => !Number.isFinite(v) || v < 0 || v > 20))) throw Error('Invalid player polygon');
    }
    for (const icon of ['play','pause','backward','forward','previous','next','volume','muted','library','call','fullscreen','end','settings','playlist','subtitles','audio']) {
        if (!s.icons[icon]) throw Error('Missing player icon');
    }
}
export function swiftPlayer(s) {
    return '\npublic enum SyncWatchPlayer {\n' +
        '    public static let states = [\n' + s.states.map(v => `        ${q(v)},\n`).join('') + '    ]\n' +
        '    public static let actions = [\n' + s.actions.map(v => `        ${q(v)},\n`).join('') + '    ]\n' +
        '    public static let maximumPositionMs: Int64 = 604_800_000\n' +
        '    public static let icons: [String: [[Double]]] = [\n' + Object.entries(s.icons).map(([k,v]) =>
            `        ${q(k)}: [\n` + v.map(p => '            [\n' + p.map(n => `                ${n},\n`).join('') + (v.length === 1 ? '            ]\n' : '            ],\n')).join('') + '        ],\n').join('') + '    ]\n}\n';
}
export function csharpPlayer(s) {
    return '\npublic static class SyncWatchPlayer\n{\n' +
        `    public static string[] States => [${s.states.map(q).join(', ')}];\n` +
        `    public static string[] Actions => [${s.actions.map(q).join(', ')}];\n` +
        `    public const long MaximumPositionMs = ${s.maximumPositionMs};\n` +
        '    public static System.Collections.Generic.IReadOnlyDictionary<string, double[][]> Icons => new System.Collections.Generic.Dictionary<string, double[][]>\n    {\n' +
        Object.entries(s.icons).map(([k,v]) => `        [${q(k)}] = ${q(v)},\n`).join('') + '    };\n}\n';
}
export function kotlinPlayer(s) {
    return '\nobject SyncWatchPlayer {\n' +
        `    val states = listOf(${s.states.map(q).join(', ')})\n` +
        `    val actions = setOf(${s.actions.map(q).join(', ')})\n` +
        `    const val maximumPositionMs: Long = ${s.maximumPositionMs}L\n` +
        '    val icons = mapOf(\n' + Object.entries(s.icons).map(([k,v]) => `        ${q(k)} to listOf(${v.map(p => 'listOf(' + p.map(n => n + (Number.isInteger(n) ? '.0f' : 'f')).join(', ') + ')').join(', ')}),\n`).join('') + '    )\n}\n';
}
