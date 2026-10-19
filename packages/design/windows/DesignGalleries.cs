using System.Globalization;
using System.Windows;
using System.Windows.Controls;

namespace SyncWatch.Design;

public sealed class DesignGallery : DesignFixtureGallery { public DesignGallery() : base("library") { } }
public sealed class SettingsGallery : DesignFixtureGallery { public SettingsGallery() : base("settings") { } }
public sealed class PlayerGallery : DesignFixtureGallery { public PlayerGallery() : base("player") { } }
public sealed class CallGallery : DesignFixtureGallery { public CallGallery() : base("call") { } }
public sealed class PlayerSettingsGallery : DesignFixtureGallery { public PlayerSettingsGallery() : base("playerSettings") { } }

// Fixture observations, model transitions and event wiring only. The shared Gallery tree owns the UI.
public class DesignFixtureGallery : UserControl
{
    private readonly string subject;
    private readonly DesignSurface surface = new("Gallery");
    public LibraryWorkspace Workspace { get; } = new();
    private readonly CallWindowShell callView = new();
    private readonly DesignSurface callFixture = new("callFixture"), remoteFixture = new("callRemoteFixture"), localFixture = new("callLocalFixture");
    private CallPresentation call = CallPresentation.Gallery(SyncWatchCall.GalleryCases[2]);
    private readonly PlayerChrome playerView = new();
    private SettingsDialog? settingsView;
    private PlayerSettingsDialog? editorView;
    private PlayerSettingsDialog? modalView;
    private readonly DesignSurface video = new("fixtureVideo");
    private LibraryPresentation library = LibraryPresentation.Gallery(LibraryVisualState.Selected);
    private PlayerPresentation player = PlayerPresentation.Gallery(PlayerVisualState.Paused);
    private SettingsEditor settings = new(editableFields: SyncWatchSettings.Defaults.Keys, canSave: true);
    private PlayerSettingsEditor editor = new(editableFields: SyncWatchPlayerSettings.Defaults.Keys, canSave: true);
    private IReadOnlyDictionary<string, string> savedPlayerSettings = SyncWatchPlayerSettings.Defaults;
    private string language = "en", state, section, lastAction = "";
    private bool dark = true, failSave, modalOpen;
    private double modalOffsetX, modalOffsetY;
    private ResourceDictionary? selectedTheme;
    public DesignFixtureGallery(string subject)
    {
        this.subject = subject; state = subject == "library" ? "selected" : subject == "player" ? "paused" : subject == "call" ? "ready" : "editing"; section = Sections.FirstOrDefault() ?? "";
        Content = surface;
        Workspace.ActionRequested += (action, value) => { lastAction = action; if (action == "selectMovie") library = library with { SelectedId = value }; Refresh(); };
        callView.ActionRequested += request => { lastAction = request.Action; call = call.ApplyingFixture(request); Refresh(); };
        playerView.ActionRequested += (action, value) =>
        {
            lastAction = action;
            if (action == "openPlayerSettings")
            {
                editor = new(savedPlayerSettings, SyncWatchPlayerSettings.Defaults.Keys, true);
                modalView = new(editor, language) { Persist = SavePlayerFixture };
                modalView.CloseRequested += () => { modalOpen = false; Refresh(); }; modalView.MoveDeltaRequested += delta => { modalOffsetX += delta.X; modalOffsetY += delta.Y; Refresh(); }; modalOffsetX = 0; modalOffsetY = 0; modalOpen = true;
            }
            else player = action switch { "seek" => player with { PositionMs = (long)(value ?? 0) }, "playPause" => player with { State = player.Playing ? PlayerVisualState.Paused : PlayerVisualState.Playing }, "setMovieVolume" => player with { Volume = value ?? 0 }, "muteMovie" => player with { Muted = !player.Muted }, _ => player };
            Refresh();
        };
        surface.EventRequested += e =>
        {
            if (e.Action != "gallery" || e.Payload is null || e.Value is null || modalOpen) return;
            switch (e.Payload)
            {
                case "language": language = e.Value; settingsView = null; editorView = null; break;
                case "dark": dark = e.Value == "true"; ApplyTheme(); break;
                case "failSave": failSave = e.Value == "true"; break;
                case "section": section = e.Value; settingsView?.SelectSection(section); editorView?.SelectSection(section); break;
                case "state":
                    state = e.Value;
                    switch (subject)
                    {
                        case "library": library = LibraryPresentation.Gallery(Enum.Parse<LibraryVisualState>(state, true)); break;
                        case "call": call = CallPresentation.Gallery(SyncWatchCall.GalleryCases.Single(c => c.Id == state)); break;
                        case "player": player = PlayerPresentation.Gallery(Enum.Parse<PlayerVisualState>(state, true)); break;
                        case "settings": settings = new(editableFields: SyncWatchSettings.Defaults.Keys, canSave: true, state: Enum.Parse<SettingsVisualState>(state, true)); settingsView = null; break;
                        case "playerSettings": editor = new(editableFields: SyncWatchPlayerSettings.Defaults.Keys, canSave: state != "readOnly", state: Enum.Parse<PlayerSettingsVisualState>(state, true)); editorView = null; break;
                    }
                    break;
            }
            Refresh();
        };
        ApplyTheme(); Refresh();
    }
    private string[] Sections => subject == "settings" ? SyncWatchSettings.Sections : subject == "playerSettings" ? SyncWatchPlayerSettings.Sections : [];
    private string[] States => subject switch { "library" => SyncWatchCopy.GalleryStates, "settings" => SyncWatchSettings.States, "player" => SyncWatchPlayer.States, "call" => SyncWatchCall.GalleryCases.Select(c => c.Id).ToArray(), _ => SyncWatchPlayerSettings.States };
    private DesignContext Choice(string id, string value, string[] options) => new() { Values = new() { ["id"] = id, ["label"] = "gallery" + char.ToUpperInvariant(id[0]) + id[1..], ["kind"] = "choice", ["value"] = value, ["editable"] = modalOpen ? "false" : "true" }, Collections = new() { ["options"] = options.Select(o => new DesignContext { Values = new() { ["id"] = o, ["label"] = o } }).ToArray() } };
    private DesignContext Toggle(string id, bool value) => new() { Values = new() { ["id"] = id, ["label"] = "gallery" + char.ToUpperInvariant(id[0]) + id[1..], ["kind"] = "boolean", ["value"] = value ? "true" : "false", ["editable"] = modalOpen ? "false" : "true" } };
    private void ApplyTheme()
    {
        var resources = Resources;
        if (selectedTheme is not null) resources.MergedDictionaries.Remove(selectedTheme);
        var source = Application.Current.Resources.MergedDictionaries.First(d => d.Contains("theme.dark"));
        selectedTheme = (ResourceDictionary)source[dark ? "theme.dark" : "theme.light"]; resources.MergedDictionaries.Add(selectedTheme);
    }
    private bool SavePlayerFixture(IReadOnlyDictionary<string, string> values)
    {
        savedPlayerSettings = new Dictionary<string, string>(values); player = player with { SkipSeconds = int.Parse(values["skipSeconds"], CultureInfo.InvariantCulture), Volume = double.Parse(values["defaultVolume"], CultureInfo.InvariantCulture) / 100 }; Refresh(); return true;
    }
    private void Refresh()
    {
        var controls = new List<DesignContext> { Choice("state", state, States) };
        if (Sections.Length > 0) controls.Add(Choice("section", section, Sections));
        controls.Add(Choice("language", language, ["en", "ru"])); controls.Add(Toggle("dark", dark));
        if (subject is "settings" or "playerSettings") controls.Add(Toggle("failSave", failSave));
        UIElement content;
        switch (subject)
        {
            case "library": Workspace.Render(library, language); content = Workspace; break;
            case "settings": settingsView ??= new(settings, language, section) { Persist = _ => !failSave }; content = settingsView; break;
            case "playerSettings": editorView ??= new(editor, language, section) { Persist = _ => !failSave }; content = editorView; break;
            case "call":
                remoteFixture.Render(new(), language); localFixture.Render(new(), language);
                callView.RemoteSurface = remoteFixture; callView.LocalPreview = localFixture; callView.Render(call, language);
                callFixture.Slots["callFixtureContent"] = callView; callFixture.Render(new(), language); content = callFixture; break;
            default:
                video.Render(new() { Values = new() { ["fixtureLabel"] = "playerFixture" } }, language); playerView.VideoSurface = video;
                playerView.Render(modalOpen ? player with { EnabledActions = new HashSet<string>() } : player, language); content = playerView; break;
        }
        surface.Slots["galleryContent"] = content;
        if (modalOpen && modalView is not null) surface.Slots["modalContent"] = modalView; else surface.Slots.Remove("modalContent");
        surface.Render(new() { Values = new() { ["lastAction"] = lastAction, ["modalOpen"] = modalOpen ? "true" : "false", ["modalOffsetX"] = modalOffsetX.ToString(CultureInfo.InvariantCulture), ["modalOffsetY"] = modalOffsetY.ToString(CultureInfo.InvariantCulture) }, Collections = new() { ["galleryControls"] = controls.ToArray() } }, language);
    }
}
