using SyncWatch.Design;
using SyncWatch.Room;

namespace SyncWatch;

/// <summary>The workspace owns membership independently of the visible dialog.</summary>
internal sealed class RoomController
{
    public RoomEditor Editor { get; } = new();
    public RoomBootstrap? Bootstrap { get; private set; }
    public bool Connected => Editor.Connected && Bootstrap is not null;
    public event Action? Changed;
    private RoomAdmission? admission;
    private CancellationTokenSource? stop;
    private Task? work;
    private bool stopping;
    private Task? closing;
    public void Connect()
    {
        if (stopping || Editor.Busy || Connected || work is not null || !Editor.IsValid) return;
        var values = Editor.Values; bool owner = Editor.Mode == "createRoom";
        Editor.State = "connecting"; Editor.Status = "";
        stop = new(); work = RunAsync(values, owner, stop.Token); Changed?.Invoke();
    }
    public LibraryPresentation LibraryPresentation(LibraryPresentation source)
    {
        var enabled = new HashSet<string>(source.EnabledActions); if (!stopping) enabled.Add("openRoom");
        // Membership alone cannot authorize an unsynchronized local Start in a room.
        if (Editor.State != "disconnected") enabled.Remove("startWatching");
        return source with { EnabledActions = enabled, RoomStatus = Connected ? "roomMetadataConnected" : Editor.Busy ? "roomConnecting" : Editor.State == "failed" ? "roomConnectionFailed" : "disconnected" };
    }
    public string? InvitationToCopy() => Connected && admission?.Invitation is { } invitation ? admission.RoomId + "\n" + invitation.CopyInvitation() : null;
    public void InvitationCopied() { Editor.Status = "roomInvitationCopied"; Changed?.Invoke(); }
    public Task CloseAsync() => closing ??= StopAsync();
    private async Task StopAsync()
    {
        await Task.Yield();
        stopping = true; stop?.Cancel();
        if (work is not null) await work;
        work = null; stop?.Dispose(); stop = null; admission = null; Bootstrap = null;
        Editor.State = "disconnected"; Editor.Status = ""; Editor.RoomId = ""; Editor.MemberCount = 0; Editor.Owner = false; Editor.ClearSecrets();
        stopping = false; closing = null; Changed?.Invoke();
    }
    private async Task RunAsync(IReadOnlyDictionary<string, string> values, bool owner, CancellationToken cancellation)
    {
        await Task.Yield(); RoomClient? current = null; RoomAdmission? admitted = null; bool failed = false;
        try
        {
            current = new(new(values["serviceAddress"]));
            var identity = new RoomIdentity("run-" + Guid.NewGuid().ToString("N"), values["username"]);
            admitted = owner ? await current.CreateAsync(identity, new(values["syncplayHost"], int.Parse(values["syncplayPort"], System.Globalization.CultureInfo.InvariantCulture), values["roomName"]), new(values["creationKey"]), cancellation)
                : await current.JoinAsync(values["roomID"], new(values["invitation"]), identity, cancellation);
            admission = admitted; Editor.ClearSecrets();
            var stream = await current.OpenEventsAsync(admitted, cancellation);
            using var initialTimeout = CancellationTokenSource.CreateLinkedTokenSource(cancellation); initialTimeout.CancelAfter(TimeSpan.FromSeconds(20));
            var initial = RoomBootstrap.InitialEvent(await stream.ReceiveAsync(initialTimeout.Token), admitted);
            cancellation.ThrowIfCancellationRequested(); Bootstrap = initial;
            Editor.State = "connected"; Editor.RoomId = admitted.RoomId; Editor.MemberCount = initial.Snapshot.Members.Count; Editor.Owner = owner; Changed?.Invoke();
            while (!cancellation.IsCancellationRequested)
            {
                var update = RoomInvalidation.Decode(await stream.ReceiveAsync(cancellation)); var previous = Bootstrap;
                if (previous is null || update.Epoch != previous.Snapshot.Epoch) throw new RoomProtocolException("malformed");
                if (update.Sequence <= previous.Snapshot.Sequence) continue;
                var snapshot = await current.SnapshotAsync(admitted, cancellation);
                if (snapshot.Snapshot.Epoch != previous.Snapshot.Epoch || snapshot.Snapshot.Sequence < update.Sequence || snapshot.Connection != initial.Connection
                    || !snapshot.Snapshot.Members.Any(p => p.MemberId == admitted.MemberId && p.Identity == identity)) throw new RoomProtocolException("malformed");
                Bootstrap = snapshot; Editor.MemberCount = snapshot.Snapshot.Members.Count; Changed?.Invoke();
            }
        }
        catch (Exception) { failed = !cancellation.IsCancellationRequested; Editor.State = "connecting"; Changed?.Invoke(); }
        finally
        {
            if (current is not null)
            {
                if (admitted is not null)
                {
                    using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(3));
                    try { await current.LeaveAsync(admitted, timeout.Token); } catch (Exception) { }
                }
                await current.DisposeAsync();
            }
            admission = null; Bootstrap = null; Editor.ClearSecrets(); Editor.MemberCount = 0; Editor.Owner = false; work = null; stop?.Dispose(); stop = null; if (failed) { Editor.State = "failed"; Editor.Status = "roomConnectionFailed"; }
            Changed?.Invoke();
        }
    }
}
