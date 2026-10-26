using System.Text;
using System.Text.RegularExpressions;

namespace SyncWatch.Domain;

/// <summary>Peer-safe catalog facts, with no path or filesystem permission.</summary>
public sealed record MediaDescriptor
{
    public string MediaId { get; }
    public string Title { get; }
    public string TitleKey { get; }
    public long FileSizeBytes { get; }
    public long? DurationMs { get; }
    public string? FullHashSha256 { get; }

    public MediaDescriptor(string mediaId, string title, string titleKey, long fileSizeBytes, long? durationMs, string? fullHashSha256)
    {
        _ = new PlaybackScope(mediaId, 0);
        if (!Text(title) || !Text(titleKey) || titleKey != NormalizedTitleKey(title)
            || fileSizeBytes is < 1 or > (long)PlaybackScope.MaximumGeneration
            || durationMs is < 0 or > WatchSession.MaximumPositionMs
            || (fullHashSha256 is not null && !Regex.IsMatch(fullHashSha256, "\\A[0-9a-f]{64}\\z", RegexOptions.CultureInvariant)))
            throw new ContractException(ContractRejection.Malformed);
        MediaId = mediaId; Title = title; TitleKey = titleKey; FileSizeBytes = fileSizeBytes;
        DurationMs = durationMs; FullHashSha256 = fullHashSha256;
    }

    private static bool Text(string value)
    {
        try { _ = new UTF8Encoding(false, true).GetByteCount(value); }
        catch (EncoderFallbackException) { return false; }
        return value.EnumerateRunes().Count() is >= 1 and <= 256 && !value.Any(c => c < 32 || c == 127);
    }

    public static string LogicalTitle(string filename)
    {
        string value = filename.Normalize(NormalizationForm.FormC); int dot = value.LastIndexOf('.');
        return dot > 0 ? value[..dot] : value;
    }
    public static string NormalizedTitleKey(string title) => new(string.Join(' ',
        title.Normalize(NormalizationForm.FormC).Split(' ', StringSplitOptions.RemoveEmptyEntries))
        .Select(c => c is >= 'A' and <= 'Z' ? (char)(c + 32) : c).ToArray());
}

public enum MediaAgreementStatus { Matched, ConfirmationRequired, Ambiguous, Missing }

public sealed record MediaAgreement
{
    public MediaAgreementStatus Status { get; }
    public IReadOnlyList<string> CandidateIds { get; }
    private MediaAgreement(MediaAgreementStatus status, IReadOnlyList<string> candidateIds) { Status = status; CandidateIds = candidateIds; }
    /// <summary>Weak or ambiguous candidates cannot authorize automatic playback.</summary>
    public static MediaAgreement Resolve(MediaDescriptor remote, IReadOnlyList<MediaDescriptor> local)
    {
        if (local.Count > 256 || local.Select(p => p.MediaId).Distinct(StringComparer.Ordinal).Count() != local.Count)
            throw new ContractException(ContractRejection.Malformed);
        List<string> exact = [], candidates = [];
        foreach (var candidate in local)
        {
            bool sameHash = remote.FullHashSha256 is not null && candidate.FullHashSha256 == remote.FullHashSha256;
            if (sameHash)
            {
                if (candidate.FileSizeBytes != remote.FileSizeBytes || (candidate.DurationMs is not null
                    && remote.DurationMs is not null && candidate.DurationMs != remote.DurationMs))
                    throw new ContractException(ContractRejection.Malformed);
                if (remote.DurationMs is > 0 && candidate.DurationMs == remote.DurationMs) exact.Add(candidate.MediaId);
            }
            if (sameHash || candidate.TitleKey == remote.TitleKey) candidates.Add(candidate.MediaId);
        }
        exact.Sort(StringComparer.Ordinal); candidates.Sort(StringComparer.Ordinal);
        return exact.Count > 0
            ? new(exact.Count == 1 ? MediaAgreementStatus.Matched : MediaAgreementStatus.Ambiguous, exact.AsReadOnly())
            : new(candidates.Count == 0 ? MediaAgreementStatus.Missing : MediaAgreementStatus.ConfirmationRequired, candidates.AsReadOnly());
    }
}
