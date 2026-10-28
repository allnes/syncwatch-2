import Foundation

public struct SelectionMenuEntry: Sendable, Codable, Equatable {
    public let id: String
    public let label: String
    public let enabled: Bool
    public let disabledTrack: Bool?
    public init(id: String, label: String, enabled: Bool = true, disabledTrack: Bool? = nil) {
        self.id = id
        self.label = label
        self.enabled = enabled
        self.disabledTrack = disabledTrack
    }
    public static var offTrack: Self { Self(id: "-1", label: "off", disabledTrack: true) }
    public static func observedLabel(_ name: String, language: String) -> String {
        guard !name.isEmpty, name.utf8.count <= SyncWatchSelectionMenu.maximumLabelBytes,
            !name.unicodeScalars.contains(where: { $0.value < 32 || $0.value == 127 })
        else { return SyncWatchCopy.text("unknown", language: language) }
        return name
    }
    public static func externalFile(kind: String, language: String) -> Self? {
        guard let filter = SyncWatchSelectionMenu.externalFileFilters.first(where: { $0.kind == kind }) else {
            return nil
        }
        return Self(
            id: SyncWatchSelectionMenu.externalFileID, label: SyncWatchCopy.text(filter.label, language: language))
    }
    public static func externalFileFailure(language: String) -> Self {
        Self(
            id: SyncWatchSelectionMenu.externalFileErrorID,
            label: SyncWatchCopy.text(SyncWatchSelectionMenu.externalFileErrorLabel, language: language), enabled: false
        )
    }
}

public struct SelectionMenuRequest: Sendable, Codable, Equatable {
    public let kind: String
    public let sourceID: String
    public let revision: Int64
    public let entryID: String
    public let action: String
    public let scope: String
}

/// Provider observations only. Selection requests require the current source/revision and never update selection.
public struct SelectionMenuPresentation: Sendable, Codable {
    public var kind = "playlist"
    public var sourceID = ""
    public var revision: Int64 = 0
    public var entries: [SelectionMenuEntry] = []
    public var selectedID: String?
    public var enabled = false
    public init() {}
    public var definition: SelectionMenuKind? { SyncWatchSelectionMenu.kinds.first { $0.id == kind } }
    public var contextToken: String { "\(kind)|\(sourceID)|\(revision)" }
    private static func validID(_ value: String) -> Bool {
        !value.isEmpty && value.utf8.count <= SyncWatchSelectionMenu.maximumIDBytes
            && value.range(of: "[^A-Za-z0-9._:-]", options: .regularExpression) == nil
    }
    public var isValid: Bool {
        definition != nil && Self.validID(sourceID) && revision >= 0
            && revision <= Int64(SyncWatchSelectionMenu.maximumRevision)
            && entries.count <= SyncWatchSelectionMenu.maximumEntries
            && Set(entries.map(\.id)).count == entries.count
            && entries.allSatisfy {
                Self.validID($0.id) && !$0.label.isEmpty
                    && $0.label.utf8.count <= SyncWatchSelectionMenu.maximumLabelBytes
                    && !$0.label.unicodeScalars.contains { $0.value < 32 || $0.value == 127 }
            } && (selectedID == nil || entries.contains { $0.id == selectedID })
    }
    public func allows(_ id: String) -> Bool {
        isValid && enabled && id != selectedID && entries.contains { $0.id == id && $0.enabled }
    }
    public func dispatch(_ id: String, contextToken: String, to handler: (SelectionMenuRequest) -> Void) {
        guard contextToken == self.contextToken, allows(id), let definition else { return }
        handler(
            SelectionMenuRequest(
                kind: kind, sourceID: sourceID, revision: revision, entryID: id, action: definition.action,
                scope: definition.scope))
    }
}
