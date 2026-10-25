import SwiftUI

/// Compose the common library and player components without coupling presentation to resource lifetime.
public struct ApplicationChrome: View {
    public var playerPresented: Bool
    public var library: AnyView
    public var player: AnyView
    public init(playerPresented: Bool, library: AnyView, player: AnyView) {
        self.playerPresented = playerPresented
        self.library = library
        self.player = player
    }
    public var body: some View {
        DesignSurface(
            "Application",
            context: DesignContext([
                "libraryPresented": String(!playerPresented), "playerPresented": String(playerPresented),
            ]), slots: ["libraryContent": library, "playerContent": player])
    }
}
