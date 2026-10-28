package syncwatch

import java.awt.Component
import java.awt.EventQueue
import java.nio.file.Path
import javax.swing.JFileChooser
import javax.swing.filechooser.FileNameExtensionFilter
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import syncwatch.design.SyncWatchCopy
import syncwatch.design.SyncWatchSelectionMenu
import syncwatch.library.LocalFileAccess


internal interface ExternalTrackChoosing {
    suspend fun choose(kind: String, language: String): LocalFileAccess?
    fun cancel()
}

/** Uses the bundled source-built desktop toolkit; no additional GUI runtime is introduced. */
internal class ExternalTrackPicker(private val owner: () -> Component?) : ExternalTrackChoosing {
    private var active: JFileChooser? = null
    private var activeID: Any? = null
    override suspend fun choose(kind: String, language: String): LocalFileAccess? = suspendCancellableCoroutine { result ->
        val id = Any()
        result.invokeOnCancellation { EventQueue.invokeLater { if (activeID === id) cancel() } }
        EventQueue.invokeLater {
            if (!result.isActive) return@invokeLater
            val filter = SyncWatchSelectionMenu.externalFileFilters.firstOrNull { it.kind == kind }
            if (active != null || filter == null) {
                result.resumeWithException(IllegalStateException("external-picker-unavailable"))
                return@invokeLater
            }
            val picker = JFileChooser()
            picker.dialogTitle = SyncWatchCopy.text(filter.label, language)
            picker.isMultiSelectionEnabled = false
            picker.isAcceptAllFileFilterUsed = false
            picker.fileFilter = FileNameExtensionFilter(picker.dialogTitle, *filter.extensions.toTypedArray())
            active = picker
            activeID = id
            try {
                val accepted = picker.showOpenDialog(owner()) == JFileChooser.APPROVE_OPTION
                if (result.isActive) {
                    val file = if (accepted) picker.selectedFile?.toPath()?.toAbsolutePath()?.normalize() else null
                    result.resume(file?.let { LocalFileAccess.selected(it) })
                }
            } catch (error: Exception) {
                if (result.isActive) result.resumeWithException(error)
            } finally {
                if (active === picker) { active = null; activeID = null }
            }
        }
    }
    override fun cancel() {
        check(EventQueue.isDispatchThread())
        active?.cancelSelection()
    }
}
