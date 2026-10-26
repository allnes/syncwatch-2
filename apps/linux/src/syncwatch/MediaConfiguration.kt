package syncwatch

import java.nio.file.Files
import java.nio.file.Path
import syncwatch.playback.VLCPlayback
import syncwatch.playback.X11Display

/** Runtime locations are local application configuration, never peer-provided paths. */
internal data class MediaConfiguration(val packageDirectory: Path, val bridge: Path) {
    /** Call before any AWT/Compose toolkit. The playback adapter verifies the complete package. */
    fun initializeDisplay(): X11Display = VLCPlayback.initializeDisplay(bridge, packageDirectory)

    fun availableDisplay(): X11Display? = try { initializeDisplay() }
        catch (_: java.io.IOException) { null }
        catch (_: RuntimeException) { null }
        catch (_: LinkageError) { null }

    companion object {
        internal fun applicationDirectory(): Path {
            val location = Path.of(MediaConfiguration::class.java.protectionDomain.codeSource.location.toURI())
            return if (Files.isDirectory(location)) location else location.parent
        }
        fun read(arguments: Array<String>, directory: Path = applicationDirectory()): MediaConfiguration {
            fun value(flag: String): Path? = arguments.indexOf(flag).takeIf { it >= 0 }
                ?.let { arguments.getOrNull(it + 1) }?.let(Path::of)
            return MediaConfiguration((value("--media-package") ?: directory.resolve("Media")).toAbsolutePath().normalize(),
                (value("--playback-bridge") ?: directory.resolve("syncwatch_playback_jni.so")).toAbsolutePath().normalize())
        }
    }
}
