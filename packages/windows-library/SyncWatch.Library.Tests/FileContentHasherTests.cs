using System.Text;
using System.Text.Json;
using SyncWatch.Library;

internal static class FileContentHasherTests
{
    internal static async Task RunAsync(string fixture)
    {
        using var corpus = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(Path.GetDirectoryName(Path.GetFullPath(fixture))!, "library-content.json")));
        string root = Path.Combine(Path.GetTempPath(), "syncwatch-hash-" + Guid.NewGuid()); Directory.CreateDirectory(root);
        try
        {
            string file = Path.Combine(root, "owned 🎬.avi"), rootId = Guid.NewGuid().ToString("D");
            var timestamp = DateTimeOffset.FromUnixTimeSeconds(1_600_000_000).UtcDateTime;
            var scanner = new FileSystemLibrary(); var hasher = new FileContentHasher(); LocalMediaFile? last = null;
            foreach (var item in corpus.RootElement.GetProperty("cases").EnumerateArray())
            {
                string value = string.Concat(Enumerable.Repeat(item.GetProperty("content").GetString(), item.GetProperty("repeat").GetInt32()));
                File.WriteAllBytes(file, Encoding.UTF8.GetBytes(value)); File.SetLastWriteTimeUtc(file, timestamp);
                byte[] bytes = Encoding.UTF8.GetBytes(value);
                var media = (await scanner.ScanAsync(root, rootId, false)).Single();
                if (await hasher.Sha256Async(media) != item.GetProperty("sha256").GetString()) throw new InvalidOperationException(item.GetProperty("name").GetString());
                string streamed = await hasher.Sha256Async(bytes.Length, (offset, capacity, _) =>
                    Task.FromResult(bytes.AsSpan((int)offset, Math.Min(capacity, bytes.Length - (int)offset)).ToArray()));
                if (streamed != item.GetProperty("sha256").GetString()) throw new InvalidOperationException("Scoped content digest");
                last = media;
            }
            var selected = last ?? throw new InvalidOperationException("No fixture");
            foreach (var (size, response) in new[] { (1L, Array.Empty<byte>()), (0L, new byte[] { 1 }), (1L, new byte[] { 1, 2 }) })
            {
                try { await hasher.Sha256Async(size, (_, _, _) => Task.FromResult(response)); throw new InvalidOperationException("Incomplete, oversized or trailing content accepted"); }
                catch (IOException) { }
            }
            File.WriteAllText(file, "longer");
            try { await hasher.Sha256Async(selected); throw new InvalidOperationException("Stale catalog accepted"); } catch (IOException) { }
            File.Delete(file);
            try { await hasher.Sha256Async(selected); throw new InvalidOperationException("Missing file accepted"); } catch (IOException) { }
            using var cancelled = new CancellationTokenSource(); cancelled.Cancel();
            try { await hasher.Sha256Async(selected, cancelled.Token); throw new InvalidOperationException("Cancellation ignored"); } catch (OperationCanceledException) { }
            Console.WriteLine("Passed full-content digest, preserved timestamp changes, stale/missing files, cancellation and release");
        }
        finally { Directory.Delete(root, true); }
    }
}
