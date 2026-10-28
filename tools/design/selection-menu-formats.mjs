// Apache-2.0. Selection metadata and validation; native geometry lives in layouts.json.
const q = JSON.stringify;
export function validateSelectionMenu(s, components, copy) {
    const c = components.components.SelectionMenu;
    const expected = [
        {id:'playlist',label:'playlist',action:'selectMovie',scope:'shared'},
        {id:'audio',label:'audioTracks',action:'selectAudioTrack',scope:'local'},
        {id:'subtitles',label:'subtitles',action:'selectSubtitleTrack',scope:'local'},
    ];
    if (s.schemaVersion !== 1 || q(s.kinds) !== q(expected) || q(c.kinds) !== q(s.kinds.map(k=>k.id))
        || q(s.states) !== q(c.states) || q(s.states) !== q(['empty','available','readOnly','longList'])) throw Error('Selection menu contract differs');
    for (const [key,max] of Object.entries({maximumEntries:10000,maximumIDBytes:1024,maximumLabelBytes:16384,maximumRevision:Number.MAX_SAFE_INTEGER,galleryEntryCount:100})) {
        if (!Number.isSafeInteger(s[key]) || s[key]<1 || s[key]>max) throw Error('Invalid selection menu limit');
    }
    if (s.galleryEntryCount > s.maximumEntries || s.maximumLabelBytes < s.maximumIDBytes) throw Error('Inconsistent selection menu limits');
    const f = s.externalFile;
    if (!f || !/^[A-Za-z0-9._:-]+$/.test(f.entryID) || !/^[A-Za-z0-9._:-]+$/.test(f.errorEntryID)
        || f.entryID === f.errorEntryID || !Array.isArray(f.filters)
        || q(f.filters.map(x=>x.kind)) !== q(['audio','subtitles'])
        || f.filters.some(x=>!Array.isArray(x.extensions) || !x.extensions.length
            || new Set(x.extensions).size!==x.extensions.length || x.extensions.some(e=>!(/^[a-z0-9]+$/).test(e)))) throw Error('Invalid external file menu policy');
    if (!f.libraryLabels || !['fileName','relativePath'].includes(f.libraryLabels.normal) || !['fileName','relativePath'].includes(f.libraryLabels.duplicate)) throw Error('Invalid library companion labels');
    for (const key of [...s.kinds.map(k=>k.label),'selectionEmpty','selectionUnavailable','selectionFixtureLabel',f.errorLabel,...f.filters.map(x=>x.label)]) {
        if (!Object.hasOwn(copy.locales.en,key)) throw Error('Missing selection menu copy');
    }
}
export function validSelection(s, p) {
    const id = value => typeof value === 'string' && value.length>0 && value.length<=s.maximumIDBytes && !/[^A-Za-z0-9._:-]/.test(value);
    return s.kinds.some(k=>k.id===p.kind) && id(p.sourceID) && Number.isSafeInteger(p.revision) && p.revision>=0 && p.revision<=s.maximumRevision
        && Array.isArray(p.entries) && p.entries.length<=s.maximumEntries && new Set(p.entries.map(e=>e.id)).size===p.entries.length
        && p.entries.every(e=>id(e.id) && typeof e.label==='string' && e.label.length>0 && Buffer.byteLength(e.label,'utf8')<=s.maximumLabelBytes && !/[\u0000-\u001f\u007f]/.test(e.label))
        && (p.selectedID===null || p.entries.some(e=>e.id===p.selectedID));
}
export function selectionRequest(s, p, entryID, token) {
    if (!validSelection(s,p) || !p.enabled || token!==`${p.kind}|${p.sourceID}|${p.revision}` || entryID===p.selectedID || !p.entries.some(e=>e.id===entryID && e.enabled)) return null;
    const kind=s.kinds.find(k=>k.id===p.kind);
    return {kind:p.kind,sourceID:p.sourceID,revision:p.revision,entryID,action:kind.action,scope:kind.scope};
}
const limits = s => Object.entries(s).filter(([k])=>k.startsWith('maximum') || k==='galleryEntryCount');
const cap = s => s[0].toUpperCase()+s.slice(1);
export function swiftSelectionMenu(s) {
    return '\npublic struct SelectionMenuKind: Sendable {\n    public let id: String\n    public let label: String\n    public let action: String\n    public let scope: String\n}\npublic struct ExternalTrackFileFilter: Sendable {\n    public let kind: String\n    public let label: String\n    public let extensions: [String]\n}\npublic enum SyncWatchSelectionMenu {\n'
        + `    public static let externalFileID = ${q(s.externalFile.entryID)}\n    public static let externalFileErrorID = ${q(s.externalFile.errorEntryID)}\n    public static let externalFileErrorLabel = ${q(s.externalFile.errorLabel)}\n`
        + '    public static let externalFileFilters: [ExternalTrackFileFilter] = [\n'+s.externalFile.filters.map(x=>`        ExternalTrackFileFilter(\n            kind: ${q(x.kind)}, label: ${q(x.label)},\n            extensions: [${x.extensions.map(q).join(', ')}]),\n`).join('')+'    ]\n'
        + `    public static let companionFileLabel = ${q(s.externalFile.libraryLabels.normal)}\n    public static let duplicateCompanionFileLabel = ${q(s.externalFile.libraryLabels.duplicate)}\n`
        + limits(s).map(([k,v])=>`    public static let ${k} = ${v >= 10000 ? String(v).replace(/\B(?=(\d{3})+(?!\d))/g, '_') : v}\n`).join('')
        + `    public static let states = [${s.states.map(q).join(', ')}]\n`
        + '    public static let kinds: [SelectionMenuKind] = [\n'+s.kinds.map(k=>`        SelectionMenuKind(\n            id: ${q(k.id)}, label: ${q(k.label)}, action: ${q(k.action)}, scope: ${q(k.scope)}),\n`).join('')+'    ]\n}\n';
}
export function csharpSelectionMenu(s) {
    return '\npublic sealed record SelectionMenuKind(string Id, string Label, string Action, string Scope);\npublic sealed record ExternalTrackFileFilter(string Kind, string Label, string[] Extensions);\npublic static class SyncWatchSelectionMenu\n{\n'
        + `    public const string ExternalFileID = ${q(s.externalFile.entryID)};\n    public const string ExternalFileErrorID = ${q(s.externalFile.errorEntryID)};\n    public const string ExternalFileErrorLabel = ${q(s.externalFile.errorLabel)};\n`
        + `    public static ExternalTrackFileFilter[] ExternalFileFilters => [${s.externalFile.filters.map(x=>`new(${q(x.kind)}, ${q(x.label)}, [${x.extensions.map(q).join(', ')}])`).join(', ')}];\n`
        + `    public const string CompanionFileLabel = ${q(s.externalFile.libraryLabels.normal)};\n    public const string DuplicateCompanionFileLabel = ${q(s.externalFile.libraryLabels.duplicate)};\n`
        + limits(s).map(([k,v])=>`    public const ${k==='maximumRevision'?'long':'int'} ${cap(k)} = ${v};\n`).join('')
        + `    public static string[] States => [${s.states.map(q).join(', ')}];\n`
        + `    public static SelectionMenuKind[] Kinds => [${s.kinds.map(k=>'new('+[k.id,k.label,k.action,k.scope].map(q).join(', ')+')').join(', ')}];\n}\n`;
}
export function kotlinSelectionMenu(s) {
    return '\ndata class SelectionMenuKind(val id: String, val label: String, val action: String, val scope: String)\ndata class ExternalTrackFileFilter(val kind: String, val label: String, val extensions: List<String>)\nobject SyncWatchSelectionMenu {\n'
        + `    const val externalFileID = ${q(s.externalFile.entryID)}\n    const val externalFileErrorID = ${q(s.externalFile.errorEntryID)}\n    const val externalFileErrorLabel = ${q(s.externalFile.errorLabel)}\n`
        + `    val externalFileFilters = listOf(${s.externalFile.filters.map(x=>`ExternalTrackFileFilter(${q(x.kind)}, ${q(x.label)}, listOf(${x.extensions.map(q).join(', ')}))`).join(', ')})\n`
        + `    const val companionFileLabel = ${q(s.externalFile.libraryLabels.normal)}\n    const val duplicateCompanionFileLabel = ${q(s.externalFile.libraryLabels.duplicate)}\n`
        + limits(s).map(([k,v])=>`    const val ${k}${k==='maximumRevision'?': Long':''} = ${v}${k==='maximumRevision'?'L':''}\n`).join('')
        + `    val states = listOf(${s.states.map(q).join(', ')})\n`
        + `    val kinds = listOf(${s.kinds.map(k=>'SelectionMenuKind('+[k.id,k.label,k.action,k.scope].map(q).join(', ')+')').join(', ')})\n}\n`;
}
