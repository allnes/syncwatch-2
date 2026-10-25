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
        catalog.Changed += Refresh; watch.Changed += Refresh;
        library.ActionRequested += Action;
        Loaded += async (_, _) =>
        {
            if (started) return; started = true;
            catalog.Restore(); await watch.PrepareRuntimeAsync();
            await WatchAcceptance.RunAsync(owner, preferences, catalog, watch);
        };
        Refresh();
    }
    public async Task CloseAsync() { await watch.CloseAsync(); catalog.Dispose(); }
    private void Refresh()
    {
        library.Render(watch.LibraryPresentation(catalog.Presentation), preferences.State.Preferences.Language);
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
        else if (action == "openSettings") OpenSettings();
    }
    private void OpenSettings()
    {
        var view = new Design.SettingsDialog(preferences.CreateEditor(), preferences.State.Preferences.Language);
        var window = new Window
        {
            Content = view,
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
