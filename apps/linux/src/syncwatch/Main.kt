package syncwatch

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.runtime.*
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.DialogWindow
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import androidx.compose.ui.window.rememberWindowState
import androidx.compose.ui.window.rememberDialogState
import androidx.compose.ui.window.WindowPlacement
import java.nio.file.Path
import syncwatch.design.*
import syncwatch.domain.*

/** Desktop entry point. Composition, text, dimensions and appearance come from SyncWatch Design.
 * Runtime distribution and visible desktop/provider acceptance remain required.
 */
fun main(arguments: Array<String>) {
    val launch = LocalPlaybackLaunch.read(arguments)
    val display = launch?.initializeDisplay()
    application {
        val scope = rememberCoroutineScope()
        val playback = remember(launch) { launch?.let { PlaybackController(it, requireNotNull(display), scope) } }
        val state = rememberWindowState(width = SyncWatchTokens.layoutGalleryWidth.dp, height = SyncWatchTokens.layoutGalleryHeight.dp)
        val close = { exitApplication() }
        Window(onCloseRequest = { if (playback != null) playback.requestClose(close) else close() }, title = "SyncWatch", state = state) {
            if (playback != null) NativePlayerWindowBounds(window)
            when {
                playback != null -> PlaybackWorkspace(playback, close) {
                    state.placement = if (state.placement == WindowPlacement.Fullscreen) WindowPlacement.Floating else WindowPlacement.Fullscreen
                }
                "--selection-menu-gallery" in arguments -> SelectionMenuGallery()
                "--call-gallery" in arguments -> CallGallery()
                "--player-settings-gallery" in arguments -> PlayerSettingsGallery()
                "--player-gallery" in arguments -> PlayerGallery()
                "--settings-gallery" in arguments -> SettingsGallery()
                "--design-gallery" in arguments -> DesignGallery()
                else -> ApplicationWorkspace()
            }
            if (playback != null && launch?.report != null) {
                LaunchedEffect(playback) {
                    PlaybackAcceptance.run(playback, window, state, launch.report, launch.detachProbe, close)
                }
            }
        }
    }
}

@Composable private fun ApplicationWorkspace() {
    val preferences = remember { AppearancePreferences(FileLocalStateStore(AppearancePreferences.defaultPath())) }
    var state by remember { mutableStateOf(preferences.state) }
    var settingsOpen by remember { mutableStateOf(false) }
    var editor by remember { mutableStateOf(preferences.editor()) }
    val language = state.preferences.language
    val dark = when (state.preferences.theme) { "dark" -> true; "light" -> false; else -> isSystemInDarkTheme() }
    val theme = if (dark) SyncWatchTheme.dark else SyncWatchTheme.light
    LibraryWorkspace(LibraryPresentation(enabledActions = setOf("openSettings")), language, theme) { action, _ ->
        if (action == "openSettings") { editor = preferences.editor(); settingsOpen = true }
    }
    if (settingsOpen) {
        DialogWindow(onCloseRequest = { settingsOpen = false }, title = SyncWatchCopy.text("openSettings", language),
            state = rememberDialogState(width = SyncWatchTokens.layoutSettingsWidth.dp, height = SyncWatchTokens.layoutSettingsHeight.dp)) {
            SettingsDialog(editor, { editor = it }, language = language, theme = theme,
                onSave = { values -> preferences.save(values).also { if (it) state = preferences.state } },
                onClose = { settingsOpen = false })
        }
    }
}

/** Only local appearance facts are enabled. Provider capabilities require their own observed owners. */
internal class AppearancePreferences(private val store: LocalStateStore) {
    var state = LocalState()
        private set
    private var canWrite = false
    init {
        try {
            val loaded = store.read()
            when (loaded.status) {
                LocalStateStatus.loaded -> { state = loaded.state!!; canWrite = true }
                LocalStateStatus.missing, LocalStateStatus.invalid -> canWrite = true
                LocalStateStatus.unsupportedVersion -> Unit
            }
        } catch (_: java.io.IOException) { }
    }
    fun editor() = SettingsEditor(values = mapOf("theme" to state.preferences.theme, "language" to state.preferences.language),
        editableFields = if (canWrite) setOf("theme", "language") else emptySet(), canSave = canWrite)
    fun save(values: Map<String, String>): Boolean {
        if (!canWrite) return false
        val theme = values["theme"] ?: return false; val language = values["language"] ?: return false
        val next = state.copy(preferences = state.preferences.copy(theme = theme, language = language))
        return try { next.validate(); store.write(next); state = next; true }
        catch (_: java.io.IOException) { false }
        catch (_: WatchFailure) { false }
    }
    companion object {
        fun defaultPath(): Path {
            val directory = System.getenv("XDG_STATE_HOME")?.takeIf { Path.of(it).isAbsolute }
                ?.let(Path::of) ?: Path.of(System.getProperty("user.home"), ".local", "state")
            return directory.resolve("SyncWatch/local-state.json")
        }
    }
}
