# Native application candidates

Application packaging uses the common first-party staging policy in
`tools/application/candidate_tree.py`. Platform adapters supply explicit application,
media, helper and runtime components. This policy does not build dependencies or
download runtimes.

The assembler reserves a new output directory, inventories its inputs, copies and
checks their bytes and executable modes, then publishes `contents` and an atomic
`candidate.json` receipt. Existing outputs are never adopted or replaced. Failure
removes only the newly reserved output. Component destinations cannot escape,
collide or overwrite an application's existing assets. Nested runtime components
are ordered after their application directory. Relative links must remain inside
their component; Windows components reject links.

The receipt records the source commit, native target, component inventories and
actual candidate files. It declares a development candidate, with release readiness
false. Local byte integrity does not authenticate a release or seal a mutable
filesystem against concurrent modification.

The staging policy is checked on all three native CI lanes:

```sh
python3 -m unittest discover -s tools/application/tests -v
```

These checks cover relocation, Unicode paths, unchanged inputs, existing user data,
contained links, partial copy failure and input mutation. They do not qualify an
installer, an application window or playback. Complete native adapters, runtime
closure, relocated launch, restart and interoperability acceptance remain required.
The developer JDK described in `tools/jvm/toolchains.json` is not an application
runtime input. The Linux adapter requires the separately pinned, source-built JVM
described below.

## Native recipes

`tools/application/package.py` runs only on its requested native OS/architecture.
Its build-time inputs are explicit; the resulting application's normal launch
does not require media, helper, bridge or developer runtime flags.

| Target | Application input | Bundled runtime locations |
| --- | --- | --- |
| macOS | Built Swift executable | `SyncWatch.app/Contents/Frameworks/{Media,Syncplay}`; first-party playback ABI statically linked |
| Windows | WPF project and declared .NET SDK | All published assemblies, `Media`, `Syncplay`, first-party playback DLL and private `Runtime` beside `SyncWatch.exe` |
| Linux | Production application JAR | `Media`, `Syncplay`, JNI/ABI libraries, source-built `Runtime`, reviewed `Desktop` JARs and `Renderer` beside the native launcher |

For example, on macOS:

```sh
python3 tools/application/package.py --target macos-arm64 \
  --application apps/macos/.build/debug/SyncWatch \
  --media-package /path/to/verified-media-payload \
  --helper-package /path/to/verified-helper-package --output /path/to/new-candidate
```

Windows publishing uses the standard WinExe apphost with `AppHostRelativeDotNet`
and `AppHostDotNetSearch=AppRelative`. SDK and framework runtime versions belong to
`tools/native/toolchains.json`. Global .NET installations are not searched. The
SDK-provided platform runtime grants accompany its selected framework directories.

`tools/application/build_linux.py` compiles only the production owners declared
in `apps/linux/application.json`; tests are not shipped as application classes.
Every runtime JAR is checked against the existing reviewed Linux compiler output.
The native launcher resolves its own executable directory, supplies owned X11,
font, audio and library locations, and invokes its private Java executable. It
preserves application arguments and removes ambient JVM options/classpath overrides.

## Application JVM source profile

`tools/application/jvm-profile.json` pins OpenJDK21 and the additional ALSA/X11
clients and build-only CUPS/Xt headers as registered Git submodules. OpenJDK's
bundled native sources and per-module grants remain in that original snapshot.
`jvm_sources.py` exports and verifies original Git blobs, modes and grants;
`jvm_runtime.py` checks their pinned archive digests before an offline Linux build.
The verified Temurin SDK is used only to bootstrap compilation. It is not copied
into the resulting runtime image.

The runtime retains corresponding original source archives, OpenJDK's root grants
and every selected module's legal files. GPL/Classpath-exception and other original
terms remain attached to their respective files; the product's Apache license does
not replace them. The source-built X11/font clients come from the declared native
SDK graph. Native import closure, packaging CI, relocated GUI launch and all six
interoperability directions remain qualification gates. A successful source build
or a locally assembled candidate alone does not clear those gates.
