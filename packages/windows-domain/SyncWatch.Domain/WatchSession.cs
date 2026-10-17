using System.Collections.Immutable;

namespace SyncWatch.Domain;

public enum WatchRejection { InvalidState, InvalidLocalState, UnsupportedVersion }
public sealed class WatchException(WatchRejection rejection) : Exception(rejection.ToString())
{
    public WatchRejection Rejection { get; } = rejection;
}

public enum WatchPhase { Idle, Selected, Preparing, Active, Ended }
public sealed record WatchLoad(PlaybackScope Scope, string MediaId, long PositionMs);

/// <summary>Local resource work only. Neither effect is a peer playback command.</summary>
public abstract record WatchEffect
{
    public sealed record Load(WatchLoad Request) : WatchEffect;
    public sealed record Release(PlaybackScope Scope) : WatchEffect;
}

/// <summary>Serialize access in the application coordinator. Engine observations remain authoritative.</summary>
public sealed class WatchSession
{
    public const long MaximumPositionMs = 604_800_000;
    public PlaybackScope Scope { get; private set; }
    public WatchPhase Phase { get; private set; }
    public string? MediaId { get; private set; }
    public long PositionMs { get; private set; }
    public bool Paused { get; private set; } = true;
    public bool PlayerPresented { get; private set; }
    public LocalState LocalState { get; private set; }

    public WatchSession(LocalState? localState = null, PlaybackScope? scope = null)
    {
        LocalState = localState ?? LocalState.CreateDefault();
        LocalState.Validate();
        Scope = scope ?? PlaybackScope.Create();
        MediaId = LocalState.SelectedMediaId;
        Phase = MediaId is null ? WatchPhase.Idle : WatchPhase.Selected;
        PositionMs = MediaId is not null ? LocalState.ResumePositionFor(MediaId) : 0;
    }

    public IReadOnlyList<WatchEffect> Select(string mediaId)
    {
        ValidateId(mediaId);
        if (MediaId == mediaId) { return []; }
        PlaybackScope next = Scope.ReplacingMedia();
        IReadOnlyList<WatchEffect> effects = ReleaseEffects();
        Scope = next;
        MediaId = mediaId;
        LocalState = LocalState with { SelectedMediaId = mediaId };
        PositionMs = LocalState.ResumePositionFor(mediaId);
        Phase = WatchPhase.Selected;
        Paused = true;
        PlayerPresented = false;
        return effects;
    }

    public IReadOnlyList<WatchEffect> Start()
    {
        if (MediaId is null) { throw new WatchException(WatchRejection.InvalidState); }
        if (Phase is WatchPhase.Active or WatchPhase.Preparing)
        {
            PlayerPresented = true;
            return [];
        }
        Scope = Scope.ReplacingMedia();
        Phase = WatchPhase.Preparing;
        PlayerPresented = true;
        Paused = true;
        return [new WatchEffect.Load(new WatchLoad(Scope, MediaId, PositionMs))];
    }

    /// <summary>Loading does not authorize playback; readiness is a separate adapter gate.</summary>
    public void Loaded(PlaybackScope owner)
    {
        Check(owner, WatchPhase.Preparing);
        Phase = WatchPhase.Active;
    }

    public void RecordPlayback(PlaybackScope owner, long positionMs, long? durationMs, bool paused)
    {
        Check(owner, WatchPhase.Active);
        if (positionMs is < 0 or > MaximumPositionMs || durationMs is < 0 or > MaximumPositionMs
            || (durationMs.HasValue && positionMs > durationMs.Value))
        {
            throw new WatchException(WatchRejection.InvalidLocalState);
        }
        string mediaId = MediaId!;
        PositionMs = positionMs;
        Paused = paused;
        ImmutableArray<ResumePosition> resumes = LocalState.ResumePositions.RemoveAll(resume => resume.MediaId == mediaId)
            .Add(new ResumePosition { MediaId = mediaId, PositionMs = positionMs });
        if (resumes.Length > 256) { resumes = resumes.RemoveAt(0); }
        LocalState = LocalState with { ResumePositions = resumes };
    }

    public void ReturnToLibrary() => PlayerPresented = false;

    public void ContinueWatching()
    {
        if (Phase is not (WatchPhase.Active or WatchPhase.Preparing))
        {
            throw new WatchException(WatchRejection.InvalidState);
        }
        PlayerPresented = true;
    }

    public IReadOnlyList<WatchEffect> Cancel(PlaybackScope owner)
    {
        Check(owner, WatchPhase.Preparing);
        return End();
    }

    public IReadOnlyList<WatchEffect> End()
    {
        if (Phase is not (WatchPhase.Active or WatchPhase.Preparing)) { return []; }
        PlaybackScope next = Scope.ReplacingMedia();
        IReadOnlyList<WatchEffect> effects = ReleaseEffects();
        Scope = next;
        Phase = WatchPhase.Ended;
        Paused = true;
        PlayerPresented = false;
        return effects;
    }

    public void SetPreferences(LocalPreferences preferences)
    {
        preferences.Validate();
        LocalState = LocalState with { Preferences = preferences };
    }

    private IReadOnlyList<WatchEffect> ReleaseEffects() =>
        Phase is WatchPhase.Active or WatchPhase.Preparing ? [new WatchEffect.Release(Scope)] : [];

    private void Check(PlaybackScope owner, WatchPhase expected)
    {
        Scope.Check(owner.ClientRunId, owner.MediaGeneration);
        if (Phase != expected) { throw new WatchException(WatchRejection.InvalidState); }
    }

    internal static void ValidateId(string identifier) => _ = new PlaybackScope(identifier, 0);
}
