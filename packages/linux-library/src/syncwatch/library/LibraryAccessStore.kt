package syncwatch.library

import java.nio.ByteBuffer
import java.nio.channels.FileChannel
import java.nio.charset.CodingErrorAction
import java.nio.charset.StandardCharsets.UTF_8
import java.nio.file.Files
import java.nio.file.NoSuchFileException
import java.nio.file.Path
import java.nio.file.StandardCopyOption.ATOMIC_MOVE
import java.nio.file.StandardCopyOption.REPLACE_EXISTING
import java.nio.file.StandardOpenOption.WRITE
import syncwatch.ipc.Json

data class LibraryAccessRecord(val rootId: String, val rootPath: String,
    val scanSubfolders: Boolean = true, val autoRefresh: Boolean = true,
    val version: Int = 1, val platform: String = "linux", val bookmark: String? = null) {
    fun validate() {
        require(version == 1 && platform == "linux" && bookmark == null
            && java.util.UUID.fromString(rootId).toString() == rootId
            && !rootPath.contains('\u0000') && Path.of(rootPath).isAbsolute) { "library-access-record" }
    }
}
enum class LibraryAccessStatus { missing, loaded, invalid, unsupportedVersion }
data class LibraryAccessRead(val status: LibraryAccessStatus, val record: LibraryAccessRecord? = null)

/** The caller chooses an application-owned file and serializes calls outside rendering. */
interface LibraryAccessStore {
    fun read(): LibraryAccessRead
    fun write(record: LibraryAccessRecord)
}

class FileLibraryAccessStore(path: Path) : LibraryAccessStore {
    val path: Path = path.toAbsolutePath().normalize()
    override fun read(): LibraryAccessRead {
        val bytes = try { Files.newInputStream(path).use { it.readNBytes(MAXIMUM_BYTES + 1) } }
            catch (_: NoSuchFileException) { return LibraryAccessRead(LibraryAccessStatus.missing) }
        if (bytes.size > MAXIMUM_BYTES) return LibraryAccessRead(LibraryAccessStatus.invalid)
        return try {
            val text = UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString()
            val root = Json.`object`(Json.parse(text))
            val version = root["version"] as? Long ?: errorRecord()
            if (version !in 0..Int.MAX_VALUE.toLong()) return LibraryAccessRead(LibraryAccessStatus.invalid)
            if (version != 1L) return LibraryAccessRead(LibraryAccessStatus.unsupportedVersion)
            require(root.keys == keys)
            val record = LibraryAccessRecord(root["rootId"] as? String ?: errorRecord(),
                root["rootPath"] as? String ?: errorRecord(), root["scanSubfolders"] as? Boolean ?: errorRecord(),
                root["autoRefresh"] as? Boolean ?: errorRecord(), platform = root["platform"] as? String ?: errorRecord(),
                bookmark = root["bookmark"]?.let { it as? String ?: errorRecord() })
            record.validate(); LibraryAccessRead(LibraryAccessStatus.loaded, record)
        } catch (_: IllegalArgumentException) { LibraryAccessRead(LibraryAccessStatus.invalid) }
          catch (_: java.nio.charset.CharacterCodingException) { LibraryAccessRead(LibraryAccessStatus.invalid) }
    }
    override fun write(record: LibraryAccessRecord) {
        record.validate()
        require(read().status != LibraryAccessStatus.unsupportedVersion) { "unsupported-library-version" }
        val bytes = Json.write(mapOf("version" to record.version, "platform" to record.platform,
            "rootId" to record.rootId, "rootPath" to record.rootPath, "bookmark" to record.bookmark,
            "scanSubfolders" to record.scanSubfolders, "autoRefresh" to record.autoRefresh)).toByteArray(UTF_8)
        require(bytes.size <= MAXIMUM_BYTES)
        Files.createDirectories(path.parent)
        val temporary = Files.createTempFile(path.parent, ".library-access-", ".tmp")
        try {
            FileChannel.open(temporary, WRITE).use { output ->
                val buffer = ByteBuffer.wrap(bytes)
                while (buffer.hasRemaining()) output.write(buffer)
                output.force(true)
            }
            Files.move(temporary, path, ATOMIC_MOVE, REPLACE_EXISTING)
        } finally { Files.deleteIfExists(temporary) }
    }
    companion object {
        const val MAXIMUM_BYTES = 262144
        private val keys = setOf("version", "platform", "rootId", "rootPath", "bookmark", "scanSubfolders", "autoRefresh")
        private fun errorRecord(): Nothing = throw IllegalArgumentException("library-access-record")
    }
}
