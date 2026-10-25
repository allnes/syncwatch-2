package syncwatch.domain

import java.nio.file.Files
import java.nio.file.Path
import syncwatch.ipc.Json

internal fun actionFenceChecks(directory: Path) {
    val corpus = Json.`object`(Json.parse(Files.readString(directory.resolve("playback-authority.json"))))
    val initial = Json.`object`(corpus["scope"])
    val scope = PlaybackScope(initial["clientRunId"] as String, initial["mediaGeneration"] as Long)
    val cases = corpus["cases"] as List<*>
    check(cases.size == 5)
    for (raw in cases) {
        val fixture = Json.`object`(raw)
        val fence = PlaybackActionFence(scope)
        for (item in fixture["steps"] as List<*>) {
            val step = Json.`object`(item)
            val owner = PlaybackScope(step["ownerRunId"] as? String ?: scope.clientRunId,
                step["ownerGeneration"] as? Long ?: scope.mediaGeneration)
            val before = Triple(fence.issuedSequence, fence.publishedSequence, fence.invalidated)
            var result = ""; var errorCode: String? = null
            try {
                when (step["op"]) {
                    "begin" -> result = fence.beginUserAction(owner).toString()
                    "canPublish" -> result = fence.canPublish(step["sequence"] as Long, owner).toString()
                    "publish" -> {
                        val status = if (step["status"] == "loading") PlaybackStatus.loading else PlaybackStatus.ready
                        val observation = PlaybackObservation(owner, 0u, status, 0,
                            if (status == PlaybackStatus.ready) 4000 else null, true, 1.0,
                            status == PlaybackStatus.ready, false, false, 0, 0, 0, null, false)
                        result = fence.didPublish(step["sequence"] as Long, observation).toString()
                    }
                    "correction" -> result = fence.correction(owner, step["afterUserAction"] as Long).name
                    "invalidate" -> fence.invalidate()
                    else -> error("Unknown authority fixture")
                }
            } catch (error: WatchFailure) { errorCode = error.code }
            check(errorCode == step["error"]) { "${fixture["name"]} $step: $errorCode" }
            if (errorCode == null) check(result == (step["result"] ?: ""))
            else check(before == Triple(fence.issuedSequence, fence.publishedSequence, fence.invalidated))
        }
    }
    println("SYNCWATCH_NATIVE_ACTION_ORDERING_OK")
}
