// SPDX-License-Identifier: Apache-2.0
// Offscreen component assertions; desktop input, video and providers have separate acceptance.
package syncwatch.design.tests

import androidx.compose.runtime.Composable
import androidx.compose.ui.ImageComposeScene
import androidx.compose.ui.use
import java.io.ByteArrayInputStream
import java.nio.file.Files
import java.nio.file.Path
import java.security.MessageDigest
import javax.imageio.ImageIO
import javax.swing.SwingUtilities
import syncwatch.design.*
import syncwatch.ipc.Json
import syncwatch.state.CompositionStateOwner
import syncwatch.state.ProvideCompositionState

private fun sha(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

// Foundation savers use lists (for example scroll position + scrolling state).
// This in-process harness permits a bounded primitive/list tree, not arbitrary objects.
private fun saveable(value: Any?, depth: Int = 0): Boolean = depth <= 32 && when (value) {
    null, is String, is Boolean, is Char, is Byte, is Short, is Int, is Long, is Float, is Double -> true
    is List<*> -> value.size <= 1024 && value.all { saveable(it, depth + 1) }
    else -> false
}

fun main(arguments: Array<String>) {
    require(arguments.size == 2) { "Pass the shared fixture directory and image output directory" }
    val fixtures = Path.of(arguments[0])
    val destination = Path.of(arguments[1])
    Files.createDirectories(destination)
    var emitted = 0
    val records = mutableListOf<String>()
    SwingUtilities.invokeAndWait {
        fun render(name: String, width: Int, height: Int, probes: List<Map<String, Any?>> = emptyList(), inkRegions: List<Map<String, Any?>> = emptyList(), content: @Composable () -> Unit) {
            val owner = CompositionStateOwner(canBeSaved = { saveable(it) })
            owner.resume()
            try {
                ImageComposeScene(width, height, content = { ProvideCompositionState(owner, content) }).use { scene ->
                    // Render the frame containing composition and then the frame containing its effects/layout invalidations.
                    scene.render().close()
                    scene.render().use { image ->
                        image.encodeToData().use { data ->
                            val bytes = checkNotNull(data).bytes
                            val bitmap = checkNotNull(ImageIO.read(ByteArrayInputStream(bytes)))
                            check(bitmap.width == width && bitmap.height == height)
                            val colors = hashSetOf<Int>()
                            for (y in 0 until height step 8) for (x in 0 until width step 8) colors += bitmap.getRGB(x, y)
                            // Text-only fixtures may contain just background and ink
                            // on this sampling grid; their positive ink region is checked below.
                            check(colors.size > 2 || inkRegions.any { it["present"] == true }) { "Empty or unrendered component: $name" }
                            for (probe in probes) {
                                val x = (probe["x"] as Number).toInt()
                                val y = (probe["y"] as Number).toInt()
                                val pixel = bitmap.getRGB(x, y)
                                val red = (pixel ushr 16) and 255
                                val green = (pixel ushr 8) and 255
                                val blue = pixel and 255
                                val matches = when (probe["color"]) {
                                    "cyan" -> blue > red + 51
                                    "yellow" -> red > blue + 51
                                    "black" -> red < 3 && green < 3 && blue < 3
                                    else -> error("Unknown shared pixel probe")
                                }
                                check(matches) { "Shared geometry probe failed: $name at $x,$y" }
                            }
                            for (region in inkRegions) {
                                val x = (region["x"] as Number).toInt(); val y = (region["y"] as Number).toInt()
                                val w = (region["width"] as Number).toInt(); val h = (region["height"] as Number).toInt()
                                val found = (y until y+h).any { py -> (x until x+w).any { px ->
                                    val pixel = bitmap.getRGB(px,py)
                                    (pixel and 255) > ((pixel ushr 16) and 255) + 51
                                } }
                                check(found == region["present"]) { "Shared paragraph ink probe failed: $name at $x,$y" }
                            }
                            check(emitted == 0) { "Rendering emitted a user action: $name" }
                            Files.write(destination.resolve("$name.png"), bytes)
                            records += "$name.png\t${sha(bytes)}\t${bitmap.width}\t${bitmap.height}\t${colors.size}"
                        }
                    }
                }
            } finally { owner.close() }
        }
        fun node(record: Map<String, Any?>): DesignNode = DesignNode(
            record["id"] as String, record["kind"] as String,
            Json.`object`(record["props"]).mapValues { it.value as String },
            (record["children"] as List<*>).map { node(Json.`object`(it)) },
        )
        val layoutCases = Json.`object`(Json.parse(Files.readString(fixtures.resolve("layout-probes.json"))))["cases"] as List<*>
        check(layoutCases.size == 6)
        for (item in layoutCases) {
            val fixture = Json.`object`(item)
            val root = node(Json.`object`(fixture["root"]))
            val probes = (fixture["probes"] as List<*>).map { Json.`object`(it) }
            val inkRegions = (fixture["inkRegions"] as? List<*>).orEmpty().map { Json.`object`(it) }
            render("layout-${fixture["name"]}", (fixture["width"] as Number).toInt(), (fixture["height"] as Number).toInt(), probes, inkRegions) {
                DesignNodeSurface(root)
            }
        }
        for ((themeName, theme) in listOf("dark" to SyncWatchTheme.dark, "light" to SyncWatchTheme.light)) {
            for (language in listOf("en", "ru")) {
                for ((width, height) in listOf(1120 to 760, 800 to 600)) {
                    for (state in LibraryVisualState.entries) {
                        val p = LibraryPresentation.gallery(state).let { if (it.entries.isNotEmpty()) it.copy(selectedID = "1") else it }
                        render("${state.name}-$themeName-$language-${width}x$height", width, height) {
                            LibraryWorkspace(p, language, theme) { _, _ -> emitted++ }
                        }
                    }
                    for (state in PlayerVisualState.entries) {
                        render("player${state.name}-$themeName-$language-${width}x$height", width, height) {
                            PlayerChrome(PlayerPresentation.gallery(state), language, theme,
                                videoSurface = { DesignSurface("fixtureVideo", DesignContext(mapOf("fixtureLabel" to "playerFixture")), language, theme) }) { _, _ -> emitted++ }
                        }
                    }
                }
                for (section in SyncWatchSettings.sections) for (state in SettingsVisualState.entries) {
                    render("settings$section${state.name}-$themeName-$language-680x420", 680, 420) {
                        SettingsDialog(SettingsEditor(editableFields = SyncWatchSettings.defaults.keys, canSave = true, state = state),
                            { emitted++ }, language, section, theme)
                    }
                }
                for (section in SyncWatchPlayerSettings.sections) for (state in PlayerSettingsVisualState.entries) {
                    render("playerSettings$section${state.name}-$themeName-$language-680x460", 680, 460) {
                        PlayerSettingsDialog(PlayerSettingsEditor(editableFields = SyncWatchPlayerSettings.defaults.keys, canSave = true, state = state),
                            { emitted++ }, language, section, theme)
                    }
                }
                for (item in SyncWatchCall.galleryCases) for ((width, height) in listOf(300 to 210, 420 to 300)) {
                    render("call${item.id}-$themeName-$language-${width}x$height", width, height) {
                        CallWindowShell(CallPresentation.gallery(item), language, theme,
                            remoteSurface = { DesignSurface("callRemoteFixture", language = language, theme = theme) },
                            localPreview = { DesignSurface("callLocalFixture", language = language, theme = theme) }) { emitted++ }
                    }
                }
                for (kind in SyncWatchSelectionMenu.kinds) for (state in SyncWatchSelectionMenu.states) {
                    render("selection${kind.id}$state-$themeName-$language-420x300", 420, 300) {
                        DesignSurface("selectionFixture", language = language, theme = theme, slots = mapOf("selectionFixtureContent" to {
                            SelectionMenu(SelectionMenuFixtures.presentation(kind.id, state, language), language, theme) { emitted++ }
                        }))
                    }
                }
            }
        }
    }
    Files.write(destination.resolve("images.tsv"), records)
    println("SYNCWATCH_DESIGN_RENDERS_OK: ${records.size} shared-design component images, including shared geometry probes; no emitted actions")
}
