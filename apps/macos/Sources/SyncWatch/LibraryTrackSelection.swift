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
    var audioFile: LocalCompanionFile?
    var subtitleFile: LocalCompanionFile?

    func resolve(_ tracks: [PlaybackTrack], subtitles: Bool) throws -> Int32? {
        guard let expected = subtitles ? subtitleNames : audioNames else { return nil }
        let actual = tracks.filter { $0.id >= 0 }
        guard actual.map(\.name) == expected else { throw MediaMetadataFailure.changed }
        if (subtitles ? subtitleFile : audioFile) != nil { return nil }
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
    private var companions: [LocalCompanionFile] = []

    mutating func reset(_ metadata: MediaMetadata? = nil, companions: [LocalCompanionFile] = []) {
        dismiss()
        self.companions = companions
        preferences = LocalTrackPreferences(
            audioNames: metadata?.audioTrackNames,
            subtitleNames: metadata?.subtitleTrackNames,
            audioIndex: metadata?.audioTrackNames?.isEmpty == false ? 0 : nil)
    }
    var audioName: String? {
        preferences.audioFile?.file.lastPathComponent ?? preferences.audioIndex.map { preferences.audioNames![$0] }
    }
    var subtitleName: String? {
        preferences.subtitleFile?.file.lastPathComponent
            ?? preferences.subtitleIndex.map { preferences.subtitleNames![$0] }
    }
    var subtitlesDisabled: Bool {
        preferences.subtitleNames != nil && preferences.subtitleIndex == nil && preferences.subtitleFile == nil
    }
    mutating func open(_ kind: String, language: String) {
        dismiss()
        guard kind == "audio" || kind == "subtitles",
            let names = kind == "audio" ? preferences.audioNames : preferences.subtitleNames
        else { return }
        let files = companions.filter { $0.kind.rawValue == kind }
        guard !names.isEmpty || !files.isEmpty else { return }
        var value = SelectionMenuPresentation()
        value.kind = kind
        value.sourceID = sourceID
        value.revision = revision
        value.entries = names.enumerated().map {
            SelectionMenuEntry(
                id: String($0.offset),
                label: $0.element.isEmpty ? SyncWatchCopy.text("unknown", language: language) : $0.element)
        }
        for file in files {
            let duplicate =
                files.filter { $0.file.lastPathComponent == file.file.lastPathComponent }.count > 1
                || names.contains(file.file.lastPathComponent)
            value.entries.append(
                SelectionMenuEntry(
                    id: "companion:" + file.id,
                    label: SelectionMenuEntry.companionLabel(
                        relativePath: file.relativePath, duplicate: duplicate, language: language)))
        }
        if kind == "subtitles" { value.entries.insert(.offTrack, at: 0) }
        let selectedFile = kind == "audio" ? preferences.audioFile : preferences.subtitleFile
        value.selectedID =
            selectedFile.map { "companion:" + $0.id }
            ?? (kind == "audio" ? preferences.audioIndex : preferences.subtitleIndex).map(String.init)
            ?? (kind == "subtitles" ? "-1" : nil)
        value.enabled = true
        menu = value
    }
    mutating func select(_ request: SelectionMenuRequest) {
        guard let menu, menu.allows(request.entryID), request.sourceID == sourceID,
            request.revision == revision, request.kind == menu.kind, request.scope == "local",
            request.action == menu.definition?.action
        else { return }
        if let file = companions.first(where: {
            "companion:" + $0.id == request.entryID && $0.kind.rawValue == request.kind
        }) {
            if request.kind == "audio" {
                preferences.audioFile = file
                preferences.audioIndex = nil
            } else {
                preferences.subtitleFile = file
                preferences.subtitleIndex = nil
            }
            dismiss()
            return
        }
        guard let index = Int(request.entryID) else { return }
        if request.kind == "audio" {
            preferences.audioIndex = index
            preferences.audioFile = nil
        } else {
            preferences.subtitleIndex = index < 0 ? nil : index
            preferences.subtitleFile = nil
        }
        dismiss()
    }
    mutating func dismiss() {
        revision += 1
        menu = nil
    }
}
