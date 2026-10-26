using System.IO;
using System.Windows;
using System.Windows.Controls;

namespace SyncWatch;

// Bind application-owned services to common components. No screen layout is authored here.
internal sealed class ApplicationWorkspace : UserControl
{
    private readonly Window owner;
    private readonly App application;
    private readonly AppearancePreferences preferences;
    private readonly Design.LibraryWorkspace library = new();
    private readonly LibraryController catalog;
    private readonly WatchSessionCoordinator watch;
    private readonly RoomController room = new();
    private readonly Design.ApplicationChrome chrome;
    private bool started;

    public ApplicationWorkspace(Window owner, App application)
    {
        this.owner = owner; this.application = application;
        preferences = application.Preferences!;
        catalog = new LibraryController(new Library.FileLibraryAccessStore(
            Path.Combine(Path.GetDirectoryName(application.StatePath)!, "library-access.json")), Dispatcher, preferences.State.SelectedMediaId);
        var fullscreen = new WindowFullscreen(owner);
        watch = new WatchSessionCoordinator(preferences, application.Media!, fullscreen.Toggle);
        chrome = new Design.ApplicationChrome(library); Content = chrome;
        catalog.Changed += Refresh; watch.Changed += Refresh; room.Changed += Refresh;
        library.ActionRequested += Action;
        Loaded += async (_, _) =>
        {
            if (started) return; started = true;
            catalog.Restore(); await watch.PrepareRuntimeAsync();
            await WatchAcceptance.RunAsync(owner, preferences, catalog, watch);
        };
        Refresh();
    }
    public async Task CloseAsync() { await watch.CloseAsync(); await room.CloseAsync(); catalog.Dispose(); }
    private void Refresh()
    {
        library.Render(room.LibraryPresentation(watch.LibraryPresentation(catalog.Presentation)), preferences.State.Preferences.Language);
        chrome.SetPlayer(watch.Player); chrome.PresentPlayer(watch.PlayerPresented);
        if (WatchAcceptance.Requested) return;
        if ((catalog.ErrorKey ?? watch.ErrorKey) is not string key) return;
        catalog.ClearError(); watch.ClearError();
        Dispatcher.InvokeAsync(() =>
        {
            if (IsLoaded) MessageBox.Show(owner, Design.SyncWatchCopy.Text(key, preferences.State.Preferences.Language),
                "SyncWatch", MessageBoxButton.OK, MessageBoxImage.Warning);
        });
    }
    private void Action(string action, string? value)
    {
        if (action == "chooseFolder")
        {
            var picker = new Microsoft.Win32.OpenFolderDialog { Title = Design.SyncWatchCopy.Text("folder", preferences.State.Preferences.Language), Multiselect = false };
            if (picker.ShowDialog(owner) == true) catalog.Choose(picker.FolderName);
        }
        else if (action == "rescan") catalog.Rescan();
        else if (action == "selectMovie" && value is not null) catalog.Select(value);
        else if (action == "startWatching" && catalog.SelectedMedia() is LibraryMediaSelection selection) watch.Start(selection);
        else if (action == "continueWatching") watch.ContinueWatching();
        else if (action == "endWatching") watch.End();
        else if (action == "openRoom") OpenRoom();
        else if (action == "openSettings") OpenSettings();
    }
    private void OpenRoom()
    {
        var view = new Design.RoomDialog(room.Editor, preferences.State.Preferences.Language);
        var window = CreateDialog(view); bool released = false;
        room.Changed += view.Refresh;
        view.ActionRequested += async action =>
        {
            if (action == "connectRoom") room.Connect();
            else if (action == "leaveRoom") await room.CloseAsync();
            else if (action == "pasteInvitation")
            {
                try { room.PasteInvitation(Clipboard.GetText()); }
                catch (System.Runtime.InteropServices.ExternalException) { room.PasteInvitation(""); }
            }
            else if (action == "copyInvitation" && room.InvitationToCopy() is string invitation)
            {
                bool copied;
                try { Clipboard.SetText(invitation); copied = true; }
                catch (System.Runtime.InteropServices.ExternalException) { copied = false; }
                room.InvitationCopyCompleted(copied);
            }
            else if (action == "close") { if (room.Editor.Busy) await room.CloseAsync(); released = true; window.Close(); }
        };
        window.Closing += async (_, e) =>
        {
            if (!released && room.Editor.Busy) { e.Cancel = true; await room.CloseAsync(); released = true; window.Close(); }
        };
        try { window.ShowDialog(); }
        finally { room.Changed -= view.Refresh; room.Editor.ClearSecrets(); }
    }
    private Window CreateDialog(UserControl content) => new()
    {
        Content = content,
        Owner = owner,
        Title = "SyncWatch",
        WindowStyle = WindowStyle.None,
        AllowsTransparency = true,
        Background = System.Windows.Media.Brushes.Transparent,
        ResizeMode = ResizeMode.NoResize,
        SizeToContent = SizeToContent.WidthAndHeight,
        ShowInTaskbar = false,
        WindowStartupLocation = WindowStartupLocation.CenterOwner
    };
    private void OpenSettings()
    {
        var view = new Design.SettingsDialog(preferences.CreateEditor(), preferences.State.Preferences.Language);
        var window = CreateDialog(view);
        view.CloseRequested += window.Close; view.MoveRequested += window.DragMove;
        view.Persist = values =>
        {
            if (!preferences.Save(values)) return false;
            application.ApplySystemTheme(); watch.PreferencesChanged(); Refresh();
            view.SetLanguage(preferences.State.Preferences.Language); return true;
        };
        window.ShowDialog();
    }
}
