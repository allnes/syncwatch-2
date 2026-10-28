package syncwatch.library

/** Bounded process-local display hints. Never authorizes a selected or shared playback input. */
class LibraryDurationCache(private val capacity: Int = 256) {
    private data class Entry(val file: LocalMediaFile, val duration: Long)
    private val entries = linkedMapOf<String, Entry>()
    init { require(capacity > 0) }
    fun duration(file: LocalMediaFile): Long? = entries[file.id]?.takeIf { it.file == file }?.duration
    fun record(duration: Long?, file: LocalMediaFile) {
        entries.remove(file.id)
        if (duration == null || duration <= 0) return
        entries[file.id] = Entry(file, duration)
        while (entries.size > capacity) entries.remove(entries.keys.first())
    }
    fun reconcile(files: List<LocalMediaFile>) {
        val current = files.associateBy { it.id }
        entries.entries.removeIf { current[it.key] != it.value.file }
    }
    fun clear() = entries.clear()
}
