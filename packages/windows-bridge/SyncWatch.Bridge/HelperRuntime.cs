using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace SyncWatch.Bridge;

/// <summary>Local development integrity, not release authentication or an atomic filesystem seal.</summary>
public sealed class HelperRuntime
{
    public string Package { get; }
    public string Executable { get; }
    public string Revision { get; }
    private HelperRuntime(string package, string executable, string revision)
    { Package = package; Executable = executable; Revision = revision; }
    public static string ExpectedRevision => HelperRuntimePolicy.SyncplayRevision;
    public static HelperRuntime Verify(string package, CancellationToken cancellation = default)
    {
        cancellation.ThrowIfCancellationRequested();
        string root = Path.GetFullPath(package), receipt = Path.Combine(root, "helper-report.json");
        if (!OperatingSystem.IsWindows() || (File.GetAttributes(root) & FileAttributes.ReparsePoint) != 0
            || (File.GetAttributes(receipt) & FileAttributes.ReparsePoint) != 0 || new FileInfo(receipt).Length > 16 * 1024 * 1024)
            throw new InvalidOperationException("helper-runtime");
        using var document = JsonDocument.Parse(File.ReadAllBytes(receipt)); var report = document.RootElement;
        if (report.GetProperty("schemaVersion").GetInt32() != 1 || report.GetProperty("target").GetString() != "windows-x64"
            || report.GetProperty("syncplayRevision").GetString() != HelperRuntimePolicy.SyncplayRevision
            || !report.GetProperty("developmentHelperOnly").GetBoolean() || report.GetProperty("authenticatedInstallation").GetBoolean())
            throw new InvalidOperationException("helper-runtime");
        var files = report.GetProperty("files").EnumerateObject().ToDictionary(p => p.Name, p => p.Value.GetString()!, StringComparer.Ordinal);
        if (!files.ContainsKey("bin/syncwatch-helper.exe") || !files.ContainsKey("app/syncplay-revision.txt")) throw new InvalidOperationException("helper-runtime");
        foreach (var (name, digest) in files)
            if (name.Contains('\\') || name.Contains(':') || name.Any(c => c < 32) || name.Split('/').Any(p => p is "" or "." or "..")
                || !Regex.IsMatch(digest, "\\A[0-9a-f]{64}\\z", RegexOptions.CultureInvariant)) throw new InvalidOperationException("helper-runtime");
        HashSet<string> observed = new(StringComparer.Ordinal);
        byte[] buffer = new byte[1024 * 1024];
        void Visit(string directory)
        {
            foreach (string file in Directory.EnumerateFileSystemEntries(directory))
            {
                cancellation.ThrowIfCancellationRequested();
                var attributes = File.GetAttributes(file);
                if ((attributes & FileAttributes.ReparsePoint) != 0) throw new InvalidOperationException("helper-runtime");
                if ((attributes & FileAttributes.Directory) != 0) { Visit(file); continue; }
                string name = Path.GetRelativePath(root, file).Replace('\\', '/');
                if (name == "helper-report.json") continue;
                if (!observed.Add(name) || !files.TryGetValue(name, out string? digest)) throw new InvalidOperationException("helper-runtime");
                using var input = File.OpenRead(file);
                using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
                int read;
                while ((read = input.Read(buffer)) != 0) { cancellation.ThrowIfCancellationRequested(); hash.AppendData(buffer, 0, read); }
                if (Convert.ToHexStringLower(hash.GetHashAndReset()) != digest) throw new InvalidOperationException("helper-runtime");
            }
        }
        Visit(root);
        if (!observed.SetEquals(files.Keys) || File.ReadAllText(Path.Combine(root, "app", "syncplay-revision.txt")).Trim() != HelperRuntimePolicy.SyncplayRevision)
            throw new InvalidOperationException("helper-runtime");
        return new(root, Path.Combine(root, "bin", "syncwatch-helper.exe"), HelperRuntimePolicy.SyncplayRevision);
    }
}
