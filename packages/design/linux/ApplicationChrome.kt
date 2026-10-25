// SPDX-License-Identifier: Apache-2.0
package syncwatch.design

import androidx.compose.runtime.Composable

/** Child content uses the shared Library/Player components; owners decide when resources end. */
@Composable fun ApplicationChrome(playerPresented: Boolean, library: @Composable () -> Unit, player: @Composable () -> Unit) {
    DesignSurface("Application", DesignContext(mapOf(
        "libraryPresented" to (!playerPresented).toString(), "playerPresented" to playerPresented.toString(),
    )), slots = mapOf("libraryContent" to { library() }, "playerContent" to { player() }))
}
