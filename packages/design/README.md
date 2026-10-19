# SyncWatch Design

Apache-2.0, platform-neutral declarative components for SyncWatch. `layouts.json` is the source of screen composition, responsive rules, typography, visual variants and primitive-control appearance. Tokens, localized copy and field/action metadata are separate data sources in this package.

The generator validates the document and compiles the same node tree into Swift, C# and Kotlin data. Platform adapters implement primitive rendering, native input and accessibility. Presentation bindings supply observations, collections, capabilities and event handlers; they do not specify screen layout or visual values. Native-owned video surfaces are explicit leaf slots.

See the [design architecture](../../docs/architecture/design-system.md) and [build commands](../../docs/design-generator.md). The Kotlin adapter is source-only until its dependency/compiler/native/font/license build is available. The design package starts no media, synchronization, browser or device service.
