using System.Text.RegularExpressions;

namespace SyncWatch.Room;

public sealed class RoomProtocolException(string code) : IOException(code);

/// <summary>Service origin only. Credentials never occur in a URL.</summary>
public sealed class RoomAddress
{
    public Uri Origin { get; }
    public RoomAddress(string value)
    {
        var syntax = Regex.Match(value, "\\A(https?)://([A-Za-z0-9.-]+|\\[[0-9A-Fa-f:]+\\])(?::[0-9]{1,5})?/?\\z", RegexOptions.CultureInvariant);
        if (!syntax.Success || !Uri.TryCreate(value, UriKind.Absolute, out var uri) || uri.UserInfo.Length != 0
            || uri.Query.Length != 0 || uri.Fragment.Length != 0 || uri.AbsolutePath != "/"
            || string.IsNullOrEmpty(uri.Host) || uri.Port is < 1 or > 65535 || value.Any(c => c <= 32 || c == 127) || value.Contains('\\')
            || !(uri.Scheme == "https" || uri.Scheme == "http" && LiteralLoopback(syntax.Groups[2].Value)))
            throw new RoomProtocolException("invalidRoomService");
        Origin = uri;
    }
    private static bool LiteralLoopback(string host) => host.Trim('[', ']') is "127.0.0.1" or "::1";
    internal Uri Endpoint(string path) => new(Origin, path);
    public override string ToString() => Origin.AbsoluteUri;
}

/// <summary>Memory-only credential; logging this value does not disclose it.</summary>
public sealed class RoomSecret
{
    internal string Value { get; }
    public RoomSecret(string value)
    {
        if (value.Length is < 32 or > 256 || value.Any(c => c < 33 || c > 126))
            throw new RoomProtocolException("invalidRoomCredential");
        Value = value;
    }
    public override string ToString() => "[redacted]";
    // Expose plaintext only for an explicit invitation transfer.
    public string CopyInvitation() => Value;
}
