using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Threading;
using SyncWatch.Design;

internal static class RetainedNativeAssertions
{
    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool IsWindowVisible(nint window);

    private static void WaitUntil(Func<bool> ready)
    {
        var frame = new DispatcherFrame();
        var deadline = DateTime.UtcNow.AddSeconds(5);
        var timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(10) };
        bool timedOut = false;
        timer.Tick += (_, _) =>
        {
            timedOut = DateTime.UtcNow >= deadline;
            if (ready() || timedOut) frame.Continue = false;
        };
        timer.Start();
        try { Dispatcher.PushFrame(frame); }
        finally { timer.Stop(); }
        if (timedOut) throw new InvalidOperationException("Native retained window did not settle");
    }

    public static void Run()
    {
        if (!Environment.UserInteractive)
            throw new InvalidOperationException("Native retained acceptance requires the current user's interactive desktop");
        int releases = 0, attachments = 0;
        var native = new SyncWatch.NativeVideoHost(() => { releases++; return Task.CompletedTask; });
        native.SurfaceCreated += _ => attachments++;
        var chrome = new ApplicationChrome(new System.Windows.Controls.Border(), native);
        var window = new Window { Content = chrome, Width = 800, Height = 600, ShowActivated = false, ShowInTaskbar = false };
        try
        {
            // Create an owned HWND without opening or automating any external desktop window.
            _ = new WindowInteropHelper(window).EnsureHandle();
            window.Show();
            nint handle = native.NativeHandle;
            if (handle == 0) throw new InvalidOperationException("Native retained surface was not created");
            foreach (bool presented in new[] { true, false, true, false, true })
            {
                chrome.PresentPlayer(presented);
                window.UpdateLayout();
                try { WaitUntil(() => IsWindowVisible(handle) == presented); }
                catch (InvalidOperationException error)
                {
                    nint root = new WindowInteropHelper(window).Handle;
                    throw new InvalidOperationException($"presented={presented}, native={IsWindowVisible(handle)}, effectiveWpf={native.IsVisible}, rootNative={IsWindowVisible(root)}, rootWpf={window.IsVisible}, size={native.ActualWidth}x{native.ActualHeight}", error);
                }
                if (native.NativeHandle != handle || attachments != 1 || releases != 0 || native.Parked)
                    throw new InvalidOperationException("Navigation replaced or released the HWND owner");
                if (IsWindowVisible(handle) != presented)
                    throw new InvalidOperationException($"Native HWND visibility disagrees with presentation: presented={presented}, native={IsWindowVisible(handle)}, effectiveWpf={native.IsVisible}, ownVisibility={native.Visibility}");
            }
        }
        finally { window.Close(); native.Dispose(); }
        if (releases != 1) throw new InvalidOperationException("Native surface was not released once on final close");
        Console.WriteLine($"SYNCWATCH_RETAINED_NATIVE_OK: one HWND across navigation; released once on close; session={System.Diagnostics.Process.GetCurrentProcess().SessionId}");
    }
}
