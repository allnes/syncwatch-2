using System.Windows;

namespace SyncWatch;

public partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();
        if (Environment.GetCommandLineArgs().Contains("--player-settings-gallery")) WorkspaceRoot.Children.Add(new Design.PlayerSettingsGallery());
        else if (Environment.GetCommandLineArgs().Contains("--player-gallery")) WorkspaceRoot.Children.Add(new Design.PlayerGallery());
        else if (Environment.GetCommandLineArgs().Contains("--settings-gallery")) WorkspaceRoot.Children.Add(new Design.SettingsGallery());
        else if (Environment.GetCommandLineArgs().Contains("--design-gallery")) WorkspaceRoot.Children.Add(new Design.DesignGallery());
        else
        {
            var application = (App)Application.Current;
            var preferences = application.Preferences!;
            var library = new Design.LibraryWorkspace();
            void Refresh() => library.Render(new Design.LibraryPresentation { EnabledActions = new HashSet<string> { "openSettings" } }, preferences.State.Preferences.Language);
            library.ActionRequested += (action, _) =>
            {
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
