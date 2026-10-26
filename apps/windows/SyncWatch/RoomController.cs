using System.Windows.Threading;
using SyncWatch.Design;
using SyncWatch.Library;
using SyncWatch.Room;

namespace SyncWatch;

/// <summary>The workspace owns membership independently of the visible dialog.</summary>
internal sealed class RoomController
{
    private readonly Dispatcher dispatcher = Dispatcher.CurrentDispatcher;
    public RoomEditor Editor { get; } = new();
    public RoomCatalogView? CatalogView { get; private set; }
    public RoomBootstrap? Bootstrap => CatalogView?.Bootstrap;
    public bool Connected => Editor.Connected && Bootstrap is not null;
    public event Action? Changed;
    private RoomAdmission? admission;
    private CancellationTokenSource? stop;
    private Task? work;
    private RoomMembershipSession? session;
    private RoomLocalCatalog catalogMap = new();
    private Guid? localRevision, acknowledgedRevision;
    private IReadOnlyList<LocalMediaFile> localFiles = [];
    private Task? publisher;
    private bool stopping;
    private Task? closing;
    public void Connect()
    {
        dispatcher.VerifyAccess();
        if (stopping || Editor.Busy || Connected || work is not null || !Editor.IsValid) return;
        var values = Editor.Values; bool owner = Editor.Mode == "createRoom";
        Editor.State = "connecting"; Editor.Status = "";
        stop = new(); work = RunAsync(values, owner, stop.Token); Changed?.Invoke();
    }
    public LibraryPresentation LibraryPresentation(LibraryPresentation source)
    {
        dispatcher.VerifyAccess();
        var enabled = new HashSet<string>(source.EnabledActions); if (!stopping) enabled.Add("openRoom");
        // Membership alone cannot authorize an unsynchronized local Start in a room.
        if (Editor.State != "disconnected") enabled.Remove("startWatching");
        return source with { EnabledActions = enabled, RoomStatus = Connected ? (Editor.Status is "roomCatalogPublishing" or "roomCatalogPublishFailed" ? Editor.Status : "roomMetadataConnected") : Editor.Busy ? "roomConnecting" : Editor.State == "failed" ? "roomConnectionFailed" : "disconnected" };
    }
    public void PasteInvitation(string text)
    {
        dispatcher.VerifyAccess();
        if (stopping || Editor.Busy || Editor.Connected || Editor.Mode != "joinRoom") return;
        try
        {
            var invitation = RoomInvitation.Parse(text);
            Editor.Edit("roomID", invitation.RoomId); Editor.Edit("invitation", invitation.Credential.CopyInvitation());
        }
        catch (RoomProtocolException)
        {
            Editor.ClearSecrets(); Editor.Edit("roomID", ""); Editor.Status = "roomInvitationInvalid";
        }
        Changed?.Invoke();
    }
    public string? InvitationToCopy() => Connected && admission?.Invitation is { } invitation ? new RoomInvitation(admission.RoomId, invitation).CopyText() : null;
    public void InvitationCopyCompleted(bool copied)
    {
        dispatcher.VerifyAccess();
        if (!Connected) return;
        Editor.Status = copied ? "roomInvitationCopied" : "roomInvitationCopyFailed"; Changed?.Invoke();
    }
    public Task CloseAsync() { dispatcher.VerifyAccess(); return closing ??= StopAsync(); }
    private async Task StopAsync()
    {
        await Task.Yield();
        stopping = true; stop?.Cancel();
        if (work is not null) await work;
        work = null; stop?.Dispose(); stop = null; admission = null; CatalogView = null;
        Editor.State = "disconnected"; Editor.Status = ""; Editor.RoomId = ""; Editor.MemberCount = 0; Editor.Owner = false; Editor.ClearSecrets();
        stopping = false; closing = null; Changed?.Invoke();
    }
    public void UpdateLibrary(Guid revision, Func<IReadOnlyList<LocalMediaFile>> files)
    {
        dispatcher.VerifyAccess();
        if (localRevision == revision) return;
        localRevision = revision; localFiles = files().ToArray(); StartPublisher();
    }
    private void StartPublisher()
    {
        if (stopping || !Connected || publisher is not null || session is null || localRevision is null || localRevision == acknowledgedRevision || stop is null) return;
        publisher = PublishLibraryAsync(session, stop.Token);
    }
    private async Task PublishLibraryAsync(RoomMembershipSession owner, CancellationToken cancellation)
    {
        await Task.Yield();
        try
        {
            while (!cancellation.IsCancellationRequested && !stopping && ReferenceEquals(session, owner) && localRevision is Guid revision && revision != acknowledgedRevision)
            {
                try
                {
                    var publication = catalogMap.Prepare(localFiles); Editor.Status = "roomCatalogPublishing"; Changed?.Invoke();
                    var view = await owner.PublishAsync(publication.Items, cancellation);
                    cancellation.ThrowIfCancellationRequested(); if (stopping || !ReferenceEquals(session, owner)) return;
                    catalogMap.Acknowledge(publication); acknowledgedRevision = revision; Accept(view);
                    if (Editor.Status is "roomCatalogPublishing" or "roomCatalogPublishFailed") Editor.Status = "";
                    Changed?.Invoke();
                }
                catch (Exception)
                {
                    if (cancellation.IsCancellationRequested || stopping || !ReferenceEquals(session, owner)) return;
                    if (localRevision != revision) continue;
                    Editor.Status = "roomCatalogPublishFailed"; Changed?.Invoke(); return;
                }
            }
        }
        finally { publisher = null; }
    }
    private void Accept(RoomCatalogView view)
    {
        if (view.Bootstrap.Snapshot.Sequence < (Bootstrap?.Snapshot.Sequence ?? 0)) return;
        CatalogView = view; Editor.MemberCount = view.Bootstrap.Snapshot.Members.Count;
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
            var ownerSession = new RoomMembershipSession(current, admitted, identity);
            var firstView = await ownerSession.RefreshAsync(initial, cancellation: cancellation);
            cancellation.ThrowIfCancellationRequested(); session = ownerSession; catalogMap = new(); acknowledgedRevision = null; CatalogView = firstView;
            Editor.State = "connected"; Editor.RoomId = admitted.RoomId; Editor.MemberCount = initial.Snapshot.Members.Count; Editor.Owner = owner; Changed?.Invoke(); StartPublisher();
            while (!cancellation.IsCancellationRequested)
            {
                var update = RoomInvalidation.Decode(await stream.ReceiveAsync(cancellation)); var previous = Bootstrap;
                if (previous is null || update.Epoch != previous.Snapshot.Epoch) throw new RoomProtocolException("malformed");
                if (update.Sequence <= previous.Snapshot.Sequence) continue;
                var complete = await ownerSession.RefreshAsync(sequence: update.Sequence, cancellation: cancellation);
                cancellation.ThrowIfCancellationRequested(); Accept(complete); Changed?.Invoke();
            }
        }
        catch (Exception) { failed = !cancellation.IsCancellationRequested; stop?.Cancel(); Editor.State = "connecting"; Changed?.Invoke(); }
        finally
        {
            if (publisher is not null) await publisher;
            publisher = null; session = null; acknowledgedRevision = null; catalogMap = new();
            if (current is not null)
            {
                if (admitted is not null)
                {
                    using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(3));
                    try { await current.LeaveAsync(admitted, timeout.Token); } catch (Exception) { }
                }
                await current.DisposeAsync();
            }
            admission = null; CatalogView = null; Editor.ClearSecrets(); Editor.MemberCount = 0; Editor.Owner = false; work = null; stop?.Dispose(); stop = null; if (failed) { Editor.State = "failed"; Editor.Status = "roomConnectionFailed"; }
            Changed?.Invoke();
        }
    }
}
