// SPDX-License-Identifier: Apache-2.0
package syncwatch.design

/** Configure before creating any Compose scene, including application dialogs. */
object NativeDesignRuntime {
    fun initialize() {
        // The pinned Compose default paints Popup on the parent's canvas. Native
        // video is a heavyweight child above that canvas. Owned platform popup
        // windows preserve the shared layout while crossing that native airspace.
        System.setProperty("compose.layers.type", "WINDOW")
    }
}
