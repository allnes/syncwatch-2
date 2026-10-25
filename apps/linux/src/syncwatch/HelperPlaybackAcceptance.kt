package syncwatch

import kotlinx.coroutines.delay
import kotlinx.coroutines.withTimeout
import syncwatch.bridge.PlayerCorrection
import syncwatch.domain.PlaybackObservation
import syncwatch.domain.PlaybackPort
import syncwatch.domain.PlaybackScope
import syncwatch.domain.PlaybackStatus
import syncwatch.domain.WatchFailure
import syncwatch.ipc.Json

/** Explicit native boundary check; no helper/server connection is established. */
internal object HelperPlaybackAcceptance {
    suspend fun run(player: PlaybackPort, scope: PlaybackScope) {
        val wire = PlaybackScope("helper-run", 7)
        fun command(id: Int, type: String, payload: Map<String, Any>) = PlayerCorrection.decode((Json.write(mapOf(
            "v" to 1L, "id" to "cmd-$id", "type" to type, "clientRunId" to wire.clientRunId,
            "mediaGeneration" to wire.mediaGeneration, "afterUserAction" to 0L, "payload" to payload,
        )) + "\n").toByteArray(Charsets.UTF_8), wire)
        suspend fun until(predicate: (PlaybackObservation) -> Boolean) = withTimeout(3000) {
            while (!predicate(player.observe(scope))) delay(40)
        }
        until { it.status == PlaybackStatus.ready && it.paused && it.seekable }
        val seek = command(1, "player.setPosition", mapOf("positionMs" to 2000L))
        val actual = seek.apply(player, scope, "media-1")
        val result = Json.`object`(Json.parse(seek.result(actual, scope).toString(Charsets.UTF_8)))
        check(result["clientRunId"] == wire.clientRunId && Json.`object`(result["payload"])["positionMs"] == actual.positionMs)
        until { kotlin.math.abs(it.positionMs - 2000) < 200 }
        command(2, "player.setPaused", mapOf("paused" to false)).apply(player, scope, "media-1")
        until { !it.paused }
        command(3, "player.setPaused", mapOf("paused" to true)).apply(player, scope, "media-1")
        until { it.paused }
        command(4, "player.setSpeed", mapOf("rate" to 1.25)).apply(player, scope, "media-1")
        until { kotlin.math.abs(it.rate - 1.25) < .001 }
        val before = player.observe(scope)
        val kept = command(5, "player.openFile", mapOf("mediaHandle" to "media-1")).apply(player, scope, "media-1")
        check(kept.paused && kotlin.math.abs(kept.positionMs - before.positionMs) < 100)
        try { command(6, "player.openFile", mapOf("mediaHandle" to "media-other")).apply(player, scope, "media-1"); error("foreign media accepted") }
        catch (error: WatchFailure) { check(error.code == "unauthorizedHandle") }
    }
}
