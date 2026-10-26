package syncwatch.bridge

import java.nio.file.Files
import java.nio.file.LinkOption.NOFOLLOW_LINKS
import java.nio.file.Path
import java.security.MessageDigest
import java.util.HexFormat
import syncwatch.ipc.Json

/** Local development integrity, not release authentication or an atomic filesystem seal. */
class HelperRuntime private constructor(val packageDirectory: Path, val executable: Path, val revision: String) {
    companion object {
        val expectedRevision: String get() = HelperRuntimePolicy.syncplayRevision
        fun verify(packageDirectory: Path, checkActive: () -> Unit = {}): HelperRuntime {
            checkActive()
            fun invalid(): Nothing = throw IllegalArgumentException("helper-runtime")
            val root = packageDirectory.toAbsolutePath().normalize()
            val receipt = root.resolve("helper-report.json")
            if (System.getProperty("os.name") != "Linux" || !Files.isDirectory(root, NOFOLLOW_LINKS) || Files.isSymbolicLink(root) ||
                !Files.isRegularFile(receipt, NOFOLLOW_LINKS) || Files.size(receipt) > 16 * 1024 * 1024) invalid()
            val report = Json.`object`(Json.parse(Files.readString(receipt)))
            if (report["schemaVersion"] != 1L || report["target"] != "linux-x64" || report["syncplayRevision"] != HelperRuntimePolicy.syncplayRevision ||
                report["developmentHelperOnly"] != true || report["authenticatedInstallation"] != false) invalid()
            val files = Json.`object`(report["files"])
            if (!files.containsKey("bin/syncwatch-helper") || !files.containsKey("app/syncplay-revision.txt")) invalid()
            for ((name, digest) in files) {
                if (name.contains('\\') || name.contains(':') || name.any { it.code < 32 } || name.split('/').any { it.isEmpty() || it == "." || it == ".." } ||
                    digest !is String || !digest.matches(Regex("[0-9a-f]{64}"))) invalid()
            }
            val observed = mutableSetOf<String>()
            val buffer = ByteArray(1024 * 1024)
            Files.walk(root).use { paths -> paths.forEach { file ->
                checkActive()
                if (Files.isSymbolicLink(file)) invalid()
                if (!Files.isDirectory(file, NOFOLLOW_LINKS)) {
                    if (!Files.isRegularFile(file, NOFOLLOW_LINKS)) invalid()
                    val name = root.relativize(file).toString().replace('\\', '/')
                    if (name != "helper-report.json") {
                        if (!observed.add(name) || !files.containsKey(name)) invalid()
                        val hash = MessageDigest.getInstance("SHA-256")
                        Files.newInputStream(file, NOFOLLOW_LINKS).use { input ->
                            while (true) { checkActive(); val read = input.read(buffer); if (read == -1) break; hash.update(buffer, 0, read) }
                        }
                        if (HexFormat.of().formatHex(hash.digest()) != files[name]) invalid()
                    }
                }
            } }
            if (observed != files.keys || !Files.isExecutable(root.resolve("bin/syncwatch-helper")) ||
                Files.readString(root.resolve("app/syncplay-revision.txt")).trim() != HelperRuntimePolicy.syncplayRevision) invalid()
            return HelperRuntime(root, root.resolve("bin/syncwatch-helper"), HelperRuntimePolicy.syncplayRevision)
        }
    }
}
