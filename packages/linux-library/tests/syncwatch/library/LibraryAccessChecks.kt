package syncwatch.library

import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.attribute.PosixFilePermission.OWNER_READ
import java.nio.file.attribute.PosixFilePermission.OWNER_WRITE
import syncwatch.ipc.Json

internal fun libraryAccessChecks(fixture: Path, scratch: Path) {
    val selected = Files.createDirectory(scratch.resolve("selected"))
    val access = LibraryFolderAccess.selected(selected)
    val record = access.record
    val path = scratch.resolve("state/library-access.json")
    val store = FileLibraryAccessStore(path)
    check(store.read().status == LibraryAccessStatus.missing)
    store.write(record); check(store.read().record == record)
    val changed = record.copy(autoRefresh = false, scanSubfolders = false)
    store.write(changed); check(store.read().record == changed)
    val valid = Files.readString(path)
    for (replacement in listOf("1.0", "1e0")) {
        Files.writeString(path, valid.replace("\"version\":1", "\"version\":$replacement"))
        check(store.read().status == LibraryAccessStatus.invalid)
    }
    val corpus = Json.`object`(Json.parse(Files.readString(fixture.resolveSibling("library-access.json"))))
    for (entry in corpus["cases"] as List<*>) {
        val value = Json.`object`(entry)
        val bytes = (value["text"] as String).toByteArray(Charsets.UTF_8)
        Files.write(path, bytes)
        check(store.read().status.name == value["status"]) { value["name"] as String }
        if (value["status"] == "unsupportedVersion") {
            check(runCatching { store.write(record) }.isFailure)
            check(Files.readAllBytes(path).contentEquals(bytes))
        }
    }
    Files.write(path, ByteArray(FileLibraryAccessStore.MAXIMUM_BYTES + 1)); check(store.read().status == LibraryAccessStatus.invalid)
    Files.write(path, byteArrayOf(-1)); check(store.read().status == LibraryAccessStatus.invalid)
    store.write(record)
    check(LibraryFolderAccess.restore(store.read().record!!).rootId == record.rootId)
    if (Files.getFileStore(path).supportsFileAttributeView("posix")) check(Files.getPosixFilePermissions(path) == setOf(OWNER_READ, OWNER_WRITE))
    Files.delete(selected)
    check(runCatching { LibraryFolderAccess.restore(record) }.isFailure)
    check(runCatching { FileLibraryAccessStore(scratch).read() }.isFailure)
    println("SYNCWATCH_LIBRARY_ACCESS_OK")
}
