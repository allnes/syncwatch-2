package syncwatch.library

/** Relationships in one completed authorized listing; paths stay local and root-relative. */
class LibraryFileIndex(videos: List<String>, audio: List<String>, subtitles: List<String>,
    private val caseSensitive: Boolean) {
    private fun key(value: String): String = if (caseSensitive) value else value.lowercase()
    private val videoPaths = videos.toSet()
    private val videoCounts: Map<String, Int>
    private val extraDirectories: Set<String>
    private val audioIndex: Map<String, List<String>>
    private val subtitleIndex: Map<String, List<String>>
    init {
        for (path in videos + audio + subtitles)
            require(path.isNotEmpty() && !path.startsWith('/') && '\u0000' !in path &&
                path.split('/').all { it.isNotEmpty() && it != "." && it != ".." }) { "library-relative-path" }
        videoCounts = videos.groupingBy { key(directory(it)) }.eachCount()
        val stems = videos.map { stem(it) }.toSet()
        extraDirectories = (audio + subtitles).flatMap {
            val folder = directory(it)
            if (folder.isEmpty()) listOf("") else listOf(key(folder), key(directory(folder)))
        }.toSet()
        fun index(paths: List<String>): Map<String, List<String>> {
            val result = HashMap<String, MutableList<String>>()
            fun compare(a: String, b: String) = java.util.Arrays.compareUnsigned(a.toByteArray(Charsets.UTF_8), b.toByteArray(Charsets.UTF_8))
            for (path in paths.sortedWith { a, b -> compare(name(a), name(b)).takeIf { it != 0 } ?: compare(a, b) }) {
                val file = name(path)
                for (dot in file.indices.filter { file[it] == '.' }) {
                    val prefix = key(file.substring(0, dot))
                    if (prefix in stems) result.getOrPut(prefix) { ArrayList() }.add(path)
                }
            }
            return result.mapValues { java.util.Collections.unmodifiableList(it.value) }
        }
        audioIndex = index(audio)
        subtitleIndex = index(subtitles)
    }
    fun isFolderMovie(video: String): Boolean {
        if (video !in videoPaths) return false
        val folder = key(directory(video))
        return videoCounts[folder] == 1 && folder in extraDirectories
    }
    fun audioPaths(video: String): List<String> = if (video in videoPaths) audioIndex[stem(video)] ?: emptyList() else emptyList()
    fun subtitlePaths(video: String): List<String> = if (video in videoPaths) subtitleIndex[stem(video)] ?: emptyList() else emptyList()
    private fun stem(path: String): String = key(name(path).let { it.substringBeforeLast('.', it) })
    private companion object {
        fun name(path: String): String = path.substringAfterLast('/')
        fun directory(path: String): String = path.substringBeforeLast('/', "")
    }
}
