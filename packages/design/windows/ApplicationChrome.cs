using System.Windows;
using System.Windows.Controls;

namespace SyncWatch.Design;

// Child content consists of shared Library/Player components and native leaf surfaces.
public sealed class ApplicationChrome : UserControl
{
    private readonly DesignSurface surface = new("Application");
    public ApplicationChrome(UIElement library, UIElement player)
    {
        surface.Slots["libraryContent"] = library;
        surface.Slots["playerContent"] = player;
        Content = surface;
        surface.ConfigureHost(this);
        PresentPlayer(false);
    }
    public void PresentPlayer(bool presented) => surface.Render(new()
    {
        Values = new()
        {
            ["libraryPresented"] = (!presented).ToString().ToLowerInvariant(),
            ["playerPresented"] = presented.ToString().ToLowerInvariant(),
        },
    });
}
