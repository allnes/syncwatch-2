import Foundation
import SyncWatchDesign
import SyncWatchDomain
import SyncWatchLibrary

/// Ordered names cross native input ownership; inspector track IDs never do.
struct LocalTrackPreferences: Sendable {
    var audioNames: [String]?
    var subtitleNames: [String]?
    var audioIndex: Int?
    var subtitleIndex: Int?

    func resolve(_ tracks: [PlaybackTrack], subtitles: Bool) throws -> Int32? {
        guard let expected = subtitles ? subtitleNames : audioNames else { return nil }
        let actual = tracks.filter { $0.id >= 0 }
        guard actual.map(\.name) == expected else { throw MediaMetadataFailure.changed }
        guard let index = subtitles ? subtitleIndex : audioIndex else { return subtitles ? -1 : nil }
        guard actual.indices.contains(index) else { throw MediaMetadataFailure.changed }
        return actual[index].id
    }
}

/// Local draft for one metadata generation, independent of room revisions and live playback.
struct LibraryTrackSelection {
    private let sourceID = "library-tracks-" + UUID().uuidString
    private var revision: Int64 = 0
    private(set) var preferences = LocalTrackPreferences()
    private(set) var menu: SelectionMenuPresentation?

    mutating func reset(_ metadata: MediaMetadata? = nil) {
        dismiss()
        preferences = LocalTrackPreferences(audioNames: metadata?.audioTrackNames,
            subtitleNames: metadata?.subtitleTrackNames,
            audioIndex: metadata?.audioTrackNames?.isEmpty == false ? 0 : nil)
    }
    var audioName: String? { preferences.audioIndex.map { preferences.audioNames![$0] } }
    var subtitleName: String? { preferences.subtitleIndex.map { preferences.subtitleNames![$0] } }
    var subtitlesDisabled: Bool { preferences.subtitleNames != nil && preferences.subtitleIndex == nil }
    mutating func open(_ kind: String, language: String) {
        dismiss()
        guard kind == "audio" || kind == "subtitles",
            let names = kind == "audio" ? preferences.audioNames : preferences.subtitleNames,
            !names.isEmpty else { return }
        var value = SelectionMenuPresentation()
        value.kind = kind; value.sourceID = sourceID; value.revision = revision
        value.entries = names.enumerated().map { SelectionMenuEntry(id: String($0.offset),
            label: $0.element.isEmpty ? SyncWatchCopy.text("unknown", language: language) : $0.element) }
        if kind == "subtitles" { value.entries.insert(.offTrack, at: 0) }
        value.selectedID = (kind == "audio" ? preferences.audioIndex : preferences.subtitleIndex).map(String.init)
            ?? (kind == "subtitles" ? "-1" : nil)
        value.enabled = true
        menu = value
    }
    mutating func select(_ request: SelectionMenuRequest) {
        guard let menu, menu.allows(request.entryID), request.sourceID == sourceID,
            request.revision == revision, request.kind == menu.kind, request.scope == "local",
            request.action == menu.definition?.action, let index = Int(request.entryID) else { return }
        if request.kind == "audio" { preferences.audioIndex = index }
        else { preferences.subtitleIndex = index < 0 ? nil : index }
        dismiss()
    }
    mutating func dismiss() { revision += 1; menu = nil }
}
