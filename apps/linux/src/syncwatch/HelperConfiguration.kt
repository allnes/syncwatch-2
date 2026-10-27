package syncwatch

import java.nio.file.Path
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import syncwatch.bridge.HelperRuntime

/** Local installation configuration. Room metadata never supplies executable or runtime paths. */
internal data class HelperConfiguration(val packageDirectory: Path) {
    suspend fun verify(): HelperRuntime = withContext(Dispatchers.IO) {
        val context = currentCoroutineContext()
        context.ensureActive()
        val runtime = HelperRuntime.verify(packageDirectory) { context.ensureActive() }
        context.ensureActive()
        runtime
    }
    companion object {
        fun read(arguments: Array<String>, directory: Path = MediaConfiguration.applicationDirectory()): HelperConfiguration {
            val packageDirectory = arguments.indexOf("--helper-package").takeIf { it >= 0 }?.let { arguments.getOrNull(it + 1) }?.let(Path::of)
                ?: directory.resolve("Syncplay")
            return HelperConfiguration(packageDirectory.toAbsolutePath().normalize())
        }
    }
}
