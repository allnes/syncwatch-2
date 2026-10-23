using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;

namespace SyncWatch.Playback;

public sealed class PlaybackException(string code) : Exception(code);

// This is a development integrity receipt, not release authentication or an atomic seal.
public sealed record MediaRuntime(string Library, string Revision)
{
    public static MediaRuntime Verify(string package)
    {
        string root = Path.GetFullPath(package);
        using JsonDocument report = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(root, "build-report.json")));
        JsonElement value = report.RootElement;
        string target = OperatingSystem.IsWindows() ? "windows-x64" : OperatingSystem.IsMacOS() ? "macos-arm64" : "linux-x64";
        string library = OperatingSystem.IsWindows() ? "bin/libvlc.dll" : OperatingSystem.IsMacOS() ? "lib/libvlc.dylib" : "lib/libvlc.so.5";
        string? revision = value.GetProperty("sources").GetProperty("vlc").GetProperty("revision").GetString();
        if (RuntimeInformation.ProcessArchitecture != (OperatingSystem.IsMacOS() ? Architecture.Arm64 : Architecture.X64)
            || value.GetProperty("sdk").GetProperty("target").GetString() != target || revision?.Length != 40)
            throw new PlaybackException("runtime-target");
        var expected = value.GetProperty("files").EnumerateObject().ToDictionary(p => p.Name, p => p.Value.GetString()!, StringComparer.Ordinal);
        if (!expected.ContainsKey(library)) throw new PlaybackException("runtime-library");
        HashSet<string> observed = new(StringComparer.Ordinal);
        void Visit(string directory)
        {
            foreach (string file in Directory.EnumerateFileSystemEntries(directory))
            {
                var attributes = File.GetAttributes(file);
                if ((attributes & FileAttributes.ReparsePoint) != 0) throw new PlaybackException("runtime-link");
                if ((attributes & FileAttributes.Directory) != 0) { Visit(file); continue; }
                string name = Path.GetRelativePath(root, file).Replace('\\', '/');
                if (name == "build-report.json") continue;
                if (!observed.Add(name) || !expected.TryGetValue(name, out string? digest)) throw new PlaybackException("runtime-membership");
                using var stream = File.OpenRead(file);
                if (Convert.ToHexStringLower(SHA256.HashData(stream)) != digest) throw new PlaybackException("runtime-digest");
            }
        }
        if ((File.GetAttributes(root) & FileAttributes.ReparsePoint) != 0) throw new PlaybackException("runtime-link");
        Visit(root);
        if (!observed.SetEquals(expected.Keys)) throw new PlaybackException("runtime-membership");
        return new(Path.Combine(root, library.Replace('/', Path.DirectorySeparatorChar)), revision);
    }
}
