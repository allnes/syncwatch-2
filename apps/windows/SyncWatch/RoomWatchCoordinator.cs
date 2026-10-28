using SyncWatch.Bridge;
using SyncWatch.Design;
using SyncWatch.Domain;
using SyncWatch.Room;

namespace SyncWatch;

// Owns room admission and the helper; the watch owner retains native playback.
internal sealed class RoomWatchCoordinator(RoomController room, WatchSessionCoordinator watch, HelperConfiguration helper)
{
    private sealed record ActiveWatch(RoomWatchMembership Membership, RoomWatchContext Context, PlaybackWorkspace Player);
    private ActiveWatch? active;
    private CancellationTokenSource? cancellation;
    private Task? work;
    private bool seenMembership, closing, admitted;
    internal bool Busy { get; private set; }
    internal string Status { get; private set; } = "";
    internal string? ErrorKey { get; private set; }
    internal event Action? Changed;
    internal void ClearError() => ErrorKey = null;
    internal LibraryPresentation LibraryPresentation(LibraryPresentation source)
    {
        var result = room.LibraryPresentation(source, !Busy && active is null);
        var enabled = new HashSet<string>(result.EnabledActions);
        if (room.Connected && !Busy && active is null && watch.RuntimeAvailable && source.SelectedId is not null) enabled.Add("startWatching");
        if (Busy || closing) enabled.Remove("startWatching");
        return result with { EnabledActions = enabled, RoomStatus = Status.Length > 0 ? Status : result.RoomStatus };
    }
    internal void MembershipChanged()
    {
        if (!room.Connected) { seenMembership = false; return; }
        if (seenMembership) return;
        seenMembership = true;
        if (work is null && watch.Player is { } player)
        {
            player.RequireSharedAdmission(); Busy = true;
            work = GateExistingAsync(player);
        }
    }
    private async Task GateExistingAsync(PlaybackWorkspace player)
    {
        await Task.Yield();
        try { await player.RevokeSharedAsync(); }
        finally { Busy = false; work = null; Changed?.Invoke(); }
    }
    internal void Start(LibraryMediaSelection selection)
    {
        if (closing || work is not null) return;
        if (room.Editor.State == "disconnected") { watch.Start(selection); return; }
        if (!room.Connected || !watch.RuntimeAvailable) return;
        Busy = true; ErrorKey = null; Status = "sharedWatchPreparing";
        cancellation = new(); work = RunAsync(selection, cancellation.Token); Changed?.Invoke();
    }
    private async Task RunAsync(LibraryMediaSelection selection, CancellationToken token)
    {
        await Task.Yield();
        RoomPreparedPublication? publication = null; RoomWatchMembership? membership = null; PlaybackWorkspace? owned = null; bool finished = false; admitted = false;
        string stage = "membership";
        try
        {
            var intent = await room.BeginWatchAsync(token); membership = intent.Membership;
            stage = "runtime";
            var runtime = await helper.VerifyAsync(token);
            stage = "input";
            token.ThrowIfCancellationRequested(); watch.End(); watch.Start(selection, requiresSharedAdmission: true);
            var scope = watch.Scope; long deadline = Environment.TickCount64 + 20000;
            while (owned is null)
            {
                token.ThrowIfCancellationRequested();
                if (!room.IsCurrent(intent.Membership) || watch.Scope != scope || watch.ErrorKey is not null || Environment.TickCount64 >= deadline) throw new InvalidOperationException("media-unavailable");
                // Native readiness does not acknowledge restored position and initial track preferences.
                if (watch.Phase == WatchPhase.Active && watch.Player is { } player && player.Scope == scope)
                {
                    try
                    {
                        var observation = await player.Player.ObserveAsync(scope, token);
                        if (observation.Status == PlaybackStatus.Ready && observation.Seekable && observation.DurationMs is > 0) owned = player;
                    }
                    catch (Playback.PlaybackException) { }
                }
                if (owned is null) await Task.Delay(100, token);
            }
            stage = "media";
            var local = await owned.PrepareSharedMediaAsync(token);
            stage = "publication";
            publication = await room.PublishPreparedAsync(local, intent.Membership, token);
            stage = "generation";
            var context = await room.WatchContextAsync(intent.Membership, token);
            RequireSameGeneration(intent.Context, context);
            if (context.Bootstrap.Snapshot.WatchStatus != "active")
            {
                stage = "selection";
                context = await room.PerformWatchAsync(new RoomCommandAction.Select(publication.Media.MediaId), intent.Membership, context, token);
                if (context.Definition.Selection?.Media != publication.Media) throw new InvalidOperationException("selection-changed");
                stage = "start";
                context = await room.PerformWatchAsync(new RoomCommandAction.Start(publication.Media.MediaId), intent.Membership, context, token);
            }
            RequireMatch(local, context);
            stage = "agreement";
            var current = await room.WatchContextAsync(intent.Membership, token);
            RequireSameGeneration(context, current); RequireMatch(local, current);
            if (!ReferenceEquals(watch.Player, owned) || watch.Scope != scope) throw new InvalidOperationException("media-changed");
            active = new(intent.Membership, current, owned);
            token.ThrowIfCancellationRequested();
            stage = "helper";
            var transport = HelperProcess.Start(runtime.Executable, runtime.Package);
            try
            {
                token.ThrowIfCancellationRequested();
                if (!Authorized()) throw new InvalidOperationException("watch-revoked");
                var connection = current.Bootstrap.Connection; var remote = current.Definition.Selection!.Media;
                await owned.ConnectSharedAsync(transport,
                    new(connection.Host, connection.Port, connection.Room, intent.Membership.Identity.SyncplayUsername),
                    new("loaded-" + Guid.NewGuid().ToString("N"), remote.Title, local.DurationMs!.Value, (ulong)local.FileSizeBytes),
                    runtime.Revision, requireDeclaredIdentity: true, authority: Authorized);
            }
            catch { await transport.DisposeAsync(); throw; }
            long readyDeadline = Environment.TickCount64 + 20000;
            while (true)
            {
                token.ThrowIfCancellationRequested();
                var actual = await owned.Player.ObserveAsync(scope, token);
                if (actual.Ended) { finished = true; Status = "ended"; break; }
                if (!Authorized() || owned.SharedState is { Connection: HelperConnection.Failed or HelperConnection.Stopped }) throw new InvalidOperationException("watch-revoked");
                if (owned.SharedState is { Connection: HelperConnection.Connected, Ready: true } state)
                {
                    if (state.AcceptedUsername != intent.Membership.Identity.SyncplayUsername) throw new InvalidOperationException("identity-changed");
                    if (!admitted) { owned.AdmitSharedPlayback(); admitted = true; stage = "playback"; }
                    if (Busy) { Busy = false; Status = "sharedWatchConnected"; Changed?.Invoke(); }
                }
                else if (!admitted && Environment.TickCount64 >= readyDeadline) throw new TimeoutException();
                await Task.Delay(100, token);
            }
        }
        catch (OperationCanceledException) when (token.IsCancellationRequested) { }
        catch (Exception error)
        {
            ErrorKey = FailureKey(error, owned?.SharedState?.IdentityRejected == true);
            // Fixed vocabulary only; never serialize exception text, paths or room credentials.
            Console.Error.WriteLine($"syncwatch.shared-watch failure stage={stage} key={ErrorKey}");
            Status = ErrorKey;
        }
        finally
        {
            var previous = active; active = null; admitted = false;
            try
            {
                if (owned is not null) await owned.RevokeSharedAsync();
                if (finished && previous is not null && room.Editor.Owner && room.IsCurrent(previous.Membership))
                {
                    try { await room.PerformWatchAsync(new RoomCommandAction.End(RoomWatchEndReason.Finished), previous.Membership, previous.Context); }
                    catch (Exception) { /* Completion metadata never changes another player's timing. */ }
                }
            }
            finally
            {
                if (publication is not null && membership is not null) room.ClearPrepared(publication.Lease, membership);
                Busy = false; work = null; Changed?.Invoke();
            }
        }
    }
    private bool Authorized()
    {
        if (closing || active is not { } value || !ReferenceEquals(watch.Player, value.Player) || watch.Scope != value.Player.Scope) return false;
        // Metadata generations authorize new loads, not play/pause/seek of an admitted file.
        if (admitted) return room.CanContinuePlayback(value.Membership);
        return room.IsCurrent(value.Membership) && room.WatchBootstrap is { } current
            && current.Snapshot.Epoch == value.Context.Bootstrap.Snapshot.Epoch
            && current.Snapshot.WatchGeneration == value.Context.Bootstrap.Snapshot.WatchGeneration && current.Snapshot.WatchStatus == "active";
    }
    internal static string FailureKey(Exception error, bool identityRejected) => identityRejected ? "sharedWatchIdentityRejected"
        : error is RoomProtocolException { Message: "staleGeneration" } ? "sharedWatchRoomChanged" : "sharedWatchFailed";
    internal static void RequireSameGeneration(RoomWatchContext expected, RoomWatchContext current)
    {
        if (expected.Bootstrap.Snapshot.Epoch != current.Bootstrap.Snapshot.Epoch || expected.Bootstrap.Snapshot.WatchGeneration != current.Bootstrap.Snapshot.WatchGeneration) throw new RoomProtocolException("staleGeneration");
    }
    internal static void RequireMatch(MediaDescriptor local, RoomWatchContext context)
    {
        if (context.Bootstrap.Snapshot.WatchStatus != "active" || context.Definition.Selection is not { } selected || MediaAgreement.Resolve(selected.Media, [local]).Status != MediaAgreementStatus.Matched) throw new InvalidOperationException("media-mismatch");
    }
    private async Task StopAsync()
    {
        cancellation?.Cancel(); var pending = work;
        if (pending is not null) await pending;
        cancellation?.Dispose(); cancellation = null;
    }
    internal async Task EndAsync()
    {
        var previous = active; await StopAsync();
        if (previous is not null && room.Editor.Owner && room.IsCurrent(previous.Membership))
        {
            try { await room.PerformWatchAsync(new RoomCommandAction.End(RoomWatchEndReason.User), previous.Membership, previous.Context); }
            catch (Exception) { /* Local End already released its own playback. */ }
        }
        watch.End(); Status = ""; Changed?.Invoke();
    }
    internal async Task LeaveAsync()
    {
        await StopAsync(); await room.CloseAsync();
        if (watch.Player is { } player) await player.RevokeSharedAsync(releaseAdmission: true);
        Status = ""; seenMembership = false; Changed?.Invoke();
    }
    internal async Task CloseAsync() { closing = true; await StopAsync(); }
}
