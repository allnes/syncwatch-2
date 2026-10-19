import SwiftUI

public struct DesignGallery: View {
    public init() {}
    public var body: some View { DesignFixtureGallery(subject: .library) }
}
public struct SettingsGallery: View {
    public init() {}
    public var body: some View { DesignFixtureGallery(subject: .settings) }
}
public struct PlayerGallery: View {
    public init() {}
    public var body: some View { DesignFixtureGallery(subject: .player) }
}
public struct PlayerSettingsGallery: View {
    public init() {}
    public var body: some View { DesignFixtureGallery(subject: .playerSettings) }
}
public struct CallGallery: View {
    public init() {}
    public var body: some View { DesignFixtureGallery(subject: .call) }
}
private enum DesignFixtureSubject { case library, settings, player, playerSettings, call }

/// Fixture state only. Gallery composition and modal placement are part of the shared document.
private struct DesignFixtureGallery: View {
    let subject: DesignFixtureSubject
    @State private var language = "en"
    @State private var dark = true
    @State private var failSave = false
    @State private var section = ""
    @State private var state = ""
    @State private var lastAction = ""
    @State private var library = LibraryPresentation.gallery(.selected)
    @State private var call = CallPresentation.gallery(SyncWatchCall.galleryCases[2])
    @State private var player = PlayerPresentation.gallery(.paused)
    @State private var settings = SettingsEditor(editableFields: Set(SyncWatchSettings.defaults.keys), canSave: true)
    @State private var playerSettings = PlayerSettingsEditor(
        editableFields: Set(SyncWatchPlayerSettings.defaults.keys), canSave: true)
    @State private var savedPlayerSettings = SyncWatchPlayerSettings.defaults
    @State private var modalOpen = false
    @State private var modalOffset = CGSize.zero
    private var sections: [String] {
        subject == .settings
            ? SyncWatchSettings.sections : subject == .playerSettings ? SyncWatchPlayerSettings.sections : []
    }
    private var states: [String] {
        switch subject {
        case .library: SyncWatchCopy.galleryStates
        case .settings: SyncWatchSettings.states
        case .player: SyncWatchPlayer.states
        case .playerSettings: SyncWatchPlayerSettings.states
        case .call: SyncWatchCall.galleryCases.map(\.id)
        }
    }
    private var initialState: String {
        subject == .library ? "selected" : subject == .player ? "paused" : subject == .call ? "ready" : "editing"
    }
    private var selectedSection: String { section.isEmpty ? sections.first ?? "" : section }
    private func choice(_ id: String, value: String, options: [String]) -> DesignContext {
        let label = "gallery" + id.prefix(1).uppercased() + id.dropFirst()
        return DesignContext(
            ["id": id, "label": label, "kind": "choice", "value": value, "editable": String(!modalOpen)],
            collections: ["options": options.map { DesignContext(["id": $0, "label": $0]) }])
    }
    private func toggle(_ id: String, value: Bool) -> DesignContext {
        DesignContext([
            "id": id, "label": "gallery" + id.prefix(1).uppercased() + id.dropFirst(), "kind": "boolean",
            "value": String(value), "editable": String(!modalOpen),
        ])
    }
    private var context: DesignContext {
        var controls = [choice("state", value: state.isEmpty ? initialState : state, options: states)]
        if !sections.isEmpty { controls.append(choice("section", value: selectedSection, options: sections)) }
        controls.append(choice("language", value: language, options: ["en", "ru"]))
        controls.append(toggle("dark", value: dark))
        if subject == .settings || subject == .playerSettings { controls.append(toggle("failSave", value: failSave)) }
        return DesignContext(
            [
                "lastAction": lastAction, "modalOpen": String(modalOpen),
                "modalOffsetX": String(Double(modalOffset.width)), "modalOffsetY": String(Double(modalOffset.height)),
            ], collections: ["galleryControls": controls])
    }
    public var body: some View {
        DesignSurface(
            "Gallery", context: context, language: language, slots: ["galleryContent": content, "modalContent": modal]
        ) { event in
            guard event.action == "gallery", let id = event.payload, let value = event.value, !modalOpen else { return }
            switch id {
            case "language": language = value
            case "dark": dark = value == "true"
            case "failSave": failSave = value == "true"
            case "section": section = value
            case "state":
                state = value
                switch subject {
                case .library: if let s = LibraryVisualState(rawValue: value) { library = .gallery(s) }
                case .player: if let s = PlayerVisualState(rawValue: value) { player = .gallery(s) }
                case .settings:
                    if let s = SettingsVisualState(rawValue: value) {
                        settings = SettingsEditor(
                            editableFields: Set(SyncWatchSettings.defaults.keys), canSave: true, state: s)
                    }
                case .call:
                    if let item = SyncWatchCall.galleryCases.first(where: { $0.id == value }) { call = .gallery(item) }
                case .playerSettings:
                    if let s = PlayerSettingsVisualState(rawValue: value) {
                        playerSettings = PlayerSettingsEditor(
                            editableFields: Set(SyncWatchPlayerSettings.defaults.keys), canSave: s != .readOnly,
                            state: s)
                    }
                }
            default: break
            }
        }.preferredColorScheme(dark ? .dark : .light)
    }
    private var content: AnyView {
        switch subject {
        case .library:
            AnyView(
                LibraryWorkspace(presentation: library, language: language) { action, value in
                    lastAction = action
                    if action == "selectMovie" { library.selectedID = value }
                })
        case .settings:
            AnyView(
                SettingsDialog(
                    editor: $settings, language: language, section: selectedSection, onSave: { _ in !failSave }
                ).id(selectedSection))
        case .playerSettings:
            AnyView(
                PlayerSettingsDialog(
                    editor: $playerSettings, language: language, section: selectedSection, onSave: { _ in !failSave }
                ).id(selectedSection))
        case .call:
            AnyView(
                DesignSurface(
                    "callFixture", language: language,
                    slots: [
                        "callFixtureContent": AnyView(
                            CallWindowShell(
                                presentation: call, language: language,
                                remoteSurface: AnyView(DesignSurface("callRemoteFixture", language: language)),
                                localPreview: AnyView(DesignSurface("callLocalFixture", language: language))
                            ) { request in
                                lastAction = request.action
                                call = call.applyingFixture(request)
                            })
                    ]))
        case .player:
            AnyView(
                PlayerChrome(
                    presentation: modalOpen ? disabledPlayer : player, language: language,
                    videoSurface: AnyView(
                        DesignSurface(
                            "fixtureVideo", context: DesignContext(["fixtureLabel": "playerFixture"]),
                            language: language))
                ) { action, value in
                    lastAction = action
                    switch action {
                    case "seek": player.positionMs = Int64(value ?? 0)
                    case "playPause": player.state = player.playing ? .paused : .playing
                    case "setMovieVolume": player.volume = value ?? 0
                    case "muteMovie": player.muted.toggle()
                    case "openPlayerSettings":
                        playerSettings = PlayerSettingsEditor(
                            values: savedPlayerSettings, editableFields: Set(SyncWatchPlayerSettings.defaults.keys),
                            canSave: true)
                        modalOffset = .zero
                        modalOpen = true
                    default: break
                    }
                })
        }
    }
    private var disabledPlayer: PlayerPresentation {
        var p = player
        p.enabledActions = []
        return p
    }
    private var modal: AnyView {
        AnyView(
            PlayerSettingsDialog(
                editor: $playerSettings, language: language,
                onSave: { values in
                    savedPlayerSettings = values
                    player.skipSeconds = Int(values["skipSeconds"] ?? "") ?? player.skipSeconds
                    player.volume = (Double(values["defaultVolume"] ?? "") ?? 0) / 100
                    return true
                }, onClose: { modalOpen = false },
                onMove: {
                    modalOffset.width += $0.width
                    modalOffset.height += $0.height
                }))
    }
}
