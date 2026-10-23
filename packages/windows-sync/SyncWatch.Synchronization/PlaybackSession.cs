using System.Diagnostics;
using SyncWatch.Bridge;
using SyncWatch.Domain;

namespace SyncWatch.Synchronization;

public sealed record SyncEndpoint(string Host, int Port, string Room, string Username)
{
    public void Validate()
    {
        if (string.IsNullOrEmpty(Host) || Host.Length > 253 || Host.Any(c => !char.IsAsciiLetterOrDigit(c) && c is not ('.' or ':' or '_' or '-'))
            || Port is < 1 or > 65535 || string.IsNullOrEmpty(Room) || Room.EnumerateRunes().Count() > 256
            || string.IsNullOrEmpty(Username) || Username.EnumerateRunes().Count() > 64
            || (Room + Username).Any(c => c < 32 || c == 127)) throw new ArgumentException("endpoint");
    }
}

public enum LocalPlaybackAction { Pause, Seek }

/// <summary>One application media generation, real player and helper. Call StepAsync from one owner.
/// Engine policy stays in Syncplay; no expected command value is published as observed state.</summary>
public sealed class PlaybackSession : IAsyncDisposable
{
    private sealed record UserAction(LocalPlaybackAction Kind, long Value);
    private readonly IPlaybackPort player;
    private readonly PlaybackScope scope;
    private readonly HelperProcess helper;
    private readonly SemaphoreSlim owner = new(1);
    private readonly Queue<UserAction> actions = new();
    private readonly Dictionary<string, (string Kind, long Deadline)> pending = new();
    private readonly Dictionary<string, (byte[] Input, byte[] Result)> completed = new();
    private readonly Queue<string> completionOrder = new();
    private readonly long duration;
    private Task<byte[]>? incoming;
    private ulong commandSequence, userSequence, correctionSequence, eventSequence;
    private long lastPing = Stopwatch.GetTimestamp();
    private readonly long connectionDeadline = Stopwatch.GetTimestamp() + 15 * Stopwatch.Frequency;
    private bool closing, connectedOnce, readyRequested;
    private Task? shutdown;
    public bool Connected { get; private set; }
    public bool Ready { get; private set; }

    private PlaybackSession(IPlaybackPort player, PlaybackScope scope, HelperProcess helper, long duration)
    { this.player = player; this.scope = scope; this.helper = helper; this.duration = duration; }

    /// <summary>Caller supplies an already authorized, paused native selection and integrity-checked development helper.</summary>
    public static async Task<PlaybackSession> StartAsync(IPlaybackPort player, PlaybackScope scope,
        string helperExecutable, string helperRuntime, string helperRevision, string mediaName, long fileSize,
        SyncEndpoint endpoint, CancellationToken cancellation = default)
    {
        endpoint.Validate();
        if (string.IsNullOrEmpty(mediaName) || mediaName.EnumerateRunes().Count() > 256 || mediaName.Any(c => c is '/' or '\\' || c < 32 || c == 127)
            || fileSize < 0 || (ulong)fileSize > PlaybackScope.MaximumGeneration) throw new ArgumentException("media");
        PlaybackObservation value = await player.ObserveAsync(scope, cancellation).ConfigureAwait(false);
        value.Validate(); scope.Check(value.Scope.ClientRunId, value.Scope.MediaGeneration);
        if (value.Status != PlaybackStatus.Ready || value.DurationMs is not long duration || duration <= 0 || !value.Paused) throw new IOException("player-not-ready");
        HelperProcess helper = HelperProcess.Start(helperExecutable, helperRuntime);
        PlaybackSession session = new(player, scope, helper, duration);
        try
        {
            string hello = await session.CommandAsync("bridge.hello", new { supportedVersions = new[] { 1 } }, cancellation).ConfigureAwait(false);
            HelperFrame reply = await session.AwaitReplyAsync(hello, cancellation).ConfigureAwait(false);
            if (reply.Kind != "bridge.ready" || reply.Payload.GetProperty("syncplayRevision").GetString() != helperRevision) throw new IOException("helper-revision");
            string loaded = await session.CommandAsync("player.loaded", new { mediaHandle = "selected-media", name = mediaName, durationMs = duration, fileSizeBytes = fileSize }, cancellation).ConfigureAwait(false);
            await session.AwaitReplyAsync(loaded, cancellation).ConfigureAwait(false);
            string connect = await session.CommandAsync("sync.connect", new { host = endpoint.Host, port = endpoint.Port, room = endpoint.Room, username = endpoint.Username, tls = true }, cancellation).ConfigureAwait(false);
            await session.AwaitReplyAsync(connect, cancellation).ConfigureAwait(false);
            return session;
        }
        catch { await session.DisposeAsync().ConfigureAwait(false); throw; }
    }

    /// <summary>Bounded UI request queue. Only an actual resulting observation receives user authority.</summary>
    public bool Request(LocalPlaybackAction action, long value)
    {
        if (!Enum.IsDefined(action) || action == LocalPlaybackAction.Pause && value is not (0 or 1)
            || action == LocalPlaybackAction.Seek && (value < 0 || value > duration)) return false;
        lock (actions)
        {
            if (closing || !Connected || actions.Count >= 32) return false;
            actions.Enqueue(new(action, value)); return true;
        }
    }

    public async Task<PlaybackObservation> StepAsync(CancellationToken cancellation = default)
    {
        if (!await owner.WaitAsync(0, cancellation).ConfigureAwait(false)) throw new IOException("concurrent-owner");
        try
        {
            ObjectDisposedException.ThrowIf(closing, this);
            // A queued local action is observed and sent before acknowledging an older correction.
            for (int count = 0; count < 32; count++)
            {
                UserAction? action;
                lock (actions) { action = actions.TryDequeue(out var next) ? next : null; }
                if (action is null) break;
                if (!Connected) throw new IOException("disconnected");
                string kind = action.Kind == LocalPlaybackAction.Pause ? "player.setPaused" : "player.setPosition";
                PlaybackObservation actual = await ApplyAsync(kind, action.Value, cancellation).ConfigureAwait(false);
                if (userSequence == PlaybackScope.MaximumGeneration) throw new IOException("counter");
                await PublishAsync(actual, ++userSequence, cancellation).ConfigureAwait(false);
            }
            for (int count = 0; count < 64; count++)
            {
                incoming ??= helper.ReadAsync(cancellation);
                if (!incoming.IsCompleted) break;
                HelperFrame frame = HelperWire.Decode(await incoming.ConfigureAwait(false), scope);
                incoming = null;
                await ReceiveAsync(frame, cancellation).ConfigureAwait(false);
            }
            if (pending.Values.Any(p => Stopwatch.GetTimestamp() > p.Deadline)) throw new IOException("helper-timeout");
            if (!connectedOnce && Stopwatch.GetTimestamp() > connectionDeadline) throw new IOException("connection-timeout");
            if (Stopwatch.GetElapsedTime(lastPing) >= TimeSpan.FromSeconds(2))
            { await CommandAsync("bridge.ping", new { }, cancellation).ConfigureAwait(false); lastPing = Stopwatch.GetTimestamp(); }
            PlaybackObservation observation = await ObserveAsync(cancellation).ConfigureAwait(false);
            await PublishAsync(observation, null, cancellation).ConfigureAwait(false);
            if (Connected && !readyRequested)
            { await CommandAsync("sync.setReady", new { ready = true }, cancellation).ConfigureAwait(false); readyRequested = true; }
            return observation;
        }
        catch { await FailAsync().ConfigureAwait(false); throw; }
        finally { owner.Release(); }
    }

    private async Task<PlaybackObservation> ObserveAsync(CancellationToken cancellation)
    {
        var value = await player.ObserveAsync(scope, cancellation).ConfigureAwait(false);
        value.Validate(); scope.Check(value.Scope.ClientRunId, value.Scope.MediaGeneration);
        if (value.Status != PlaybackStatus.Ready || value.DurationMs != duration || value.Ended) throw new IOException("media-unavailable");
        return value;
    }
    private async Task<PlaybackObservation> ApplyAsync(string kind, double value, CancellationToken cancellation)
    {
        switch (kind)
        {
            case "player.setPaused": await player.SetPausedAsync(value != 0, scope, cancellation).ConfigureAwait(false); break;
            case "player.setPosition":
                if (value > duration) throw new IOException("seek-range");
                await player.SeekAsync((long)value, scope, cancellation).ConfigureAwait(false); break;
            case "player.setSpeed": await player.SetRateAsync(value, scope, cancellation).ConfigureAwait(false); break;
        }
        long started = Stopwatch.GetTimestamp();
        while (true)
        {
            PlaybackObservation actual = await ObserveAsync(cancellation).ConfigureAwait(false);
            bool applied = kind switch
            {
                "player.setPaused" => actual.Paused == (value != 0),
                "player.setPosition" => Math.Abs(actual.PositionMs - value) <= 1000,
                "player.setSpeed" => Math.Abs(actual.Rate - value) < .01,
                _ => true
            };
            if (applied) return actual;
            if (Stopwatch.GetElapsedTime(started) > TimeSpan.FromSeconds(2)) throw new IOException("player-timeout");
            await Task.Delay(20, cancellation).ConfigureAwait(false);
        }
    }
    private Task PublishAsync(PlaybackObservation value, ulong? user, CancellationToken cancellation) => helper.SendAsync(
        HelperWire.Encode(scope, "player.state", new
        {
            status = "ready",
            positionMs = value.PositionMs,
            durationMs = value.DurationMs,
            paused = value.Paused,
            rate = value.Rate,
            seekable = value.Seekable
        }, userAction: user), cancellation);

    private async Task<string> CommandAsync(string kind, object payload, CancellationToken cancellation)
    {
        if (pending.Count >= 16 || commandSequence == PlaybackScope.MaximumGeneration) throw new IOException("queueFull");
        string id = "cmd-" + ++commandSequence;
        pending.Add(id, (kind, Stopwatch.GetTimestamp() + 5 * Stopwatch.Frequency));
        await helper.SendAsync(HelperWire.Encode(scope, kind, payload, id: id), cancellation).ConfigureAwait(false);
        return id;
    }
    private async Task<HelperFrame> AwaitReplyAsync(string id, CancellationToken cancellation)
    {
        while (true)
        {
            byte[] bytes = await helper.ReadAsync(cancellation).WaitAsync(TimeSpan.FromSeconds(5), cancellation).ConfigureAwait(false);
            HelperFrame frame = HelperWire.Decode(bytes, scope);
            await ReceiveAsync(frame, cancellation).ConfigureAwait(false);
            if (frame.ReplyTo == id) return frame;
        }
    }
    private async Task ReceiveAsync(HelperFrame frame, CancellationToken cancellation)
    {
        if (frame.ReplyTo is string reply)
        {
            if (!pending.Remove(reply, out var request) || frame.Kind == "bridge.error"
                || frame.Kind != (request.Kind == "bridge.hello" ? "bridge.ready" : "bridge.result")) throw new IOException("helper-result");
            return;
        }
        if (frame.AfterUserAction is ulong after)
        {
            string id = frame.Id!;
            if (completed.TryGetValue(id, out var replay))
            {
                if (!frame.Bytes.AsSpan().SequenceEqual(replay.Input)) throw new IOException("conflicting-replay");
                await helper.SendAsync(replay.Result, cancellation).ConfigureAwait(false); return;
            }
            ulong number = ulong.Parse(id.AsSpan(4));
            if (number <= correctionSequence || after > userSequence) throw new IOException("correction-order");
            correctionSequence = number;
            byte[] result;
            if (after < userSequence)
                result = HelperWire.Encode(scope, "bridge.error", new { code = "cancelled", message = "cancelled", retryable = false }, replyTo: id);
            else
            {
                double value = frame.Kind switch
                {
                    "player.setPaused" => frame.Payload.GetProperty("paused").GetBoolean() ? 1 : 0,
                    "player.setPosition" => frame.Payload.GetProperty("positionMs").GetInt64(),
                    "player.setSpeed" => frame.Payload.GetProperty("rate").GetDouble(),
                    _ => 0
                };
                // Only the current application selection can be named; an engine request never opens another file.
                if (frame.Kind == "player.openFile" && frame.Payload.GetProperty("mediaHandle").GetString() != "selected-media") throw new IOException("media-selection");
                var actual = await ApplyAsync(frame.Kind, value, cancellation).ConfigureAwait(false);
                result = HelperWire.Encode(scope, "player.result", new { status = "applied", positionMs = actual.PositionMs, paused = actual.Paused }, replyTo: id);
            }
            completed.Add(id, (frame.Bytes, result)); completionOrder.Enqueue(id);
            if (completionOrder.Count > 64) completed.Remove(completionOrder.Dequeue());
            await helper.SendAsync(result, cancellation).ConfigureAwait(false); return;
        }
        ulong eventNumber = ulong.Parse(frame.Id!.AsSpan(6));
        if (eventNumber <= eventSequence) throw new IOException("event-order");
        eventSequence = eventNumber;
        if (frame.Kind == "sync.connection")
        {
            Connected = frame.Payload.GetProperty("state").GetString() == "connected";
            if (!Connected && connectedOnce) throw new IOException("disconnected");
            connectedOnce |= Connected;
        }
        else if (frame.Kind == "sync.readiness") Ready = frame.Payload.GetProperty("ready").GetBoolean();
    }
    private async Task FailAsync()
    {
        lock (actions) { closing = true; actions.Clear(); }
        Connected = Ready = false;
        try { await player.StopAsync(scope).ConfigureAwait(false); } catch { }
        await helper.DisposeAsync().ConfigureAwait(false);
    }
    public ValueTask DisposeAsync()
    {
        lock (actions) { closing = true; actions.Clear(); shutdown ??= CloseAsync(); }
        return new(shutdown);
    }
    private async Task CloseAsync()
    {
        await owner.WaitAsync().ConfigureAwait(false);
        try { await FailAsync().ConfigureAwait(false); }
        finally { owner.Release(); }
    }
}
