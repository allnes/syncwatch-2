package syncwatch.domain

import java.nio.file.Files
import java.nio.file.Path
import syncwatch.ipc.Json

internal fun mediaAgreementChecks(directory: Path) {
    val root = Json.`object`(Json.parse(Files.readString(directory.resolve("media-agreement.json"))))
    fun descriptor(value: Any?): MediaDescriptor {
        val p = Json.`object`(value)
        return MediaDescriptor(p["mediaId"] as String, p["title"] as String, p["titleKey"] as String,
            p["fileSizeBytes"] as Long, p["durationMs"] as Long?, p["fullHashSha256"] as String?)
    }
    for (raw in root["normalization"] as List<*>) {
        val p = Json.`object`(raw); check(MediaDescriptor.normalizedTitleKey(p["title"] as String) == p["key"])
    }
    for (raw in root["validation"] as List<*>) {
        val p = Json.`object`(raw); var code: String? = null
        try { descriptor(p["value"]) } catch (error: WatchFailure) { code = error.code }
        check(code == p["error"]) { p["name"].toString() }
    }
    val descriptors = Json.`object`(root["descriptors"])
    for (raw in root["cases"] as List<*>) {
        val p = Json.`object`(raw); var code: String? = null
        try {
            val result = MediaAgreement.resolve(descriptor(descriptors[p["remote"]]),
                (p["local"] as List<*>).map { descriptor(descriptors[it]) })
            check(result.status.name == p["status"] && result.candidateIds == p["candidateIds"]) { p["name"].toString() }
        } catch (error: WatchFailure) { code = error.code }
        check(code == p["error"]) { p["name"].toString() }
    }
    val reference = descriptor(descriptors["remote"])
    try {
        MediaAgreement.resolve(reference, (0..256).map { reference.copy(mediaId = "local-$it") })
        error("Unbounded catalog accepted")
    } catch (failure: WatchFailure) { check(failure.code == "malformed") }
    println("SYNCWATCH_MEDIA_AGREEMENT_OK Unicode, ambiguity, metadata and catalog bounds")
}
