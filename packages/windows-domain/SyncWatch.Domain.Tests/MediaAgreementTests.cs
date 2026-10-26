using System.Text.Json;
using SyncWatch.Domain;

internal static class MediaAgreementTests
{
    internal static void Run(string directory)
    {
        using var document = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(directory, "media-agreement.json")));
        var root = document.RootElement;
        foreach (var item in root.GetProperty("fileNames").EnumerateArray())
            Require(MediaDescriptor.LogicalTitle(item.GetProperty("filename").GetString()!) == item.GetProperty("title").GetString(), "logical title");
        foreach (var item in root.GetProperty("normalization").EnumerateArray())
            Require(MediaDescriptor.NormalizedTitleKey(item.GetProperty("title").GetString()!) == item.GetProperty("key").GetString(), "title normalization");
        foreach (var fixture in root.GetProperty("validation").EnumerateArray())
        {
            string? code = null;
            try { _ = Descriptor(fixture.GetProperty("value")); }
            catch (ContractException error) { code = error.Rejection.ToString().ToLowerInvariant(); }
            Require(code == fixture.GetProperty("error").GetString(), fixture.GetProperty("name").GetString()!);
        }
        var descriptors = root.GetProperty("descriptors");
        foreach (var fixture in root.GetProperty("cases").EnumerateArray())
        {
            string? code = null;
            try
            {
                var remote = Descriptor(descriptors.GetProperty(fixture.GetProperty("remote").GetString()!));
                var local = fixture.GetProperty("local").EnumerateArray().Select(p => Descriptor(descriptors.GetProperty(p.GetString()!))).ToArray();
                var result = MediaAgreement.Resolve(remote, local);
                Require(string.Equals(result.Status.ToString(), fixture.GetProperty("status").GetString(), StringComparison.OrdinalIgnoreCase)
                    && result.CandidateIds.SequenceEqual(fixture.GetProperty("candidateIds").EnumerateArray().Select(p => p.GetString()!)), fixture.GetProperty("name").GetString()!);
            }
            catch (ContractException error) { code = error.Rejection.ToString().ToLowerInvariant(); }
            Require(code == fixture.GetProperty("error").GetString(), fixture.GetProperty("name").GetString()!);
        }
        var reference = Descriptor(descriptors.GetProperty("remote"));
        try
        {
            MediaAgreement.Resolve(reference, Enumerable.Range(0, 257).Select(i => new MediaDescriptor("local-" + i,
                reference.Title, reference.TitleKey, reference.FileSizeBytes, reference.DurationMs, null)).ToArray());
            throw new InvalidOperationException("Unbounded catalog accepted");
        }
        catch (ContractException error) { Require(error.Rejection == ContractRejection.Malformed, "catalog bound"); }
        Console.WriteLine("Passed shared media agreement, Unicode normalization, ambiguity and catalog bounds");
    }
    private static MediaDescriptor Descriptor(JsonElement p) => new(p.GetProperty("mediaId").GetString()!,
        p.GetProperty("title").GetString()!, p.GetProperty("titleKey").GetString()!, p.GetProperty("fileSizeBytes").GetInt64(),
        p.GetProperty("durationMs").ValueKind == JsonValueKind.Null ? null : p.GetProperty("durationMs").GetInt64(),
        p.GetProperty("fullHashSha256").GetString());
    private static void Require(bool value, string name) { if (!value) throw new InvalidOperationException(name); }
}
