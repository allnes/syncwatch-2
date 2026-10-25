using System.Windows;

namespace SyncWatch;

public partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();
        if (LocalPlaybackLaunch.Read(Environment.GetCommandLineArgs()) is LocalPlaybackLaunch launch)
        {
            var application = (App)Application.Current;
            var playback = new PlaybackWorkspace(launch, application.Preferences!.State.Preferences.Language);
            WorkspaceRoot.Children.Add(playback);
            bool released = false, closing = false;
            Closing += async (_, e) =>
            {
                if (released) return;
                e.Cancel = true;
                if (closing) return;
                closing = true;
                await playback.DisposeAsync(); released = true;
                // Even an already-completed release must leave this Closing
                // callback before issuing the final native close.
                await Dispatcher.InvokeAsync(Close);
            };
            return;
        }
        if (Environment.GetCommandLineArgs().Contains("--selection-menu-gallery")) WorkspaceRoot.Children.Add(new Design.SelectionMenuGallery());
        else if (Environment.GetCommandLineArgs().Contains("--call-gallery")) WorkspaceRoot.Children.Add(new Design.CallGallery());
        else if (Environment.GetCommandLineArgs().Contains("--player-settings-gallery")) WorkspaceRoot.Children.Add(new Design.PlayerSettingsGallery());
        else if (Environment.GetCommandLineArgs().Contains("--player-gallery")) WorkspaceRoot.Children.Add(new Design.PlayerGallery());
        else if (Environment.GetCommandLineArgs().Contains("--settings-gallery")) WorkspaceRoot.Children.Add(new Design.SettingsGallery());
        else if (Environment.GetCommandLineArgs().Contains("--design-gallery")) WorkspaceRoot.Children.Add(new Design.DesignGallery());
        else
        {
            var application = (App)Application.Current;
            var preferences = application.Preferences!;
            var library = new Design.LibraryWorkspace();
            var controller = new LibraryController(new Library.FileLibraryAccessStore(
                System.IO.Path.Combine(System.IO.Path.GetDirectoryName(AppearancePreferences.DefaultPath)!, "library-access.json")),
                Dispatcher, preferences.State.SelectedMediaId);
            void Refresh()
            {
                library.Render(controller.Presentation, preferences.State.Preferences.Language);
                if (controller.ErrorKey is string key)
                {
                    controller.ClearError();
                    Dispatcher.InvokeAsync(() => { if (IsLoaded) MessageBox.Show(this, Design.SyncWatchCopy.Text(key, preferences.State.Preferences.Language),
                        "SyncWatch", MessageBoxButton.OK, MessageBoxImage.Warning); });
                }
            }
            controller.Changed += Refresh;
            Loaded += (_, _) => controller.Restore();
            Closing += (_, _) => controller.Dispose();
            library.ActionRequested += (action, value) =>
            {
                if (action == "chooseFolder")
                {
                    var picker = new Microsoft.Win32.OpenFolderDialog { Title = Design.SyncWatchCopy.Text("folder", preferences.State.Preferences.Language), Multiselect = false };
                    if (picker.ShowDialog(this) == true) controller.Choose(picker.FolderName);
                    return;
                }
                if (action == "rescan") { controller.Rescan(); return; }
                if (action == "selectMovie" && value is not null) { controller.Select(value); return; }
                if (action != "openSettings") return;
                var view = new Design.SettingsDialog(preferences.CreateEditor(), preferences.State.Preferences.Language);
                var window = new Window
                {
                    Content = view,
                    Owner = this,
                    Title = "SyncWatch",
                    WindowStyle = WindowStyle.None,
                    AllowsTransparency = true,
                    Background = System.Windows.Media.Brushes.Transparent,
                    ResizeMode = ResizeMode.NoResize,
                    SizeToContent = SizeToContent.WidthAndHeight,
                    ShowInTaskbar = false,
                    WindowStartupLocation = WindowStartupLocation.CenterOwner
                };
                view.CloseRequested += () => window.Close();
                view.MoveRequested += window.DragMove;
                view.Persist = values =>
                {
                    if (!preferences.Save(values)) return false;
                    application.ApplySystemTheme(); Refresh(); view.SetLanguage(preferences.State.Preferences.Language); return true;
                };
                window.ShowDialog();
            };
            WorkspaceRoot.Children.Add(library); Refresh();
        }
    }
}
