namespace SyncWatch.Domain;

public enum CorrectionDisposition { Apply, WaitForUserObservation, Cancelled, Unavailable }

/// <summary>Native ordering only. The owner sends actual user state before marking it published.</summary>
public sealed class PlaybackActionFence(PlaybackScope scope)
{
    public PlaybackScope Scope { get; } = scope;
    public ulong IssuedSequence { get; private set; }
    public ulong PublishedSequence { get; private set; }
    public bool Invalidated { get; private set; }

    public ulong BeginUserAction(PlaybackScope owner)
    {
        Check(owner);
        if (IssuedSequence == PlaybackScope.MaximumGeneration) throw new ContractException(ContractRejection.Malformed);
        return ++IssuedSequence;
    }
    // Recheck on the serialized writer immediately before emitting a user frame.
    public bool CanPublish(ulong sequence, PlaybackScope owner)
    {
        Check(owner);
        if (sequence == 0 || sequence > IssuedSequence) throw new ContractException(ContractRejection.Malformed);
        return sequence > PublishedSequence;
    }
    public bool DidPublish(ulong sequence, PlaybackObservation observation)
    {
        observation.Validate();
        if (!CanPublish(sequence, observation.Scope)) return false;
        if (observation.Status != PlaybackStatus.Ready) throw new WatchException(WatchRejection.InvalidState);
        PublishedSequence = sequence; return true;
    }
    // Check before queuing a correction and after its native await. Cancellation
    // must follow the newer actual user frame, not merely the local request.
    public CorrectionDisposition Correction(PlaybackScope owner, ulong afterUserAction)
    {
        Scope.Check(owner.ClientRunId, owner.MediaGeneration);
        if (Invalidated) return CorrectionDisposition.Unavailable;
        if (afterUserAction > PublishedSequence) throw new ContractException(ContractRejection.Malformed);
        if (afterUserAction < PublishedSequence) return CorrectionDisposition.Cancelled;
        return IssuedSequence == PublishedSequence ? CorrectionDisposition.Apply : CorrectionDisposition.WaitForUserObservation;
    }
    public void Invalidate() => Invalidated = true;
    private void Check(PlaybackScope owner)
    {
        Scope.Check(owner.ClientRunId, owner.MediaGeneration);
        if (Invalidated) throw new WatchException(WatchRejection.InvalidState);
    }
}
