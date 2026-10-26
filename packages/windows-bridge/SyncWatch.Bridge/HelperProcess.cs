using System.Diagnostics;
using System.Text;

namespace SyncWatch.Bridge;

/// <summary>Owns a single helper and its inherited pipes. It does not interpret playback.</summary>
public sealed class HelperProcess : IHelperTransport
{
    private const int MaximumFrameBytes = 65536; // contracts/manifest.json, including LF
    private static readonly UTF8Encoding StrictUtf8 = new(false, true);
    private readonly Process process;
    private readonly SemaphoreSlim reader = new(1);
    private readonly SemaphoreSlim writer = new(1);
    private readonly byte[] buffer = new byte[4096];
    private int start;
    private int end;
    private int disposed;
    private readonly Task diagnostics;

    private HelperProcess(Process process)
    {
        this.process = process;
        diagnostics = DrainAsync(process.StandardError.BaseStream);
    }

    public int ProcessId => process.Id;

    public static HelperProcess Start(string executable, string runtime)
    {
        if (!Path.IsPathFullyQualified(executable) || !Path.IsPathFullyQualified(runtime))
            throw new ArgumentException("Verified absolute helper paths are required");
        ProcessStartInfo options = new(executable)
        {
            UseShellExecute = false,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
            WorkingDirectory = runtime
        };
        options.ArgumentList.Add(runtime);
        foreach (string key in options.Environment.Keys.ToArray())
            if (key.StartsWith("PYTHON", StringComparison.OrdinalIgnoreCase)) options.Environment.Remove(key);
        return new HelperProcess(Process.Start(options) ?? throw new IOException("Helper could not start"));
    }

    private static async Task DrainAsync(Stream stream)
    {
        byte[] discard = new byte[1024];
        try { while (await stream.ReadAsync(discard).ConfigureAwait(false) != 0) { } }
        catch (IOException) { }
    }

    public async Task SendAsync(ReadOnlyMemory<byte> frame, CancellationToken cancellation = default)
    {
        Validate(frame.Span);
        if (!await writer.WaitAsync(0, cancellation).ConfigureAwait(false)) throw new IOException("queueFull");
        try
        {
            ObjectDisposedException.ThrowIf(Volatile.Read(ref disposed) != 0, this);
            await process.StandardInput.BaseStream.WriteAsync(frame, cancellation).ConfigureAwait(false);
            await process.StandardInput.BaseStream.FlushAsync(cancellation).ConfigureAwait(false);
        }
        catch { Kill(); throw; }
        finally { writer.Release(); }
    }

    public async Task<byte[]> ReadAsync(CancellationToken cancellation = default)
    {
        if (!await reader.WaitAsync(0, cancellation).ConfigureAwait(false)) throw new IOException("queueFull");
        try
        {
            ObjectDisposedException.ThrowIf(Volatile.Read(ref disposed) != 0, this);
            using MemoryStream frame = new();
            while (true)
            {
                if (start == end)
                {
                    end = await process.StandardOutput.BaseStream.ReadAsync(buffer, cancellation).ConfigureAwait(false);
                    start = 0;
                    if (end == 0) throw new EndOfStreamException("Helper stopped");
                }
                byte value = buffer[start++];
                frame.WriteByte(value);
                if (frame.Length > MaximumFrameBytes) throw new IOException("frameTooLarge");
                if (value == 10)
                {
                    byte[] result = frame.ToArray();
                    Validate(result);
                    return result;
                }
            }
        }
        catch { Kill(); throw; }
        finally { reader.Release(); }
    }

    private static void Validate(ReadOnlySpan<byte> frame)
    {
        if (frame.Length is < 2 or > MaximumFrameBytes || frame[^1] != 10
            || frame[..^1].Contains((byte)10) || frame.Contains((byte)13)) throw new IOException("malformed");
        _ = StrictUtf8.GetCharCount(frame);
    }

    private void Kill()
    {
        try { if (!process.HasExited) process.Kill(entireProcessTree: true); }
        catch (InvalidOperationException) { }
    }

    public async ValueTask DisposeAsync()
    {
        if (Interlocked.Exchange(ref disposed, 1) != 0) return;
        process.StandardInput.Close();
        using CancellationTokenSource deadline = new(TimeSpan.FromSeconds(3));
        try { await process.WaitForExitAsync(deadline.Token).ConfigureAwait(false); }
        catch (OperationCanceledException) { Kill(); await process.WaitForExitAsync().ConfigureAwait(false); }
        await diagnostics.ConfigureAwait(false);
        process.Dispose();
    }
}
