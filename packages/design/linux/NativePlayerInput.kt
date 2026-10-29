// SPDX-License-Identifier: Apache-2.0
package syncwatch.design

import androidx.compose.runtime.*
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.awt.ComposeWindow
import androidx.compose.ui.awt.LocalAwtWindow
import androidx.compose.ui.window.WindowPlacement
import java.awt.*
import java.awt.event.*
import javax.swing.*
import javax.swing.text.JTextComponent

/** Post-processing preserves native control input; only the mounted, focused player can issue requests. */
@OptIn(ExperimentalComposeUiApi::class)
@Composable internal fun NativePlayerInput(presentation: PlayerPresentation, protectedFocus: Boolean, onAction: (String, Double?) -> Unit) {
    val owner = LocalAwtWindow.current ?: return
    val current by rememberUpdatedState(presentation)
    val inputProtected by rememberUpdatedState(protectedFocus || !LocalDesignPresented.current)
    val dispatch by rememberUpdatedState(onAction)
    DisposableEffect(owner) {
        val manager = KeyboardFocusManager.getCurrentKeyboardFocusManager()
        val held = mutableSetOf<Int>()
        fun owns(component: Component?) = component != null && SwingUtilities.getWindowAncestor(component) === owner && owner.isFocused
        val keys = KeyEventPostProcessor { event ->
            if (event.id == KeyEvent.KEY_RELEASED) { held.remove(event.keyCode); false }
            else if (event.id != KeyEvent.KEY_PRESSED || event.isConsumed || !owns(event.component)) false
            else {
                val repeating = !held.add(event.keyCode)
                val key = when (event.keyCode) {
                    KeyEvent.VK_SPACE -> "Space"; KeyEvent.VK_LEFT -> "ArrowLeft"; KeyEvent.VK_RIGHT -> "ArrowRight"
                    KeyEvent.VK_UP -> "ArrowUp"; KeyEvent.VK_DOWN -> "ArrowDown"; KeyEvent.VK_M -> "KeyM"
                    KeyEvent.VK_F -> "KeyF"; KeyEvent.VK_ESCAPE -> "Escape"; else -> ""
                }
                val focus = manager.focusOwner
                val editing = focus is JTextComponent || focus is JSlider || focus is JComboBox<*>
                    || key == "Space" && focus is AbstractButton
                val consumed = current.dispatchKey(key, repeating, (owner as? ComposeWindow)?.placement == WindowPlacement.Fullscreen,
                    event.isAltDown || event.isControlDown || event.isShiftDown || event.isMetaDown, inputProtected || editing, dispatch)
                if (consumed) event.consume()
                consumed
            }
        }
        val wheel = AWTEventListener { event ->
            if (event is MouseWheelEvent && !event.isConsumed && owns(event.component)) {
                if (current.dispatchWheel(-event.preciseWheelRotation,
                    event.isAltDown || event.isControlDown || event.isShiftDown || event.isMetaDown, inputProtected, dispatch)) event.consume()
            }
        }
        val focus = object : WindowAdapter() { override fun windowLostFocus(event: WindowEvent) { held.clear() } }
        manager.addKeyEventPostProcessor(keys); owner.addWindowFocusListener(focus)
        Toolkit.getDefaultToolkit().addAWTEventListener(wheel, AWTEvent.MOUSE_WHEEL_EVENT_MASK)
        onDispose {
            manager.removeKeyEventPostProcessor(keys); owner.removeWindowFocusListener(focus)
            Toolkit.getDefaultToolkit().removeAWTEventListener(wheel); held.clear()
        }
    }
}
