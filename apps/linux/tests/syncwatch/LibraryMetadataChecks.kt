package syncwatch

import java.nio.file.Files
import java.nio.file.Path
import kotlinx.coroutines.*
import syncwatch.library.*

internal suspend fun libraryMetadataChecks(owner: CoroutineScope) {
    val root = Files.createTempDirectory("syncwatch-metadata-")
    val reader = ControlledMetadata()
    val model = LibraryController(FileLibraryAccessStore(root.resolve("state/access.json")), owner, null, reader)
    try {
        for (name in listOf("A.mkv", "B.mp4")) Files.writeString(root.resolve(name), "fixture")
        model.choose(root); model.settled(); reader.entered(1)
        val revision = model.roomRevision; val last = model.presentation.entries.last().id
        model.select(last)
        model.select(last)
        check(model.presentation.metadataLoading && model.presentation.metadataDurationMs == null && reader.calls == 1)
        val value = MediaMetadata(60_000, 64, 48, 1, 0)
        reader.complete(value); reader.entered(2)
        check(model.presentation.selectedID == last && model.presentation.metadataDurationMs == null)
        reader.fail(); reader.entered(3); reader.complete(value); model.metadataSettled()
        check(model.presentation.entries.first().durationMs == 60_000L && model.presentation.entries.last().durationMs == null)
        check(model.presentation.metadataUnavailable && !model.presentation.metadataLoading && model.errorKey == null)
        check(model.roomRevision == revision && model.selectedMedia()?.media?.id == last)
        model.rescan(); model.settled(); reader.entered(4)
        reader.complete(value); model.metadataSettled(); check(reader.calls == 4)
        check(model.presentation.metadataDurationMs == 60_000L && model.presentation.metadataAudioTracks == 1 &&
            model.presentation.metadataSubtitleTracks == 0 && !model.presentation.metadataUnavailable)
        Files.writeString(root.resolve("A.mkv"), "changed fixture")
        model.rescan(); model.settled(); reader.entered(5); reader.complete(value); reader.entered(6)
        check(model.presentation.entries.first().durationMs == null)
        val closing = owner.launch { model.closeAndWait() }; yield(); check(!reader.closed)
        reader.complete(value); closing.join()
        check(reader.closed && model.selectedMedia() == null && model.presentation.enabledActions.isEmpty())
        realMetadataVlc(root)
        println("SYNCWATCH_LIBRARY_METADATA_OK stale selection, serial input, retry, close and local-only revision")
    } finally {
        reader.abort(); model.closeAndWait()
        Files.walk(root).use { it.sorted(Comparator.reverseOrder()).forEach(Files::delete) }
    }
}
private class ControlledMetadata : syncwatch.library.MediaMetadataReader {
    private val waiting = ArrayDeque<CompletableDeferred<MediaMetadata>>()
    var calls = 0; private set
    var closed = false; private set
    private var aborted = false
    override suspend fun read(file: LocalMediaFile): MediaMetadata {
        calls++; check(!aborted)
        val result = CompletableDeferred<MediaMetadata>(); waiting.addLast(result)
        // Ignore cancellation to exercise rejection of a late native result.
        return withContext(NonCancellable) { result.await() }
    }
    suspend fun entered(count: Int) = withTimeout(2_000) { while (calls < count) delay(5); check(calls == count) }
    fun complete(value: MediaMetadata) { waiting.removeFirst().complete(value) }
    fun fail() { waiting.removeFirst().completeExceptionally(java.io.IOException("unavailable")) }
    fun abort() { aborted = true; while (waiting.isNotEmpty()) fail() }
    override suspend fun close() { closed = true }
}
private suspend fun realMetadataVlc(scratch: Path) {
    val packageDirectory = System.getenv("SYNCWATCH_METADATA_MEDIA") ?: return
    val source = System.getenv("SYNCWATCH_METADATA_FILE") ?: return
    val root = Files.createDirectory(scratch.resolve("real"))
    val clip = root.resolve("Кино movie.avi"); val broken = root.resolve("broken.mkv")
    Files.copy(Path.of(source), clip); Files.writeString(broken, "not a media container")
    val access = LibraryFolderAccess.selected(root)
    val catalog = FileSystemLibrary().scan(root, access.rootId, false)
    val good = catalog.single { it.file == clip }; val invalid = catalog.single { it.file == broken }
    val reader = LibraryMetadataReader(MediaConfiguration(Path.of(packageDirectory), Path.of(System.getenv("SYNCWATCH_METADATA_BRIDGE"))))
    try {
        repeat(2) {
            val value = reader.read(good)
            check(value.durationMs == 60_000L && value.width == 320 && value.height == 180 && value.audioTracks == 1 && value.subtitleTracks == 0)
        }
        check(runCatching { reader.read(invalid) }.isFailure)
        val recovered = reader.read(good); check(recovered.durationMs == 60_000L && recovered.width == 320)
        Files.write(clip, byteArrayOf(0), java.nio.file.StandardOpenOption.APPEND)
        check(runCatching { reader.read(good) }.isFailure)
        Files.delete(clip); check(runCatching { reader.read(good) }.isFailure)
        println("SYNCWATCH_LIBRARY_METADATA_REAL_VLC_OK")
    } finally { reader.close() }
}
