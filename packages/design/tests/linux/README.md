# Linux design assertions

`PresentationChecks.kt` executes the shared `../fixtures` corpus against the Kotlin design presentations. It checks player and call requests, observed-state ownership, stale menu contexts, local and shared selection routing, invalid values, library capabilities, and settings persistence acknowledgements.

Compile it in the same Kotlin module as the Linux design and generated design sources, with the application IPC JSON boundary. Pass the fixture directory to `syncwatch.design.tests.PresentationChecksKt`.

These assertions exercise presentation behavior. They do not qualify component rendering, native input, a desktop window, video, or provider capabilities. The Linux application and render CI remain gated by the complete registered Compose/native source graph.

`RenderChecks.kt` exercises the actual Compose/Skia primitive adapter on the Swing event thread. Pass the fixture directory and image output directory to `syncwatch.design.tests.RenderChecksKt`. It runs the shared geometry, transparency and filled-text alignment probes, then the component state/theme/language/viewport matrix. Text probes check ink presence in document-defined regions, allowing native font rasterization differences while rejecting a paragraph placed on the wrong edge. Each scene is disposed before its composition owner, and rendering must emit no user actions. Offscreen image checks do not establish desktop input, video or provider acceptance.

`RetainedChecks.kt` verifies that changing Application presentation changes the rendered pane without recreating its composition. It also checks final disposal. These assertions run in the render suite. Its explicit `--native` mode requires an interactive desktop and the registered renderer/font environment; an owned window verifies that a real AWT Canvas stays displayable, hides/shows and releases once on final close. This mode does not qualify manual input, physical video output or synchronization.
