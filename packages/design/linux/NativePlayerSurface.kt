package syncwatch.design

import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.awt.SwingPanel
import androidx.compose.ui.graphics.awt.toAwtColor
import java.awt.Component
import java.awt.Dimension
import java.awt.Window
import java.awt.event.WindowAdapter
import java.awt.event.WindowEvent

/** Apply content minimums after native decorations have reported their insets. */
@Composable fun NativePlayerWindowBounds(window: Window) {
    DisposableEffect(window) {
        fun applyBounds() {
            val insets = window.insets
            window.minimumSize = Dimension(SyncWatchTokens.layoutMinimumWidth.toInt() + insets.left + insets.right,
                SyncWatchTokens.layoutMinimumHeight.toInt() + insets.top + insets.bottom)
        }
        val listener = object : WindowAdapter() {
            override fun windowOpened(event: WindowEvent) = applyBounds()
        }
        window.addWindowListener(listener)
        applyBounds()
        onDispose { window.removeWindowListener(listener) }
    }
}

/** Native content only; the shared Player layout owns its slot and surrounding controls. */
@OptIn(ExperimentalComposeUiApi::class)
@Composable fun NativePlayerSurface(component: Component) {
    val background = rgba(SyncWatchTokens.colorSharedVideoSurface)
    val presented = LocalDesignPresented.current
    SwingPanel(factory = { component.apply { this.background = background.toAwtColor() } },
        modifier = Modifier.fillMaxSize(), update = {
            it.background = background.toAwtColor()
            it.isVisible = presented
        })
}
