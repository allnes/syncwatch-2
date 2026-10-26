using System.Net.Http.Headers;
using System.Net.WebSockets;
using System.Text.Json;

namespace SyncWatch.Room;

/// <summary>One room attempt owns all network work. Close cancels and joins it.</summary>
public sealed class RoomClient : IAsyncDisposable
{
    public RoomAddress Address { get; }
    private readonly HttpClient client;
    private readonly CancellationTokenSource lifetime = new();
    private readonly object gate = new();
    private readonly HashSet<TaskCompletionSource> requests = [];
    private TaskCompletionSource? closing;
    private RoomEventStream? eventStream;
    private bool eventsRequested;
    public RoomClient(RoomAddress address)
    {
        Address = address;
        client = new HttpClient(new SocketsHttpHandler
        {
            AllowAutoRedirect = false,
            UseCookies = false,
            Credentials = null,
            PreAuthenticate = false,
            MaxConnectionsPerServer = 2,
            MaxResponseHeadersLength = 16,
            ConnectTimeout = TimeSpan.FromSeconds(10)
        })
        { Timeout = TimeSpan.FromSeconds(20), MaxResponseContentBufferSize = RoomWire.MaximumBytes };
    }
    public async Task<RoomAdmission> CreateAsync(RoomIdentity identity, RoomConnection connection, RoomSecret creationKey, CancellationToken cancellation = default)
    {
        byte[] body = RoomWire.Encode(new
        {
            v = 1,
            clientRunId = identity.ClientRunId,
            syncplayUsername = identity.SyncplayUsername,
            syncplayHost = connection.Host,
            syncplayPort = connection.Port,
            syncplayRoom = connection.Room
        });
        return RoomAdmission.Decode(await RequestAsync(HttpMethod.Post, "v1/rooms", creationKey, body, cancellation), identity, true);
    }
    public async Task<RoomAdmission> JoinAsync(string roomId, RoomSecret invitation, RoomIdentity identity, CancellationToken cancellation = default)
    {
        RoomWire.Id(roomId);
        byte[] body = RoomWire.Encode(new { v = 1, invitation = invitation.Value, clientRunId = identity.ClientRunId, syncplayUsername = identity.SyncplayUsername });
        return RoomAdmission.Decode(await RequestAsync(HttpMethod.Post, $"v1/rooms/{roomId}/join", null, body, cancellation), identity, false);
    }
    public async Task<RoomBootstrap> SnapshotAsync(RoomAdmission admission, CancellationToken cancellation = default) =>
        RoomBootstrap.Decode(await RequestAsync(HttpMethod.Get, $"v1/rooms/{admission.RoomId}/snapshot", admission.Token, null, cancellation));
    public async Task<RoomCatalogPage> CatalogAsync(RoomAdmission admission, RoomBootstrap bootstrap, string cursor, CancellationToken cancellation = default)
    {
        if (bootstrap.Snapshot.Epoch != admission.Bootstrap.Snapshot.Epoch) throw RoomWire.Bad();
        _ = new RoomCatalogPosition(cursor, bootstrap);
        return RoomCatalogPage.Decode(await RequestAsync(HttpMethod.Get, $"v1/rooms/{admission.RoomId}/catalog", admission.Token, null, cancellation, cursor), bootstrap, cursor);
    }
    public async Task LeaveAsync(RoomAdmission admission, CancellationToken cancellation = default)
    {
        using var document = RoomWire.Parse(await RequestAsync(HttpMethod.Post, $"v1/rooms/{admission.RoomId}/leave", admission.Token, null, cancellation));
        var value = document.RootElement; RoomWire.Keys(value, "v", "status");
        if (RoomWire.Integer(value, "v", 1) != 1 || RoomWire.String(value, "status") != "left") throw RoomWire.Bad();
    }
    /// <summary>Attach immediately after admission, before hashing media.</summary>
    public async Task<RoomEventStream> OpenEventsAsync(RoomAdmission admission, CancellationToken cancellation = default)
    {
        TaskCompletionSource completed = new(TaskCreationOptions.RunContinuationsAsynchronously);
        CancellationTokenSource linked;
        lock (gate)
        {
            if (closing is not null || eventsRequested) throw new RoomProtocolException("closed");
            eventsRequested = true; requests.Add(completed);
            linked = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token, cancellation);
        }
        var socket = new ClientWebSocket();
        try
        {
            socket.Options.SetRequestHeader("Authorization", "Bearer " + admission.Token.Value);
            var uri = new UriBuilder(Address.Endpoint($"v1/rooms/{admission.RoomId}/events")) { Scheme = Address.Origin.Scheme == "https" ? "wss" : "ws" }.Uri;
            linked.CancelAfter(TimeSpan.FromSeconds(20));
            await socket.ConnectAsync(uri, client, linked.Token).ConfigureAwait(false);
            lock (gate)
            {
                linked.Token.ThrowIfCancellationRequested();
                return eventStream = new RoomEventStream(socket);
            }
        }
        catch { socket.Dispose(); throw; }
        finally { linked.Dispose(); lock (gate) requests.Remove(completed); completed.SetResult(); }
    }
    public ValueTask DisposeAsync()
    {
        TaskCompletionSource completion; Task[] pending;
        lock (gate)
        {
            if (closing is not null) return new(closing.Task);
            closing = completion = new(TaskCreationOptions.RunContinuationsAsynchronously);
            pending = requests.Select(p => p.Task).ToArray();
        }
        _ = CloseCoreAsync(pending, completion);
        return new(completion.Task);
    }
    private async Task CloseCoreAsync(Task[] pending, TaskCompletionSource completion)
    {
        try
        {
            await lifetime.CancelAsync(); client.Dispose();
            await Task.WhenAll(pending);
            if (eventStream is not null) await eventStream.DisposeAsync();
            lifetime.Dispose(); completion.SetResult();
        }
        catch (Exception) { completion.SetException(new RoomProtocolException("transport")); }
    }
    private async Task<byte[]> RequestAsync(HttpMethod method, string path, RoomSecret? credential, byte[]? body, CancellationToken cancellation, string? cursor = null)
    {
        cancellation.ThrowIfCancellationRequested();
        TaskCompletionSource completed = new(TaskCreationOptions.RunContinuationsAsynchronously);
        CancellationTokenSource stop;
        lock (gate)
        {
            if (closing is not null) throw new RoomProtocolException("closed");
            stop = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token, cancellation); requests.Add(completed);
        }
        try
        {
            var uri = Address.Endpoint(path);
            if (cursor is not null) uri = new UriBuilder(uri) { Query = "cursor=" + Uri.EscapeDataString(cursor) }.Uri;
            using var request = new HttpRequestMessage(method, uri);
            request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
            if (credential is not null) request.Headers.Authorization = new("Bearer", credential.Value);
            if (body is not null) { request.Content = new ByteArrayContent(body); request.Content.Headers.ContentType = new("application/json"); }
            using var response = await client.SendAsync(request, HttpCompletionOption.ResponseContentRead, stop.Token).ConfigureAwait(false);
            if (response.RequestMessage?.RequestUri != request.RequestUri || response.Content.Headers.ContentType?.MediaType != "application/json") throw new RoomProtocolException("transport");
            byte[] bytes = await response.Content.ReadAsByteArrayAsync(stop.Token).ConfigureAwait(false);
            if (!response.IsSuccessStatusCode)
            {
                using var document = RoomWire.Parse(bytes); var value = document.RootElement;
                RoomWire.Keys(value, "error"); var error = value.GetProperty("error"); RoomWire.Keys(error, "code");
                string code = RoomWire.String(error, "code");
                throw new RoomProtocolException(code is "unauthorized" or "forbidden" or "notFound" or "conflict" or "expired" or "queueFull" or "tlsRequired" or "malformed" or "frameTooLarge" or "internal" or "snapshotRequired" ? code : "transport");
            }
            stop.Token.ThrowIfCancellationRequested(); return bytes;
        }
        finally { stop.Dispose(); lock (gate) requests.Remove(completed); completed.SetResult(); }
    }
}
