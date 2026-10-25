using System.IO;
using SyncWatch.Playback;

namespace SyncWatch;

// Application-local runtime locations. Neither value can come from a peer descriptor.
internal sealed record MediaConfiguration(string Package, string Bridge)
{
    public static MediaConfiguration Read(string[] arguments, string? directory = null)
    {
        directory ??= AppContext.BaseDirectory;
        string? Value(string flag) { int i = Array.IndexOf(arguments, flag); return i >= 0 && i + 1 < arguments.Length ? arguments[i + 1] : null; }
        return new(Path.GetFullPath(Value("--media-package") ?? Path.Combine(directory, "Media")),
            Path.GetFullPath(Value("--playback-bridge") ?? Path.Combine(directory, "syncwatch_playback.dll")));
    }
    public void Verify()
    {
        _ = MediaRuntime.Verify(Package);
        if (!File.Exists(Bridge)) throw new PlaybackException("runtime-bridge");
    }
}
