using System.Net.WebSockets;
using System.Threading.Channels;

namespace SyncWatch.Room;

/// <summary>Bounded single-consumer stream. Decode each message before applying it.</summary>
public sealed class RoomEventStream : IAsyncDisposable
{
    private readonly ClientWebSocket socket;
    private readonly CancellationTokenSource stop = new();
    private readonly Channel<byte[]> messages = Channel.CreateBounded<byte[]>(new BoundedChannelOptions(32)
    { SingleReader = true, SingleWriter = true, FullMode = BoundedChannelFullMode.Wait });
    private readonly Task pump;
    private readonly object gate = new();
    private Task? closing;
    private int receiving;
    internal RoomEventStream(ClientWebSocket socket) { this.socket = socket; pump = PumpAsync(); }
    public async Task<byte[]> ReceiveAsync(CancellationToken cancellation = default)
    {
        if (Interlocked.CompareExchange(ref receiving, 1, 0) != 0) throw new RoomProtocolException("malformed");
        try { return await messages.Reader.ReadAsync(cancellation).ConfigureAwait(false); }
        finally { Volatile.Write(ref receiving, 0); }
    }
    public ValueTask DisposeAsync()
    {
        lock (gate) { return new(closing ??= CloseCoreAsync()); }
    }
    private async Task CloseCoreAsync()
    {
        await stop.CancelAsync(); socket.Abort();
        await pump.ConfigureAwait(false); socket.Dispose(); stop.Dispose();
        while (messages.Reader.TryRead(out _)) { }
    }
    private async Task PumpAsync()
    {
        Exception failure = new RoomProtocolException("closed");
        try
        {
            byte[] buffer = new byte[RoomWire.MaximumBytes];
            while (!stop.IsCancellationRequested)
            {
                int size = 0; ValueWebSocketReceiveResult result;
                do
                {
                    // Include an extra receive for an empty final fragment at the exact limit.
                    Memory<byte> remaining = size < buffer.Length ? buffer.AsMemory(size) : new byte[1];
                    result = await socket.ReceiveAsync(remaining, stop.Token).ConfigureAwait(false);
                    if (result.MessageType != WebSocketMessageType.Text) throw new RoomProtocolException("malformed");
                    if (result.Count > buffer.Length - size) throw new RoomProtocolException("frameTooLarge");
                    size += result.Count;
                } while (!result.EndOfMessage);
                byte[] bytes = buffer[..size]; using (RoomWire.Parse(bytes)) { }
                if (!messages.Writer.TryWrite(bytes)) throw new RoomProtocolException("queueFull");
            }
        }
        catch (RoomProtocolException error) { failure = error; }
        catch (Exception) { failure = new RoomProtocolException("transport"); }
        finally { messages.Writer.TryComplete(failure); socket.Abort(); }
    }
}
