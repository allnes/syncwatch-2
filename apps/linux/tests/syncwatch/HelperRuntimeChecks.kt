package syncwatch

import java.nio.file.Files
import java.nio.file.Path
import java.security.MessageDigest
import java.util.HexFormat
import kotlinx.coroutines.CancellationException
import syncwatch.bridge.HelperRuntime
import syncwatch.ipc.Json

internal fun helperRuntimeChecks() {
    val temporary = Files.createTempDirectory("sw-helper-integrity-")
    try {
        for (name in listOf("valid", "wrongTarget", "wrongPin", "wrongRevisionFile", "changedFile", "extraFile", "missingFile", "pathEscape", "entrySymlink")) {
            val root = temporary.resolve(name)
            Files.createDirectories(root.resolve("bin")); Files.createDirectories(root.resolve("app"))
            val executable = root.resolve("bin/syncwatch-helper")
            Files.writeString(executable, "owned test stub; never executed"); check(executable.toFile().setExecutable(true, true))
            Files.writeString(root.resolve("app/syncplay-revision.txt"), (if (name == "wrongRevisionFile") "0".repeat(40) else HelperRuntime.expectedRevision) + "\n")
            val files = mutableMapOf<String, String>()
            for (relative in listOf("bin/syncwatch-helper", "app/syncplay-revision.txt"))
                files[relative] = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(root.resolve(relative))))
            if (name == "pathEscape") files["../outside"] = "a".repeat(64)
            val report = mapOf("schemaVersion" to 1L, "target" to if (name == "wrongTarget") "windows-x64" else "linux-x64",
                "syncplayRevision" to if (name == "wrongPin") "0".repeat(40) else HelperRuntime.expectedRevision,
                "developmentHelperOnly" to true, "authenticatedInstallation" to false, "files" to files)
            Files.writeString(root.resolve("helper-report.json"), Json.write(report))
            if (name == "changedFile") Files.writeString(executable, "changed")
            if (name == "extraFile") Files.writeString(root.resolve("extra"), "")
            if (name == "missingFile") Files.delete(executable)
            if (name == "entrySymlink") Files.createSymbolicLink(root.resolve("link"), executable)
            val result = runCatching { HelperRuntime.verify(root); HelperRuntime.verify(root) }
            check(result.isSuccess == (name == "valid")) { "helper integrity: $name" }
        }
        check(runCatching { HelperRuntime.verify(temporary.resolve("valid")) { throw CancellationException() } }.exceptionOrNull() is CancellationException)
        System.getenv("SYNCWATCH_VERIFY_HELPER_PACKAGE")?.let { HelperRuntime.verify(Path.of(it)) }
        System.getenv("SYNCWATCH_REJECT_HELPER_PACKAGE")?.let { check(runCatching { HelperRuntime.verify(Path.of(it)) }.isFailure) }
        println("SYNCWATCH_HELPER_RUNTIME_OK integrity/pins/membership/cancellation")
    } finally { Files.walk(temporary).use { paths -> paths.sorted(Comparator.reverseOrder()).forEach(Files::delete) } }
}
