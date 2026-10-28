package syncwatch.library

internal fun mediaMetadataChecks() {
    val names = mutableListOf("English", "Русский")
    val value = MediaMetadata(1000, 320, 180, 2, 0, names, emptyList())
    names[0] = "Changed"
    check(value.audioTrackNames == listOf("English", "Русский") && value.subtitleTrackNames == emptyList<String>())
    val equal = MediaMetadata(1000, 320, 180, 2, 0, listOf("English", "Русский"), emptyList())
    check(value == equal && value.hashCode() == equal.hashCode())
    check(MediaMetadata(null, 0, 0, 2, 0).audioTrackNames == null)
    for (invalid in listOf(emptyList(), listOf("English", "Русский"), listOf("bad\u0000label"), listOf("é".repeat(2049)))) {
        check(runCatching { MediaMetadata(null, 0, 0, 1, 0, invalid, emptyList()) }.isFailure)
    }
    check(runCatching { MediaMetadata(null, 0, 0, 0, 1, emptyList(), emptyList()) }.isFailure)
    check(MediaMetadata(null, 0, 0, 1, 0, listOf("é".repeat(2048)), emptyList()).audioTrackNames!!.single().length == 2048)
    @Suppress("UNCHECKED_CAST")
    val exposed = value.audioTrackNames as MutableList<String>
    check(runCatching { exposed[0] = "Changed" }.isFailure)
}
