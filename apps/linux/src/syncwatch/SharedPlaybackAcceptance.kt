package syncwatch

import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import syncwatch.bridge.*
import syncwatch.domain.*
import syncwatch.ipc.Json

/** Explicit authored-fixture check. Commands use the normal player controller and
 * exported state comes from VLC. It makes no manual/physical acceptance claim. */
internal object SharedPlaybackAcceptance {
    suspend fun run(controller: PlaybackController, configuration: Path, close: () -> Unit) {
        val config = Json.`object`(Json.parse(Files.readString(configuration)))
        fun text(key: String) = config[key] as String
        val runtime = Path.of(text("runtime")); val executable = Path.of(text("executable"))
        val control = Path.of(text("control")); val output = Path.of(text("state"))
        val endpoint = SyncplayEndpoint(text("host"), Math.toIntExact(config["port"] as Long), text("room"), text("username"))
        val expires = System.nanoTime() + 900_000_000_000
        var actual: PlaybackObservation
        do {
            actual = controller.player.observe(controller.scope)
            check(System.nanoTime() < expires)
            if (actual.status != PlaybackStatus.ready || !actual.seekable) delay(40)
        } while (actual.status != PlaybackStatus.ready || !actual.seekable)
        val descriptor = controller.prepareSharedMedia()
        val expected = Json.`object`(config["expectedMedia"])
        val remote = MediaDescriptor(expected["mediaId"] as String, expected["title"] as String, expected["titleKey"] as String,
            expected["fileSizeBytes"] as Long, expected["durationMs"] as Long?, expected["fullHashSha256"] as String?)
        check(MediaAgreement.resolve(remote, listOf(descriptor)).status == MediaAgreementStatus.matched) { "media-agreement-required" }
        val duration = checkNotNull(descriptor.durationMs)
        val revision = Files.readString(runtime.resolve("app/syncplay-revision.txt")).trim()
        val transport = withContext(Dispatchers.IO) { HelperProcess.start(executable, runtime) }
        controller.connectShared(transport, endpoint, SharedMedia(descriptor.mediaId, remote.title, duration, descriptor.fileSizeBytes), revision)
        var sequence = 0L
        while (System.nanoTime() < expires) {
            controller.sharedState?.let { shared ->
                check(shared.connection != HelperConnection.failed)
                val value = controller.player.observe(controller.scope)
                val state = mapOf("connection" to shared.connection.name, "ready" to shared.ready,
                    "acceptedUsername" to (shared.acceptedUsername ?: ""), "participants" to shared.participants.map { it.username },
                    "positionMs" to value.positionMs, "paused" to value.paused, "rate" to value.rate,
                    "sequence" to value.sequence.toLong(), "controlSequence" to sequence, "guiObserved" to false, "physicalOutputAccepted" to false,
                    "mediaId" to descriptor.mediaId, "fullHashSha256" to descriptor.fullHashSha256,
                    "localTitle" to descriptor.title, "sharedTitle" to remote.title, "agreedMediaId" to remote.mediaId,
                    "fileSizeBytes" to descriptor.fileSizeBytes, "durationMs" to duration)
                val temporary = output.resolveSibling(output.fileName.toString() + ".tmp")
                Files.writeString(temporary, Json.write(state)); Files.move(temporary, output, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE)
            }
            if (Files.exists(control)) {
                val instruction = Json.`object`(Json.parse(Files.readString(control)))
                val next = instruction["sequence"] as Long
                if (next > sequence) {
                    check(next == sequence + 1); val action = instruction["action"] as String
                    if (action == "finish") return
                    check(action in setOf("playPause", "seek", "setMovieVolume", "muteMovie"))
                    controller.action(action, (instruction["value"] as? Number)?.toDouble(), close, {})
                    sequence = next
                }
            }
            delay(100)
        }
        error("shared playback check timeout")
    }
}
