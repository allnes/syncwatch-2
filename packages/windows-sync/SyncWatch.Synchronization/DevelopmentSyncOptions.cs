using System.Security.Cryptography;
using System.Text.Json;

namespace SyncWatch.Synchronization;

/// <summary>Explicit development selection; an integrity receipt does not authenticate a release or authorize a room catalog.</summary>
public sealed record DevelopmentSyncOptions(string Runtime, string Executable, string Revision, SyncEndpoint Endpoint)
{
    public static DevelopmentSyncOptions Read(string configuration)
    {
        if (!Path.IsPathFullyQualified(configuration) || new FileInfo(configuration).Length > 65536) throw new IOException("sync-config");
        using var config = JsonDocument.Parse(File.ReadAllBytes(configuration));
        var c = config.RootElement; HelperWire.Keys(c, "host", "port", "room", "username", "helperPackage");
        SyncEndpoint endpoint = new(HelperWire.Text(c.GetProperty("host"), 253), c.GetProperty("port").GetInt32(),
            HelperWire.Text(c.GetProperty("room"), 256), HelperWire.Text(c.GetProperty("username"), 64)); endpoint.Validate();
        string root = HelperWire.Text(c.GetProperty("helperPackage"), 4096);
        if (!Path.IsPathFullyQualified(root)) throw new IOException("helper-path");
        root = Path.GetFullPath(root);
        using var receipt = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(root, "helper-report.json")));
        var report = receipt.RootElement;
        string target = OperatingSystem.IsWindows() ? "windows-x64" : OperatingSystem.IsMacOS() ? "macos-arm64" : "linux-x64";
        string binary = "bin/syncwatch-helper" + (OperatingSystem.IsWindows() ? ".exe" : "");
        string revision = HelperWire.Text(report.GetProperty("syncplayRevision"), 40);
        if (report.GetProperty("target").GetString() != target || revision.Length != 40 || revision.Any(c => !char.IsAsciiHexDigit(c) || char.IsUpper(c))) throw new IOException("helper-target");
        var files = report.GetProperty("files").EnumerateObject().ToDictionary(p => p.Name, p => p.Value.GetString()!, StringComparer.Ordinal);
        if (!files.ContainsKey(binary)) throw new IOException("helper-binary");
        HashSet<string> observed = new(StringComparer.Ordinal);
        void Visit(string directory)
        {
            if ((File.GetAttributes(directory) & FileAttributes.ReparsePoint) != 0) throw new IOException("helper-link");
            foreach (string path in Directory.EnumerateFileSystemEntries(directory))
            {
                var attributes = File.GetAttributes(path);
                if ((attributes & FileAttributes.ReparsePoint) != 0) throw new IOException("helper-link");
                if ((attributes & FileAttributes.Directory) != 0) { Visit(path); continue; }
                string relative = Path.GetRelativePath(root, path).Replace('\\', '/');
                if (relative == "helper-report.json") continue;
                if (!files.TryGetValue(relative, out string? digest) || !observed.Add(relative)) throw new IOException("helper-membership");
                using var stream = File.OpenRead(path);
                if (Convert.ToHexStringLower(SHA256.HashData(stream)) != digest) throw new IOException("helper-digest");
            }
        }
        Visit(root); if (!observed.SetEquals(files.Keys)) throw new IOException("helper-membership");
        return new(root, Path.Combine(root, binary.Replace('/', Path.DirectorySeparatorChar)), revision, endpoint);
    }
}
