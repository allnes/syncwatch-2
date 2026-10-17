using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace SyncWatch.RoomMetadata;

public sealed class RoomException(string code, int status = 409) : Exception(code)
{
    public string Code { get; } = code;
    public int Status { get; } = status;
}

public sealed record MemberBinding(string MemberId, string ClientRunId, string SyncplayUsername);
public sealed record WatchState(string Status, string? MediaId);
public sealed record RoomSnapshot(int V, string RoomEpoch, long Sequence, long WatchGeneration,
    WatchState Watch, MemberBinding[] Members, string? MeetUri);
public sealed record RoomEvent(int V, string Type, string RoomEpoch, long Sequence, string MemberId,
    string ClientRunId, long WatchGeneration, object Payload);
public sealed record SyncplayBinding(string Host, int Port, string Room, bool RequireTls = true);
public sealed record MediaDescriptor(int V, string MediaId, string Title, string TitleKey, long FileSizeBytes,
    long? DurationMs, [property: JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] string? FullHashSha256);
public sealed record CatalogEntry(string MemberId, MediaDescriptor Media);
public sealed record CatalogPage(int V, string RoomEpoch, long Sequence, CatalogEntry[] Items, string? NextCursor);
public sealed record Bootstrap(RoomSnapshot Snapshot, SyncplayBinding Connection, string CatalogCursor, string[] MissingMembers);
public sealed record Admission(string RoomId, string MemberId, string Token, DateTimeOffset ExpiresAt,
    Bootstrap Bootstrap, string? Invitation = null);
public sealed record Command(string Id, long Number, string Type, string ClientRunId, string RoomEpoch,
    long WatchGeneration, JsonElement Payload, string Digest);
public sealed record CommandResult(int V, string Type, string Id, long Sequence, string? Error);

public static class Wire
{
    public const int MaximumBytes = 65_536;
    public const long MaximumCounter = 9_007_199_254_740_991;
    public static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web)
    {
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
        MaxDepth = 32
    };

    public static void Need(bool condition, string code = "malformed", int status = 400)
    {
        if (!condition) { throw new RoomException(code, status); }
    }

    public static bool Id(string? value) => value is not null && Regex.IsMatch(value, @"\A[A-Za-z0-9][A-Za-z0-9._-]{0,63}\z", RegexOptions.CultureInvariant);
    public static bool Text(string? value, int maximum = 256) => value is not null && value.EnumerateRunes().Count() is > 0
        && value.EnumerateRunes().Count() <= maximum && !value.Any(c => c is < ' ' or '\u007f');
    public static string NewId(string prefix) => prefix + Guid.NewGuid().ToString("N");
    public static string Secret() => Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
    public static byte[] Hash(string value) => SHA256.HashData(Encoding.UTF8.GetBytes(value));
    public static bool SecretMatches(string candidate, byte[] expected) => candidate.Length <= 256
        && CryptographicOperations.FixedTimeEquals(Hash(candidate), expected);

    public static JsonElement Parse(ReadOnlyMemory<byte> bytes)
    {
        Need(bytes.Length <= MaximumBytes, "frameTooLarge", 413);
        try
        {
            using JsonDocument document = JsonDocument.Parse(bytes, new JsonDocumentOptions { MaxDepth = 32 });
            CheckTree(document.RootElement);
            return document.RootElement.Clone();
        }
        catch (JsonException) { throw new RoomException("malformed", 400); }
        catch (InvalidOperationException) { throw new RoomException("malformed", 400); }
    }

    private static void CheckTree(JsonElement value)
    {
        if (value.ValueKind == JsonValueKind.Object)
        {
            HashSet<string> names = [];
            foreach (JsonProperty property in value.EnumerateObject())
            {
                Need(names.Add(property.Name));
                CheckTree(property.Value);
            }
        }
        else if (value.ValueKind == JsonValueKind.Array)
        {
            foreach (JsonElement item in value.EnumerateArray()) { CheckTree(item); }
        }
        else if (value.ValueKind == JsonValueKind.String) { _ = value.GetString(); }
    }

    public static void Fields(JsonElement value, params string[] fields)
    {
        Need(value.ValueKind == JsonValueKind.Object);
        Need(value.EnumerateObject().Select(property => property.Name).ToHashSet(StringComparer.Ordinal).SetEquals(fields));
    }

    public static string String(JsonElement value, string name)
    {
        Need(value.TryGetProperty(name, out JsonElement item) && item.ValueKind == JsonValueKind.String);
        return item.GetString()!;
    }

    public static long Integer(JsonElement value, string name, long maximum = MaximumCounter)
    {
        Need(value.TryGetProperty(name, out JsonElement item) && item.ValueKind == JsonValueKind.Number && item.TryGetInt64(out _));
        long number = item.GetInt64();
        Need(number >= 0 && number <= maximum);
        return number;
    }

    public static bool Boolean(JsonElement value, string name)
    {
        Need(value.TryGetProperty(name, out JsonElement item) && item.ValueKind is JsonValueKind.True or JsonValueKind.False);
        return item.GetBoolean();
    }

    public static void Version(JsonElement value) => Need(Integer(value, "v") == 1, "unsupportedVersion");

    public static MediaDescriptor Media(JsonElement value)
    {
        string[] fields = ["v", "mediaId", "title", "titleKey", "fileSizeBytes", "durationMs"];
        Fields(value, value.TryGetProperty("fullHashSha256", out _) ? [.. fields, "fullHashSha256"] : fields);
        Version(value);
        string id = String(value, "mediaId"), title = String(value, "title"), key = String(value, "titleKey");
        Need(Id(id) && Text(title) && Text(key));
        string normalized = string.Join(' ', title.Normalize(NormalizationForm.FormC).Split(' ', StringSplitOptions.RemoveEmptyEntries));
        normalized = new string(normalized.Select(c => c is >= 'A' and <= 'Z' ? (char)(c + 32) : c).ToArray());
        Need(key == normalized, "invalidState");
        long size = Integer(value, "fileSizeBytes");
        Need(size > 0);
        long? duration = value.GetProperty("durationMs").ValueKind == JsonValueKind.Null ? null : Integer(value, "durationMs", 604_800_000);
        string? hash = value.TryGetProperty("fullHashSha256", out _) ? String(value, "fullHashSha256") : null;
        Need(hash is null || Regex.IsMatch(hash, @"\A[0-9a-f]{64}\z", RegexOptions.CultureInvariant));
        return new(1, id, title, key, size, duration, hash);
    }

    public static Command ReadCommand(ReadOnlyMemory<byte> bytes)
    {
        JsonElement root = Parse(bytes);
        Fields(root, "v", "id", "type", "clientRunId", "roomEpoch", "watchGeneration", "payload");
        Version(root);
        string id = String(root, "id"), run = String(root, "clientRunId"), epoch = String(root, "roomEpoch");
        Need(Regex.IsMatch(id, @"\Acmd-[1-9][0-9]{0,15}\z", RegexOptions.CultureInvariant));
        Need(long.TryParse(id.AsSpan(4), out long number) && number <= MaximumCounter && Id(run) && Id(epoch));
        return new(id, number, String(root, "type"), run, epoch, Integer(root, "watchGeneration"), root.GetProperty("payload"),
            Convert.ToHexString(SHA256.HashData(bytes.Span)));
    }
}
