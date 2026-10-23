using System.Reflection;
using System.Runtime.InteropServices;

namespace SyncWatch.Playback;

internal static class Native
{
    private static readonly Lock gate = new();
    private static string? configuredPath;
    static Native() => NativeLibrary.SetDllImportResolver(typeof(Native).Assembly, Resolve);
    internal static void Configure(string path)
    {
        path = Path.GetFullPath(path);
        lock (gate)
        {
            if (!File.Exists(path) || configuredPath is not null && configuredPath != path) throw new PlaybackException("bridge-path");
            configuredPath = path;
        }
    }
    private static nint Resolve(string name, Assembly assembly, DllImportSearchPath? search)
    {
        if (name != "syncwatch_playback") return 0;
        lock (gate) return configuredPath is string path ? NativeLibrary.Load(path) : throw new PlaybackException("bridge-missing");
    }
    [StructLayout(LayoutKind.Sequential)]
    internal struct Observation
    {
        public ulong Generation, Sequence;
        public long PositionMs, DurationMs;
        public double Rate;
        public int Status, Paused, Seekable, Buffering, Ended, VideoOutputs, Width, Height, Volume, Muted;
    }
    private const string Module = "syncwatch_playback";
    [DllImport(Module, CallingConvention = CallingConvention.Cdecl, EntryPoint = "sw_playback_open")]
    internal static extern int Open([MarshalAs(UnmanagedType.LPUTF8Str)] string library, [MarshalAs(UnmanagedType.LPUTF8Str)] string revision, int output, nint surface, out nint player);
    [DllImport(Module, CallingConvention = CallingConvention.Cdecl, EntryPoint = "sw_playback_load")]
    internal static extern int Load(nint player, ulong generation, [MarshalAs(UnmanagedType.LPUTF8Str)] string file);
    [DllImport(Module, CallingConvention = CallingConvention.Cdecl, EntryPoint = "sw_playback_observe")]
    internal static extern int Observe(nint player, ulong generation, out Observation observation);
    [DllImport(Module, CallingConvention = CallingConvention.Cdecl, EntryPoint = "sw_playback_pause")]
    internal static extern int Pause(nint player, ulong generation, int paused);
    [DllImport(Module, CallingConvention = CallingConvention.Cdecl, EntryPoint = "sw_playback_seek")]
    internal static extern int Seek(nint player, ulong generation, long position);
    [DllImport(Module, CallingConvention = CallingConvention.Cdecl, EntryPoint = "sw_playback_rate")]
    internal static extern int Rate(nint player, ulong generation, double rate);
    [DllImport(Module, CallingConvention = CallingConvention.Cdecl, EntryPoint = "sw_playback_volume")]
    internal static extern int Volume(nint player, ulong generation, double volume, int muted);
    [DllImport(Module, CallingConvention = CallingConvention.Cdecl, EntryPoint = "sw_playback_stop")]
    internal static extern int Stop(nint player, ulong generation);
    [DllImport(Module, CallingConvention = CallingConvention.Cdecl, EntryPoint = "sw_playback_tracks")]
    internal static extern int Tracks(nint player, ulong generation, int subtitles, [Out] int[] ids, nuint capacity, out nuint count);
    [DllImport(Module, CallingConvention = CallingConvention.Cdecl, EntryPoint = "sw_playback_track_name")]
    internal static extern int TrackName(nint player, ulong generation, int subtitles, int id, [Out] byte[] name, nuint capacity);
    [DllImport(Module, CallingConvention = CallingConvention.Cdecl, EntryPoint = "sw_playback_select_track")]
    internal static extern int SelectTrack(nint player, ulong generation, int subtitles, int id);
    [DllImport(Module, CallingConvention = CallingConvention.Cdecl, EntryPoint = "sw_playback_close")]
    internal static extern void Close(nint player);
    internal static void Check(int code)
    {
        if (code != 0) throw new PlaybackException(code switch { 1 => "invalid", 2 => "unavailable", 3 => "stale", _ => "engine" });
    }
}
