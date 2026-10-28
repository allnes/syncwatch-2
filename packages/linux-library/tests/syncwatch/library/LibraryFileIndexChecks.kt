package syncwatch.library

import java.nio.file.Files
import java.nio.file.Path
import syncwatch.ipc.Json

@Suppress("UNCHECKED_CAST")
internal fun libraryFileIndexChecks(fixture: Path) {
    val corpus = Json.parse(Files.readString(fixture.resolveSibling("library-companions.json"))) as Map<String, Any?>
    for (item in corpus["cases"] as List<Map<String, Any?>>) {
        val videos = item["videos"] as List<String>
        val audio = item["audio"] as List<String>
        val subtitles = item["subtitles"] as List<String>
        for (reversed in listOf(false, true)) {
            val index = LibraryFileIndex(if (reversed) videos.reversed() else videos,
                if (reversed) audio.reversed() else audio, if (reversed) subtitles.reversed() else subtitles,
                item["caseSensitive"] as Boolean)
            for (expected in item["expected"] as List<Map<String, Any?>>) {
                val video = expected["video"] as String
                check(index.isFolderMovie(video) == expected["folder"]) { item["id"].toString() }
                check(index.audioPaths(video) == expected["audio"]) { item["id"].toString() }
                check(index.subtitlePaths(video) == expected["subtitles"]) { item["id"].toString() }
            }
            val unknown = "not-in-snapshot/" + (videos.firstOrNull()?.substringAfterLast('/') ?: "film.mkv")
            check(!index.isFolderMovie(unknown) && index.audioPaths(unknown).isEmpty() && index.subtitlePaths(unknown).isEmpty())
        }
    }
    for (path in corpus["invalidPaths"] as List<String>)
        check(runCatching { LibraryFileIndex(listOf(path), emptyList(), emptyList(), true) }.exceptionOrNull() is IllegalArgumentException)
}
