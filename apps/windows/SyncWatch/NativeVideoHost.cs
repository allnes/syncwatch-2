using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Windows.Interop;
using System.Windows.Threading;

namespace SyncWatch;

// Native lifetime only. The design's video slot supplies all layout and appearance.
internal sealed class NativeVideoHost : HwndHost
{
    private readonly Func<Task> release;
    public NativeVideoHost(Func<Task> release)
    {
        this.release = release;
        Unloaded += (_, _) => Dispatcher.BeginInvoke(DispatcherPriority.Background, new Action(() =>
        {
            // A same-turn reparent is allowed to finish before disposal.
            if (!IsLoaded) Dispose();
        }));
    }
    public event Action<nint>? SurfaceCreated;
    internal nint NativeHandle { get; private set; }
    internal bool Parked { get; private set; }
    private readonly TaskCompletionSource destroyed = new(TaskCreationOptions.RunContinuationsAsynchronously);
    internal Task Destroyed => destroyed.Task;
    protected override HandleRef BuildWindowCore(HandleRef parent)
    {
        nint handle = CreateWindowEx(0, "STATIC", "", 0x40000000 | 0x10000000 | 0x02000000 | 0x04000000,
            0, 0, 0, 0, parent.Handle, 0, 0, 0);
        if (handle == 0) throw new Win32Exception(Marshal.GetLastWin32Error());
        NativeHandle = handle; SurfaceCreated?.Invoke(handle);
        return new(this, handle);
    }
    protected override void DestroyWindowCore(HandleRef window)
    {
        Task stopped = release();
        if (stopped.IsCompletedSuccessfully) { DestroyWindow(window.Handle); destroyed.TrySetResult(); return; }
        // Unexpected visual-tree removal must not destroy a drawable still in
        // use by VLC. Park it invisibly until asynchronous native stop completes.
        nint parking = CreateWindowEx(0, "STATIC", "", 0, 0, 0, 0, 0, new nint(-3), 0, 0, 0);
        if (parking == 0) throw new Win32Exception(Marshal.GetLastWin32Error());
        ShowWindow(window.Handle, 0);
        if (SetParent(window.Handle, parking) == 0)
        {
            DestroyWindow(parking);
            throw new Win32Exception(Marshal.GetLastWin32Error());
        }
        Parked = true;
        _ = ReleaseParkedAsync(stopped, window.Handle, parking);
    }
    private async Task ReleaseParkedAsync(Task stopped, nint window, nint parking)
    {
        try { await stopped; }
        finally { DestroyWindow(window); DestroyWindow(parking); destroyed.TrySetResult(); }
    }
    [DllImport("user32.dll", CharSet = CharSet.Unicode, EntryPoint = "CreateWindowExW", SetLastError = true)]
    private static extern nint CreateWindowEx(uint extended, string type, string title, uint style,
        int x, int y, int width, int height, nint parent, nint menu, nint instance, nint parameter);
    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool DestroyWindow(nint window);
    [DllImport("user32.dll", SetLastError = true)]
    private static extern nint SetParent(nint window, nint parent);
    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool ShowWindow(nint window, int command);
}
