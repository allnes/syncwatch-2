package syncwatch

import java.nio.file.Files
import java.nio.file.Path
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.withTimeout
import syncwatch.library.*

private class RefreshAccessStore : LibraryAccessStore {
    private var record: LibraryAccessRecord? = null
    private var writes = 0
    @Synchronized fun count() = writes
    @Synchronized override fun read() = LibraryAccessRead(if (record == null) LibraryAccessStatus.missing else LibraryAccessStatus.loaded, record)
    @Synchronized override fun write(record: LibraryAccessRecord) { this.record = record; writes++ }
}

suspend fun libraryRefreshChecks(owner: CoroutineScope) {
    val scratch = Files.createTempDirectory("syncwatch-library-refresh-")
    val first = Files.createDirectory(scratch.resolve("first")); val second = Files.createDirectory(scratch.resolve("second"))
    for (root in listOf(first, second)) Files.writeString(root.resolve("Кино.One.mkv"), "fixture")
    val store = RefreshAccessStore(); val model = LibraryController(store, owner, null)
    var restored: LibraryController? = null
    suspend fun eventually(condition: () -> Boolean) = withTimeout(8000) { while (!condition()) delay(20) }
    try {
        model.choose(first); model.settled()
        val selected = checkNotNull(model.presentation.selectedID)
        Files.writeString(first.resolve("Кино.Two.mkv"), "fixture")
        eventually { model.presentation.entries.size == 2 }
        check(model.presentation.selectedID == selected && store.count() == 1)
        Files.writeString(first.resolve("old-only.mp4"), "fixture")
        model.choose(second); model.settled()
        Files.writeString(second.resolve("Кино.Two.mkv"), "fixture")
        eventually { model.presentation.entries.size == 2 }
        check(model.presentation.entries.map { it.title } == listOf("Кино.One.mkv", "Кино.Two.mkv"))
        check(model.selectedMedia()?.access?.root == second && store.count() == 2)
        model.closeAndWait()
        store.write(checkNotNull(store.read().record).copy(autoRefresh = false))
        val next = LibraryController(store, owner, null); restored = next
        next.restore(); next.settled(); val writes = store.count()
        Files.writeString(second.resolve("manual.mp4"), "fixture"); delay(1000)
        check(next.presentation.entries.size == 2)
        next.rescan(); next.settled()
        check(next.presentation.entries.size == 3 && store.count() == writes)
        next.closeAndWait(); check(next.presentation.enabledActions.isEmpty())
    } finally {
        model.closeAndWait(); restored?.closeAndWait()
        scratch.toFile().deleteRecursively(); check(!Files.exists(scratch))
    }
}
