package syncwatch.bridge

import java.nio.file.Files
import java.nio.file.Path
import syncwatch.domain.PlaybackObservation
import syncwatch.domain.PlaybackScope
import syncwatch.domain.PlaybackStatus
import syncwatch.domain.WatchFailure
import syncwatch.ipc.Json

/** The shared wire corpus also runs in the production JVM consumer lane. */
fun main(arguments: Array<String>) {
    helperCommandChecks(Path.of(arguments.single()).parent.resolve("helper-commands.json"))
    helperReplyChecks(Path.of(arguments.single()).parent.resolve("helper-replies.json"))
    val corpus = Json.`object`(Json.parse(Files.readString(Path.of(arguments.single()))))
    val cases = corpus["cases"] as List<*>
    check(cases.size == 49)
    val scope = PlaybackScope("helper-run", 7)
    for (raw in cases) {
        val fixture = Json.`object`(raw)
        val bytes = if (fixture.containsKey("hex")) byteArrayOf(-1, 10) else (fixture["frame"] as String).toByteArray(Charsets.UTF_8)
        var accepted = false
        try {
            val command = PlayerCorrection.decode(bytes, scope)
            check(command.id == "cmd-9" && command.afterUserAction == if (fixture["name"] == "legacy-zero-watermark") 0L else 3L)
            accepted = true
        } catch (_: IllegalArgumentException) { }
        catch (_: java.nio.charset.CharacterCodingException) { }
        check(accepted == fixture["accepted"]) { fixture["name"].toString() }
    }
    val first = cases.map { Json.`object`(it) }.first { it["name"] == "player.setPosition" }
    val command = PlayerCorrection.decode((first["frame"] as String).toByteArray(Charsets.UTF_8), scope)
    val native = PlaybackScope("native-owner", 2)
    val actual = PlaybackObservation(native, 9u, PlaybackStatus.ready, 1300, 4000, true, 1.0, true, false, false, 0, 0, 0, null, false)
    val result = Json.`object`(Json.parse(command.result(actual, native).toString(Charsets.UTF_8)))
    check(result["clientRunId"] == scope.clientRunId && result["replyTo"] == "cmd-9" && Json.`object`(result["payload"])["positionMs"] == 1300L)
    try { command.result(actual, scope); error("foreign observation accepted") } catch (_: WatchFailure) { }
    println("SYNCWATCH_HELPER_PLAYER_OK 49 frames; actual result and independent native ownership")
}
