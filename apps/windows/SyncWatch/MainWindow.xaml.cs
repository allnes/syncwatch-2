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
            var workspace = new ApplicationWorkspace(this, (App)Application.Current);
            WorkspaceRoot.Children.Add(workspace);
            bool released = false, closing = false;
            Closing += async (_, e) =>
            {
                if (released) return;
                e.Cancel = true;
                if (closing) return;
                closing = true;
                try
                {
                    await workspace.CloseAsync(); released = true;
                    await Dispatcher.InvokeAsync(Close);
                }
                catch (Exception) { closing = false; }
            };
        }
    }
}
