# SyncWatch Linux domain

Kotlin/JVM ownership and local state, independent of Compose, VLC, Syncplay and browser APIs. `PlaybackScope` rejects foreign runs and obsolete media generations. `WatchSession` produces local load/release effects, prevents duplicate owners, keeps playback observations authoritative, and bounds resume history. `LocalState` copies caller collections. `FileLocalStateStore` bounds UTF-8 reads, preserves future formats and commits validated state through an atomic replacement.

`tests/syncwatch/domain/DomainChecks.kt` consumes the same [local-domain corpus](../../contracts/fixtures/local-domain.json) as the macOS and Windows domain checks: 31 storage cases and six lifecycle scenarios, with additional persistence and ownership checks. The first-party JVM JSON value codec is in `packages/ipc/jvm`.

The registered Kotlin compiler/standard-library build remains incomplete. Research execution of these sources is separate from application build qualification. The required [Linux source/JVM check](../../tools/native/check_linux.py) does not compile the Kotlin domain or Compose; its report records that boundary explicitly. See [platform parity](../../docs/architecture/platform-parity.md).
