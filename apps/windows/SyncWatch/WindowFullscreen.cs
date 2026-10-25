using System.Windows;
using System.Windows.Input;

namespace SyncWatch;

// Window presentation outlives each media owner.
internal sealed class WindowFullscreen
{
    private readonly Window window;
    private bool fullscreen;
    private WindowState savedState;
    private WindowStyle savedStyle;
    public WindowFullscreen(Window window)
    {
        this.window = window;
        window.KeyDown += (_, e) => { if (!e.Handled && fullscreen && e.Key == Key.Escape) { Toggle(); e.Handled = true; } };
    }
    public void Toggle()
    {
        if (fullscreen) { window.WindowStyle = savedStyle; window.WindowState = savedState; }
        else
        {
            savedState = window.WindowState; savedStyle = window.WindowStyle;
            window.WindowStyle = WindowStyle.None; window.WindowState = WindowState.Maximized;
        }
        fullscreen = !fullscreen;
    }
}
