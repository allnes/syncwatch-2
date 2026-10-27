using System.Collections.Concurrent;
using System.Text.Json;
using System.Threading.Channels;
using SyncWatch.Bridge;
using SyncWatch.Domain;

internal static class HelperSessionChecks
{
    private const string Revision = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    private static void Require(bool value) { if (!value) throw new InvalidDataException("Session invariant failed"); }
    private static async Task Eventually(Func<bool> predicate)
    {
        var end = DateTime.UtcNow.AddSeconds(3);
        while (!predicate()) { if (DateTime.UtcNow >= end) throw new TimeoutException("Session check"); await Task.Delay(10); }
    }

    private sealed class OwnerContext : SynchronizationContext
    {
        private readonly BlockingCollection<(SendOrPostCallback Callback, object? State)> queue = new();
        public override void Post(SendOrPostCallback d, object? state) => queue.Add((d, state));
        internal void Run(Func<Task> action)
        {
            var previous = Current; SetSynchronizationContext(this);
            try
            {
                Task task = action();
                _ = task.ContinueWith(_ => Post(_ => queue.CompleteAdding(), null), TaskScheduler.Default);
                foreach (var item in queue.GetConsumingEnumerable()) item.Callback(item.State);
                task.GetAwaiter().GetResult();
            }
            finally { SetSynchronizationContext(previous); queue.Dispose(); }
        }
    }

    // This peer scripts IPC ordering; it contains no synchronization decisions.
    private sealed class Peer : IHelperTransport
    {
        private readonly Channel<byte[]> incoming = Channel.CreateBounded<byte[]>(64);
        private readonly List<JsonElement> sent = [];
        private JsonElement context;
        private ulong eventSequence;
        private TaskCompletionSource? writing;
        private bool holdUser;
        internal bool UserWriteHeld { get; private set; }
        private Dictionary<string, object?> Frame(string kind, object payload) => new()
        {
            ["v"] = 1,
            ["type"] = kind,
            ["payload"] = payload,
            ["clientRunId"] = context.GetProperty("clientRunId").GetString(),
            ["mediaGeneration"] = context.GetProperty("mediaGeneration").GetUInt64()
        };
        private void Push(Dictionary<string, object?> value)
        {
            byte[] frame = JsonSerializer.SerializeToUtf8Bytes(value).Concat(new byte[] { 10 }).ToArray();
            Require(incoming.Writer.TryWrite(frame));
        }
        private void Event(string kind, object payload)
        {
            var frame = Frame(kind, payload); frame["id"] = "event-" + ++eventSequence; Push(frame);
        }
        public async Task SendAsync(ReadOnlyMemory<byte> frame, CancellationToken cancellation = default)
        {
            using var doc = JsonDocument.Parse(frame); var value = doc.RootElement; context = value.Clone();
            if (value.TryGetProperty("origin", out var origin) && origin.GetString() == "user" && holdUser)
            {
                UserWriteHeld = true; writing = new(TaskCreationOptions.RunContinuationsAsynchronously);
                await writing.Task.WaitAsync(cancellation);
            }
            cancellation.ThrowIfCancellationRequested(); sent.Add(value.Clone());
            if (!value.TryGetProperty("id", out var id)) return;
            string kind = value.GetProperty("type").GetString()!;
            if (kind == "player.state") return;
            bool hello = kind == "bridge.hello";
            var reply = Frame(hello ? "bridge.ready" : "bridge.result",
                hello ? new { syncplayRevision = Revision } : (object)new { status = "applied" });
            reply["replyTo"] = id.GetString(); Push(reply);
            if (kind == "sync.connect")
            { Event("sync.identity", new { username = "Viewer_2" }); Event("sync.connection", new { state = "connected" }); }
            if (kind == "sync.setReady") Event("sync.readiness", new { ready = true });
        }
        public Task<byte[]> ReadAsync(CancellationToken cancellation = default) => incoming.Reader.ReadAsync(cancellation).AsTask();
        public ValueTask DisposeAsync() { incoming.Writer.TryComplete(); writing?.TrySetCanceled(); return ValueTask.CompletedTask; }
        internal void Readiness(bool value) => Event("sync.readiness", new { ready = value });
        internal void GateUserWrite() => holdUser = true;
        internal void ReleaseUserWrite() { holdUser = false; writing?.TrySetResult(); writing = null; }
        internal void Correction(int id, int after, long position)
        {
            var frame = Frame("player.setPosition", new { positionMs = position });
            frame["id"] = "cmd-" + id; frame["afterUserAction"] = after; Push(frame);
        }
        internal int ReplyCount(int id, string kind) => sent.Count(v => v.TryGetProperty("replyTo", out var reply) && reply.GetString() == "cmd-" + id && v.GetProperty("type").GetString() == kind);
        internal bool SawNativeEnd => sent.Any(v => v.GetProperty("type").GetString() == "player.state" && v.GetProperty("payload").GetProperty("positionMs").GetInt64() == 60000 && !v.GetProperty("payload").GetProperty("seekable").GetBoolean() && v.GetProperty("payload").GetProperty("paused").GetBoolean());
        internal int UserCount => sent.Count(v => v.TryGetProperty("origin", out var origin) && origin.GetString() == "user");
    }

    private sealed class Player(PlaybackScope owner) : IPlaybackPort
    {
        private ulong sequence;
        internal bool Paused { get; private set; }
        internal long Position { get; private set; } = 1200;
        internal int Seeks { get; private set; }
        internal int Closes { get; private set; }
        private bool ended;
        internal void FinishMedia() { ended = true; Paused = true; Position = 60000; }
        public Task<PlaybackObservation> ObserveAsync(PlaybackScope scope, CancellationToken cancellation = default)
        {
            cancellation.ThrowIfCancellationRequested(); owner.Check(scope.ClientRunId, scope.MediaGeneration);
            return Task.FromResult(new PlaybackObservation
            {
                Scope = scope,
                Sequence = ++sequence,
                Status = PlaybackStatus.Ready,
                PositionMs = Position,
                DurationMs = 60000,
                Paused = Paused,
                Seekable = !ended,
                Ended = ended
            });
        }
        public Task SetPausedAsync(bool paused, PlaybackScope scope, CancellationToken cancellation = default)
        { cancellation.ThrowIfCancellationRequested(); Paused = paused; return Task.CompletedTask; }
        public Task SeekAsync(long positionMs, PlaybackScope scope, CancellationToken cancellation = default)
        { cancellation.ThrowIfCancellationRequested(); Position = positionMs; Seeks++; return Task.CompletedTask; }
        public Task LoadAsync(string file, PlaybackScope scope, CancellationToken cancellation = default) => throw new InvalidOperationException();
        public Task SetRateAsync(double rate, PlaybackScope scope, CancellationToken cancellation = default) => throw new InvalidOperationException();
        public Task SetVolumeAsync(double volume, bool muted, PlaybackScope scope, CancellationToken cancellation = default) => throw new InvalidOperationException();
        public Task<IReadOnlyList<PlaybackTrack>> TracksAsync(bool subtitles, PlaybackScope scope, CancellationToken cancellation = default) => throw new InvalidOperationException();
        public Task SelectTrackAsync(int id, bool subtitles, PlaybackScope scope, CancellationToken cancellation = default) => throw new InvalidOperationException();
        public Task StopAsync(PlaybackScope scope, CancellationToken cancellation = default) => throw new InvalidOperationException();
        public ValueTask DisposeAsync() { Closes++; return ValueTask.CompletedTask; }
    }

    private static async Task Scenario(bool eof, bool strict = false, bool nativeEnd = false)
    {
        var native = PlaybackScope.Create().ReplacingMedia(); var player = new Player(native); var peer = new Peer();
        await using var session = new HelperSession(peer, player, native, new("localhost", 8999, "room", "Viewer"),
            new("media-1", "Movie.mkv", 60000, 1234), Revision, requireDeclaredIdentity: strict);
        if (strict)
        {
            await player.SetPausedAsync(false, native);
            session.Start(); await Eventually(() => session.State.Connection == HelperConnection.Failed);
            await session.DisposeAsync(); await session.DisposeAsync();
            Require(!session.State.Ready && session.State.IdentityRejected && session.State.AcceptedUsername is null && peer.UserCount == 0 && player.Paused && player.Closes == 0);
            return;
        }
        session.Start(); await Eventually(() => session.State.Ready);
        Require(session.State.AcceptedUsername == "Viewer_2" && player.Paused && peer.UserCount == 0);
        if (nativeEnd)
        {
            player.FinishMedia(); await Eventually(() => peer.SawNativeEnd);
            Require(session.State.Connection == HelperConnection.Connected && session.State.Ready && peer.UserCount == 0);
        }
        else if (eof)
        {
            session.Pause(false); await Eventually(() => peer.UserCount == 1);
            await peer.DisposeAsync(); await Eventually(() => session.State.Connection == HelperConnection.Failed);
        }
        else
        {
            peer.GateUserWrite(); session.Pause(false); await Eventually(() => peer.UserWriteHeld);
            peer.Correction(1, 1, 2400); await Task.Delay(30);
            Require(session.State.Connection == HelperConnection.Connected && player.Seeks == 0);
            peer.ReleaseUserWrite(); await Eventually(() => peer.ReplyCount(1, "player.result") == 1);
            peer.Correction(1, 1, 2400); await Eventually(() => peer.ReplyCount(1, "player.result") == 2);
            Require(player.Seeks == 1);
            peer.Readiness(false); await Eventually(() => !session.State.Ready);
            session.Seek(3000); await Eventually(() => peer.UserCount == 2);
            peer.Correction(2, 0, 0); await Eventually(() => peer.ReplyCount(2, "bridge.error") == 1);
            Require(player.Position == 3000 && peer.UserCount == 2);
            peer.Correction(3, 3, 0); await Eventually(() => session.State.Connection == HelperConnection.Failed);
        }
        await session.DisposeAsync(); await session.DisposeAsync(); Require(player.Paused && player.Closes == 0);
    }
    internal static void Run()
    {
        new OwnerContext().Run(async () => { await Scenario(false); await Scenario(true); await Scenario(false, strict: true); await Scenario(false, nativeEnd: true); });
        Console.WriteLine("SYNCWATCH_HELPER_SESSION_OK publication race replay stale correction future authority EOF cleanup");
    }
}
