# SyncWatch Design

Apache-2.0, platform-neutral declarative components for SyncWatch. `layouts.json` is the source of screen composition, responsive rules, typography, visual variants and primitive-control appearance. Tokens, localized copy and field/action metadata are separate data sources in this package.

The generator validates the document and compiles the same node tree into Swift, C# and Kotlin data. Platform adapters implement primitive rendering, native input and accessibility. Presentation bindings supply observations, collections, capabilities and event handlers; they do not specify screen layout or visual values. Native-owned video surfaces are explicit leaf slots.

See the [design architecture](../../docs/architecture/design-system.md) and [build commands](../../docs/design-generator.md). The Kotlin adapter includes shared presentation and offscreen render assertions. Its registered application build still requires complete dependency, native, font and runtime qualification. The design package starts no media, synchronization, browser or device service.

The selection-menu component has focused model, binding and gallery files in each platform directory. `selection-menu.json` declares supported kinds, request scopes and input bounds; the common layout declares menu geometry and appearance. A correlated selection request carries source identity and revision, without changing the observed selection. Playlist requests describe shared movie selection; audio and subtitle requests stay local. Routing and provider acknowledgement belong to the application coordinator.
