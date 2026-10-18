using System.Windows;

namespace SyncWatch;

public partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();
        WorkspaceRoot.Children.Add(Environment.GetCommandLineArgs().Contains("--design-gallery")
            ? new SyncWatch.Design.DesignGallery() : new SyncWatch.Design.LibraryWorkspace());
    }
}
