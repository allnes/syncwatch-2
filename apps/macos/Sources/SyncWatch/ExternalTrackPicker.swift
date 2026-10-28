import AppKit
import Foundation
import SyncWatchDesign
import SyncWatchLibrary
import UniformTypeIdentifiers

@MainActor protocol ExternalTrackChoosing: AnyObject {
    func choose(kind: String, language: String) async throws -> LocalFileAccess?
    func cancel()
}

/// OS-owned chooser; filter policy and copy are supplied by the common Design description.
@MainActor final class ExternalTrackPicker: ExternalTrackChoosing {
    private let window: @MainActor () -> NSWindow?
    private var active: NSOpenPanel?
    private var activeID: UUID?
    init(window: @escaping @MainActor () -> NSWindow?) { self.window = window }
    func choose(kind: String, language: String) async throws -> LocalFileAccess? {
        try Task.checkCancellation()
        guard active == nil,
            let filter = SyncWatchSelectionMenu.externalFileFilters.first(where: { $0.kind == kind })
        else { throw CocoaError(.fileReadUnknown) }
        let picker = NSOpenPanel()
        picker.canChooseFiles = true
        picker.canChooseDirectories = false
        picker.allowsMultipleSelection = false
        picker.allowsOtherFileTypes = false
        picker.allowedContentTypes = filter.extensions.compactMap { UTType(filenameExtension: $0) }
        picker.title = SyncWatchCopy.text(filter.label, language: language)
        let id = UUID()
        active = picker
        activeID = id
        defer {
            if active === picker {
                active = nil
                activeID = nil
            }
        }
        let file: URL? = await withTaskCancellationHandler {
            await withCheckedContinuation { continuation in
                let completion: (NSApplication.ModalResponse) -> Void = { response in
                    continuation.resume(returning: response == .OK ? picker.url : nil)
                }
                if let owner = window() {
                    picker.beginSheetModal(for: owner, completionHandler: completion)
                } else {
                    picker.begin(completionHandler: completion)
                }
            }
        } onCancel: {
            Task { @MainActor [weak self] in if self?.activeID == id { self?.cancel() } }
        }
        try Task.checkCancellation()
        return try file.map(LocalFileAccess.selected)
    }
    func cancel() { active?.cancel(nil) }
}
