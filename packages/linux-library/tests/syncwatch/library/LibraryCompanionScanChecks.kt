package syncwatch.library

import java.nio.file.Files
import java.nio.file.Path
import syncwatch.ipc.Json

@Suppress("UNCHECKED_CAST")
internal suspend fun libraryCompanionScanChecks(fixture: Path) {
    val corpus = Json.parse(Files.readString(fixture.resolveSibling("library-companion-scan.json"))) as Map<String, Any?>
    val root = Files.createTempDirectory("syncwatch-companions-")
    try {
        for (name in corpus["files"] as List<String>) {
            val path = root.resolve(name)
            Files.createDirectories(path.parent); Files.writeString(path, name)
        }
        Files.createSymbolicLink(root.resolve("Movie.Part.1.link.srt"), root.resolve("Movie.Part.1.en.srt"))
        val scanner = FileSystemLibrary(mapOf("srt" to LibraryCompanionKind.subtitles, "wav" to LibraryCompanionKind.audio))
        val id = corpus["rootId"] as String
        val files = scanner.scan(root, id, true)
        val insensitive = Files.exists(root.resolve("mOvIe.PaRt.1.mkv"))
        val expectedByPath = corpus["expected"] as Map<String, List<String>>
        for (file in files) {
            val expected = (expectedByPath[file.relativePath] ?: emptyList()).toMutableList()
            if (insensitive && file.title == "Movie.Part.1.mkv") expected.add(corpus["insensitiveExtra"] as String)
            check(file.companions.map { it.relativePath } == expected) { file.relativePath }
            if (file.relativePath in corpus["folderMovies"] as List<String>) check(file.folderMovie)
            if (file.relativePath in corpus["notFolderMovies"] as List<String>) check(!file.folderMovie)
            check(file.companions.all { it.id != file.id && it.sizeBytes > 0 })
        }
        val movie = files.single { it.relativePath == "Movie.Part.1.mkv" }
        val subtitle = movie.companions.first { it.kind == LibraryCompanionKind.subtitles }
        check(subtitle.open().file == subtitle.file)
        Files.writeString(subtitle.file, "changed")
        check(runCatching { subtitle.open() }.isFailure)
        val next = scanner.scan(root, id, true).single { it.id == movie.id }.companions.single { it.id == subtitle.id }
        check(next.sizeBytes == 7L && next != subtitle)
        Files.delete(next.file); check(runCatching { next.open() }.isFailure)
        val flat = scanner.scan(root, id, false)
        check(flat.size == 1 && flat.single().companions.isEmpty() && !flat.single().folderMovie)
    } finally { root.toFile().deleteRecursively(); check(!Files.exists(root)) }
}
