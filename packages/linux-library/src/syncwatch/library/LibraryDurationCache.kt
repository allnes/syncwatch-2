package syncwatch.library

/** Bounded process-local display hints. Never authorizes a selected or shared playback input. */
class LibraryDurationCache(private val capacity: Int = 256) {
    private data class Version(val path: java.nio.file.Path, val size: Long, val modified: java.nio.file.attribute.FileTime) {
        constructor(file: LocalMediaFile) : this(file.file, file.sizeBytes, file.modificationTime)
    }
    private data class Entry(val version: Version, val duration: Long)
    private val entries = linkedMapOf<String, Entry>()
    init { require(capacity > 0) }
    fun duration(file: LocalMediaFile): Long? = entries[file.id]?.takeIf { it.version == Version(file) }?.duration
    fun record(duration: Long?, file: LocalMediaFile) {
        entries.remove(file.id)
        if (duration == null || duration <= 0) return
        entries[file.id] = Entry(Version(file), duration)
        while (entries.size > capacity) entries.remove(entries.keys.first())
    }
    fun reconcile(files: List<LocalMediaFile>) {
        val current = files.associate { it.id to Version(it) }
        entries.entries.removeIf { current[it.key] != it.value.version }
    }
    fun clear() = entries.clear()
}
