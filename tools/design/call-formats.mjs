// First-party call presentation metadata and normalized polygons; no provider API is adopted.
const q = value => JSON.stringify(value);
export function validateCall(s, components, copy) {
    const c = components.components.CallWindowShell;
    if (s.schemaVersion !== 1 || q(s.states) !== q(c.states) || q(s.previewStates) !== q(c.localPreviewStates)
        || q(Object.keys(s.actions)) !== q(c.actions) || s.maximumExtent !== 8192
        || q(s.galleryCases.map(g=>g.id)) !== q(c.galleryCases)) throw Error('Call contract differs');
    const kinds = ['delta','size','none','volume','boolean'];
    if (Object.values(s.actions).some(k=>!kinds.includes(k))) throw Error('Invalid call action kind');
    const expected = {move:'delta',resize:'size',minimize:'none',restore:'none',fullscreen:'none',pin:'none',close:'none',setCallVolume:'volume',setMicrophoneEnabled:'boolean',setCameraEnabled:'boolean',hangUp:'none'};
    if (q(s.actions)!==q(expected) || new Set(s.galleryCases.map(g=>g.id)).size!==s.galleryCases.length) throw Error('Call actions/cases differ');
    for (const g of s.galleryCases) if (!/^[a-z][a-zA-Z]*$/.test(g.id) || !s.states.includes(g.state) || !s.previewStates.includes(g.preview)) throw Error('Invalid call gallery');
    for (const state of s.states) if (!Object.hasOwn(copy.locales.en,'callState'+state[0].toUpperCase()+state.slice(1))) throw Error('Missing call state copy');
    for (const state of s.previewStates) if (!Object.hasOwn(copy.locales.en,state)) throw Error('Missing preview copy');
    for (const name of ['volume','muted','fullscreen','end','microphone','camera','pin','minimize','restore','close','resize','slash']) {
        const paths=s.icons?.[name];
        if (!Array.isArray(paths) || !paths.length || paths.length>8 || paths.some(p=>!Array.isArray(p)||p.length<6||p.length>64||p.length%2||p.some(n=>!Number.isFinite(n)||n<0||n>20))) throw Error('Invalid call icon');
    }
    if (Object.keys(s.icons).length!==12) throw Error('Unexpected call icons');
}
export function swiftCall(s) {
    return '\npublic struct CallGalleryCase: Sendable {\n    public let id: String\n    public let state: String\n    public let preview: String\n}\n\npublic enum SyncWatchCall {\n' +
        '    public static let states = [\n' + s.states.map(v => `        ${q(v)},\n`).join('') + '    ]\n' +
        '    public static let actions = [\n' + Object.keys(s.actions).map(v => `        ${q(v)},\n`).join('') + '    ]\n' +
        '    public static let maximumExtent = 8192.0\n' +
        '    public static let previewStates = [\n' + s.previewStates.map(v=>'        '+q(v)+',\n').join('') + '    ]\n' +
        '    public static let actionKinds = [\n' + Object.entries(s.actions).map(([a,k])=>'        '+q(a)+': '+q(k)+',\n').join('') + '    ]\n' +
        '    public static let galleryCases: [CallGalleryCase] = [\n' + s.galleryCases.map(c=>'        CallGalleryCase(id: '+q(c.id)+', state: '+q(c.state)+', preview: '+q(c.preview)+'),\n').join('')+'    ]\n' +
        '    public static let icons: [String: [[Double]]] = [\n' + Object.entries(s.icons).map(([k,v]) =>
            `        ${q(k)}: [\n` + v.map(p => '            [\n' + p.map(n => `                ${n},\n`).join('') + (v.length === 1 ? '            ]\n' : '            ],\n')).join('') + '        ],\n').join('') + '    ]\n}\n';
}
export function csharpCall(s) {
    return '\npublic sealed record CallGalleryCase(string Id, string State, string Preview);\n\npublic static class SyncWatchCall\n{\n' +
        `    public static string[] States => [${s.states.map(q).join(', ')}];\n` +
        `    public static string[] Actions => [${Object.keys(s.actions).map(q).join(', ')}];\n` +
        '    public const double MaximumExtent = 8192;\n' +
        `    public static string[] PreviewStates => [${s.previewStates.map(q).join(', ')}];\n` +
        '    public static System.Collections.Generic.IReadOnlyDictionary<string,string> ActionKinds => new System.Collections.Generic.Dictionary<string,string> { '+Object.entries(s.actions).map(([a,k])=>'['+q(a)+'] = '+q(k)).join(', ')+' };\n' +
        '    public static CallGalleryCase[] GalleryCases => ['+s.galleryCases.map(c=>'new('+q(c.id)+', '+q(c.state)+', '+q(c.preview)+')').join(', ')+'];\n' +
        '    public static System.Collections.Generic.IReadOnlyDictionary<string, double[][]> Icons => new System.Collections.Generic.Dictionary<string, double[][]>\n    {\n' +
        Object.entries(s.icons).map(([k,v]) => `        [${q(k)}] = ${q(v)},\n`).join('') + '    };\n}\n';
}
export function kotlinCall(s) {
    return '\ndata class CallGalleryCase(val id: String, val state: String, val preview: String)\n\nobject SyncWatchCall {\n' +
        `    val states = listOf(${s.states.map(q).join(', ')})\n` +
        `    val actions = setOf(${Object.keys(s.actions).map(q).join(', ')})\n` +
        '    const val maximumExtent: Double = 8192.0\n' +
        '    val previewStates = listOf('+s.previewStates.map(q).join(', ')+')\n' +
        '    val actionKinds = mapOf('+Object.entries(s.actions).map(([a,k])=>q(a)+' to '+q(k)).join(', ')+')\n' +
        '    val galleryCases = listOf('+s.galleryCases.map(c=>'CallGalleryCase('+q(c.id)+', '+q(c.state)+', '+q(c.preview)+')').join(', ')+')\n' +
        '    val icons = mapOf(\n' + Object.entries(s.icons).map(([k,v]) => `        ${q(k)} to listOf(${v.map(p => 'listOf(' + p.map(n => n + (Number.isInteger(n) ? '.0f' : 'f')).join(', ') + ')').join(', ')}),\n`).join('') + '    )\n}\n';
}
