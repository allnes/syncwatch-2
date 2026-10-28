package syncwatch.library

internal fun mediaMetadataChecks() {
    val a = LocalMediaFile("a", "a", "a", java.nio.file.Path.of("/movies/a"), 1, java.nio.file.attribute.FileTime.fromMillis(10))
    val b = a.copy(id = "b", title = "b"); val c = a.copy(id = "c", title = "c")
    val cache = LibraryDurationCache(2)
    cache.record(60_000, a); cache.record(90_000, b); cache.record(120_000, c)
    check(cache.duration(a) == null && cache.duration(b) == 90_000L)
    check(cache.duration(b.copy(sizeBytes = 2)) == null)
    cache.reconcile(listOf(b.copy(sizeBytes = 2), c)); check(cache.duration(b) == null && cache.duration(c) == 120_000L)
    cache.reconcile(listOf(b)); check(cache.duration(c) == null)
    cache.record(60_000, b); cache.record(null, b); check(cache.duration(b) == null)
    cache.record(0, b); check(cache.duration(b) == null)
    cache.record(60_000, b); cache.clear(); check(cache.duration(b) == null)
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
