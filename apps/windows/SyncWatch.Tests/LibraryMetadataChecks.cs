using System.IO;
using System.Windows.Threading;
using SyncWatch;
using SyncWatch.Library;

internal static class LibraryMetadataChecks
{
    internal static async Task RunAsync()
    {
        string root = Path.Combine(Path.GetTempPath(), "syncwatch-metadata-" + Guid.NewGuid());
        Directory.CreateDirectory(root);
        var reader = new ControlledMetadata();
        var model = new LibraryController(new FileLibraryAccessStore(Path.Combine(root, "state/access.json")), Dispatcher.CurrentDispatcher, metadata: reader);
        try
        {
            foreach (string name in new[] { "A.mkv", "B.mp4" }) File.WriteAllText(Path.Combine(root, name), "fixture");
            model.Choose(root); await model.Settled; await reader.Entered(1);
            var revision = model.RoomRevision; string last = model.Presentation.Entries.Last().Id;
            model.Select(last);
            model.Select(last);
            Require(model.Presentation.MetadataLoading && model.Presentation.MetadataDurationMs is null && reader.Calls == 1);
            var value = new MediaMetadata(60_000, 64, 48, 1, 0);
            reader.Complete(value); await reader.Entered(2);
            Require(model.Presentation.SelectedId == last && model.Presentation.MetadataDurationMs is null);
            reader.Fail(); await reader.Entered(3); reader.Complete(value); await model.MetadataSettled.WaitAsync(TimeSpan.FromSeconds(2));
            Require(model.Presentation.Entries.First().DurationMs == 60_000 && model.Presentation.Entries.Last().DurationMs is null);
            Require(model.Presentation.MetadataUnavailable && !model.Presentation.MetadataLoading && model.ErrorKey is null);
            Require(model.RoomRevision == revision && model.SelectedMedia()?.Media.Id == last);
            model.Rescan(); await model.Settled; await reader.Entered(4);
            reader.Complete(value); await model.MetadataSettled.WaitAsync(TimeSpan.FromSeconds(2)); Require(reader.Calls == 4);
            Require(model.Presentation.MetadataDurationMs == 60_000 && model.Presentation.MetadataAudioTracks == 1 &&
                model.Presentation.MetadataSubtitleTracks == 0 && !model.Presentation.MetadataUnavailable);
            File.WriteAllText(Path.Combine(root, "A.mkv"), "changed fixture");
            model.Rescan(); await model.Settled; await reader.Entered(5); reader.Complete(value); await reader.Entered(6);
            Require(model.Presentation.Entries.First().DurationMs is null);
            var closing = model.CloseAsync(); await Task.Yield(); Require(!reader.Closed);
            reader.Complete(value); await closing;
            Require(reader.Closed && model.SelectedMedia() is null && model.Presentation.EnabledActions.Count == 0);
            await RealVlc(root);
            Console.WriteLine("SYNCWATCH_LIBRARY_METADATA_OK stale selection, serial input, retry, close and local-only revision");
        }
        finally { reader.Abort(); await model.CloseAsync(); Directory.Delete(root, true); }
    }
    private static void Require(bool value) { if (!value) throw new InvalidOperationException("metadata-acceptance"); }
    private static async Task RealVlc(string scratch)
    {
        string? package = Environment.GetEnvironmentVariable("SYNCWATCH_METADATA_MEDIA"), source = Environment.GetEnvironmentVariable("SYNCWATCH_METADATA_FILE");
        if (package is null || source is null) return;
        string root = Path.Combine(scratch, "real"); Directory.CreateDirectory(root);
        string clip = Path.Combine(root, "Кино movie.avi"), broken = Path.Combine(root, "broken.mkv");
        File.Copy(source, clip); File.WriteAllText(broken, "not a media container");
        var grant = LibraryFolderAccess.Selected(root);
        var catalog = await new FileSystemLibrary().ScanAsync(root, grant.RootId, false);
        var good = catalog.Single(p => p.File == clip); var invalid = catalog.Single(p => p.File == broken);
        var reader = new LibraryMetadataReader(new(package, Environment.GetEnvironmentVariable("SYNCWATCH_METADATA_BRIDGE")!));
        try
        {
            for (int i = 0; i < 2; i++)
            {
                var value = await reader.ReadAsync(good, default);
                Require(value.DurationMs == 60_000 && value.Width == 320 && value.Height == 180 && value.AudioTracks == 1 && value.SubtitleTracks == 0);
            }
            bool rejected = false;
            try { await reader.ReadAsync(invalid, default); } catch (Exception) { rejected = true; }
            Require(rejected);
            var recovered = await reader.ReadAsync(good, default); Require(recovered.DurationMs == 60_000 && recovered.Width == 320);
            using (var output = new FileStream(clip, FileMode.Append, FileAccess.Write)) output.WriteByte(0);
            rejected = false;
            try { await reader.ReadAsync(good, default); } catch (Exception) { rejected = true; }
            Require(rejected); File.Delete(clip); rejected = false;
            try { await reader.ReadAsync(good, default); } catch (Exception) { rejected = true; }
            Require(rejected); Console.WriteLine("SYNCWATCH_LIBRARY_METADATA_REAL_VLC_OK");
        }
        finally { await reader.CloseAsync(); }
    }
    private sealed class ControlledMetadata : IMediaMetadataReader
    {
        private readonly Queue<TaskCompletionSource<MediaMetadata>> waiting = new();
        private bool aborted;
        internal int Calls { get; private set; }
        internal bool Closed { get; private set; }
        public Task<MediaMetadata> ReadAsync(LocalMediaFile file, CancellationToken cancellation)
        {
            Calls++; if (aborted) return Task.FromException<MediaMetadata>(new IOException("aborted"));
            // Ignore cancellation to exercise rejection of a late native result.
            var result = new TaskCompletionSource<MediaMetadata>(TaskCreationOptions.RunContinuationsAsynchronously);
            waiting.Enqueue(result); return result.Task;
        }
        internal async Task Entered(int count)
        {
            using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(2));
            while (Calls < count) await Task.Delay(5, deadline.Token);
            Require(Calls == count);
        }
        internal void Complete(MediaMetadata value) => waiting.Dequeue().SetResult(value);
        internal void Fail() => waiting.Dequeue().SetException(new IOException("unavailable"));
        internal void Abort() { aborted = true; while (waiting.TryDequeue(out var item)) item.TrySetException(new IOException("aborted")); }
        public Task CloseAsync() { Closed = true; return Task.CompletedTask; }
    }
}
