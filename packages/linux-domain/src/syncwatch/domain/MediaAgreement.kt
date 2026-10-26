package syncwatch.domain

import java.text.Normalizer
import java.util.Collections

/** Peer-safe catalog facts. Local paths and file permissions remain in the library. */
data class MediaDescriptor(val mediaId: String, val title: String, val titleKey: String,
    val fileSizeBytes: Long, val durationMs: Long?, val fullHashSha256: String?) {
    init {
        PlaybackScope.validateId(mediaId)
        fun text(value: String) = value.codePointCount(0, value.length) in 1..256 &&
            value.codePoints().allMatch { it >= 32 && it != 127 && it !in 0xD800..0xDFFF }
        if (!text(title) || !text(titleKey) || titleKey != normalizedTitleKey(title) ||
            fileSizeBytes !in 1..PlaybackScope.MAXIMUM_GENERATION ||
            (durationMs != null && durationMs !in 0..WatchSession.MAXIMUM_POSITION_MS) ||
            (fullHashSha256 != null && !fullHashSha256.matches(Regex("[0-9a-f]{64}")))) throw WatchFailure("malformed")
    }
    companion object {
        fun normalizedTitleKey(title: String): String = Normalizer.normalize(title, Normalizer.Form.NFC)
            .split(' ').filter { it.isNotEmpty() }.joinToString(" ")
            .map { if (it in 'A'..'Z') it + 32 else it }.joinToString("")
    }
}

enum class MediaAgreementStatus { matched, confirmationRequired, ambiguous, missing }
class MediaAgreement private constructor(val status: MediaAgreementStatus, candidates: List<String>) {
    val candidateIds: List<String> = Collections.unmodifiableList(ArrayList(candidates))
    companion object {
        /** Weak or ambiguous candidates never authorize automatic playback. */
        fun resolve(remote: MediaDescriptor, local: List<MediaDescriptor>): MediaAgreement {
            if (local.size > 256 || local.map { it.mediaId }.toSet().size != local.size) throw WatchFailure("malformed")
            val exact = ArrayList<String>(); val candidates = ArrayList<String>()
            for (candidate in local) {
                val sameHash = remote.fullHashSha256 != null && candidate.fullHashSha256 == remote.fullHashSha256
                if (sameHash) {
                    if (candidate.fileSizeBytes != remote.fileSizeBytes || (candidate.durationMs != null &&
                        remote.durationMs != null && candidate.durationMs != remote.durationMs)) throw WatchFailure("malformed")
                    if (remote.durationMs != null && remote.durationMs > 0 && candidate.durationMs == remote.durationMs) exact.add(candidate.mediaId)
                }
                if (sameHash || candidate.titleKey == remote.titleKey) candidates.add(candidate.mediaId)
            }
            return if (exact.isNotEmpty()) MediaAgreement(if (exact.size == 1) MediaAgreementStatus.matched else MediaAgreementStatus.ambiguous, exact.sorted())
                else MediaAgreement(if (candidates.isEmpty()) MediaAgreementStatus.missing else MediaAgreementStatus.confirmationRequired, candidates.sorted())
        }
    }
}
