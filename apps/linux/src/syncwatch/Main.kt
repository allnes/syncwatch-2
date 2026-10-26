package syncwatch

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.runtime.*
import kotlinx.coroutines.launch
import androidx.compose.ui.unit.dp
import androidx.compose.ui.input.key.*
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
    val media = MediaConfiguration.read(arguments)
    val gallery = arguments.any { it in setOf("--selection-menu-gallery", "--call-gallery", "--player-settings-gallery",
        "--player-gallery", "--settings-gallery", "--design-gallery") }
    // XInitThreads must precede the first toolkit, including the normal Library's folder picker.
    // A missing runtime leaves playback unavailable for this run; it never grants a later unsafe attach.
    val display = when {
        launch != null -> launch.initializeDisplay()
        !gallery -> media.availableDisplay()
        else -> null
    }
    application {
        val scope = rememberCoroutineScope()
        val playback = remember(launch) { launch?.let { PlaybackController(it, requireNotNull(display), scope) } }
        val workspace = remember {
            if (launch == null && !gallery) {
                val index = arguments.indexOf("--state-directory")
                val path = arguments.getOrNull(index + 1)?.takeIf { index >= 0 }
                    ?.let { Path.of(it).toAbsolutePath().normalize().resolve("local-state.json") }
                    ?: AppearancePreferences.defaultPath()
                ApplicationSession(media, display, scope, path)
            } else null
        }
        val state = rememberWindowState(width = SyncWatchTokens.layoutGalleryWidth.dp, height = SyncWatchTokens.layoutGalleryHeight.dp)
        val close = { exitApplication() }
        Window(onCloseRequest = {
            if (playback != null) playback.requestClose(close)
            else if (workspace != null) workspace.requestClose(close) else close()
        }, title = "SyncWatch", state = state, onKeyEvent = { event ->
            if (event.type == KeyEventType.KeyUp && event.key == Key.Escape && state.placement == WindowPlacement.Fullscreen) {
                state.placement = WindowPlacement.Floating; true
            } else false
        }) {
            if (playback != null || workspace != null) NativePlayerWindowBounds(window)
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
                workspace != null -> ApplicationWorkspace(workspace, arguments, { workspace.requestClose(close) }) {
                    state.placement = if (state.placement == WindowPlacement.Fullscreen) WindowPlacement.Floating else WindowPlacement.Fullscreen
                }
            }
            if (playback != null && launch?.report != null) {
                LaunchedEffect(playback) {
                    PlaybackAcceptance.run(playback, window, state, launch.report, launch.detachProbe, close)
                }
            }
        }
    }
}

@Composable private fun ApplicationWorkspace(workspace: ApplicationSession, arguments: Array<String>, onClose: () -> Unit, onFullscreen: () -> Unit) {
    val preferences = workspace.preferences
    val state = preferences.state
    val watch = workspace.watch
    val room = workspace.room
    val roomWork = rememberCoroutineScope()
    var roomOpen by remember { mutableStateOf(false) }
    var settingsOpen by remember { mutableStateOf(false) }
    var editor by remember { mutableStateOf(preferences.editor()) }
    val library = workspace.library
    LaunchedEffect(workspace) {
        library.restore(); watch.prepareRuntime()
        WatchAcceptance.run(arguments, workspace, onClose)
    }
    DisposableEffect(library) { onDispose { library.close() } }
    val language = state.preferences.language
    val dark = when (state.preferences.theme) { "dark" -> true; "light" -> false; else -> isSystemInDarkTheme() }
    val theme = if (dark) SyncWatchTheme.dark else SyncWatchTheme.light
    ApplicationChrome(watch.playerPresented, library = {
    LibraryWorkspace(room.libraryPresentation(watch.libraryPresentation(library.presentation)), language, theme) { action, value ->
        if (action == "chooseFolder") {
            val picker = javax.swing.JFileChooser().apply {
                fileSelectionMode = javax.swing.JFileChooser.DIRECTORIES_ONLY
                isMultiSelectionEnabled = false
                dialogTitle = SyncWatchCopy.text("folder", language)
                approveButtonText = SyncWatchCopy.text("chooseFolder", language)
            }
            if (picker.showOpenDialog(null) == javax.swing.JFileChooser.APPROVE_OPTION) library.choose(picker.selectedFile.toPath())
        } else if (action == "rescan") library.rescan()
        else if (action == "selectMovie" && value != null) library.select(value)
        else if (action == "startWatching") library.selectedMedia()?.let(watch::start)
        else if (action == "continueWatching") watch.continueWatching()
        else if (action == "endWatching") watch.end()
        else if (action == "openRoom") roomOpen = true
        else if (action == "openSettings") { editor = preferences.editor(); settingsOpen = true }
    }
    }, player = {
        watch.player?.let { controller -> key(controller.scope.clientRunId, controller.scope.mediaGeneration) {
            PlaybackPane(controller, language, theme, onClose, onFullscreen)
        } }
    })
    LaunchedEffect(library.errorKey, watch.errorKey) {
        if (WatchAcceptance.requested(arguments)) return@LaunchedEffect
        (library.errorKey ?: watch.errorKey)?.let { key ->
            javax.swing.JOptionPane.showMessageDialog(null, SyncWatchCopy.text(key, language), SyncWatchCopy.text("brand", language), javax.swing.JOptionPane.WARNING_MESSAGE)
            library.clearError(); watch.clearError()
        }
    }
    if (roomOpen) {
        fun closeDialog() { if (room.editor.busy) roomWork.launch { room.close(); roomOpen = false } else { room.editor = room.editor.clearSecrets(); roomOpen = false } }
        DialogWindow(onCloseRequest = ::closeDialog, title = SyncWatchCopy.text("openRoom", language),
            state = rememberDialogState(width = SyncWatchTokens.layoutSettingsWidth.dp, height = SyncWatchTokens.layoutSettingsHeight.dp)) {
            RoomDialog(room.editor, { room.editor = it }, language, theme) { action -> when (action) {
                "connectRoom" -> room.connect()
                "leaveRoom" -> roomWork.launch { room.close() }
                "pasteInvitation" -> room.pasteInvitation(runCatching {
                    java.awt.Toolkit.getDefaultToolkit().systemClipboard.getData(java.awt.datatransfer.DataFlavor.stringFlavor) as? String
                }.getOrNull() ?: "")
                "copyInvitation" -> room.invitationToCopy()?.let { value -> java.awt.Toolkit.getDefaultToolkit().systemClipboard.setContents(java.awt.datatransfer.StringSelection(value), null); room.invitationCopied() }
                "close" -> closeDialog()
            } }
        }
    }
    if (settingsOpen) {
        DialogWindow(onCloseRequest = { settingsOpen = false }, title = SyncWatchCopy.text("openSettings", language),
            state = rememberDialogState(width = SyncWatchTokens.layoutSettingsWidth.dp, height = SyncWatchTokens.layoutSettingsHeight.dp)) {
            SettingsDialog(editor, { editor = it }, language = language, theme = theme,
                onSave = { values -> preferences.save(values).also { if (it) watch.preferencesChanged() } },
                onClose = { settingsOpen = false })
        }
    }
}

/** Only local appearance facts are enabled. Provider capabilities require their own observed owners. */
internal class AppearancePreferences(store: LocalStateStore) {
    private val store = SerializedLocalStateStore(store)
    var state by mutableStateOf(LocalState())
        private set
    var savingWatchState by mutableStateOf(false)
        private set
    private var canWrite = false
    init {
        try {
            val loaded = this.store.read()
            when (loaded.status) {
                LocalStateStatus.loaded -> { state = loaded.state!!; canWrite = true }
                LocalStateStatus.missing, LocalStateStatus.invalid -> canWrite = true
                LocalStateStatus.unsupportedVersion -> Unit
            }
        } catch (_: java.io.IOException) { }
    }
    fun editor() = SettingsEditor(values = mapOf("theme" to state.preferences.theme, "language" to state.preferences.language),
        editableFields = if (canWrite && !savingWatchState) setOf("theme", "language") else emptySet(), canSave = canWrite && !savingWatchState)
    fun save(values: Map<String, String>): Boolean {
        if (!canWrite || savingWatchState) return false
        val theme = values["theme"] ?: return false; val language = values["language"] ?: return false
        val next = state.copy(preferences = state.preferences.copy(theme = theme, language = language))
        return try { next.validate(); store.write(next); state = next; true }
        catch (_: java.io.IOException) { false }
        catch (_: WatchFailure) { false }
    }
    suspend fun persistWatchState(value: LocalState): Boolean {
        if (savingWatchState) return false
        val next = value.copy(preferences = state.preferences)
        try { next.validate() } catch (_: WatchFailure) { return false }
        state = next
        if (!canWrite) return false
        savingWatchState = true
        return try {
            kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) { store.write(next) }
            true
        } catch (_: java.io.IOException) { false }
        catch (_: WatchFailure) { false }
        finally { savingWatchState = false }
    }
    companion object {
        fun defaultPath(): Path {
            val directory = System.getenv("XDG_STATE_HOME")?.takeIf { Path.of(it).isAbsolute }
                ?.let(Path::of) ?: Path.of(System.getProperty("user.home"), ".local", "state")
            return directory.resolve("SyncWatch/local-state.json")
        }
    }
}
