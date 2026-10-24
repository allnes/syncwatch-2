import java.nio.file.Files
import java.nio.file.Path
import java.util.Optional
import kotlin.coroutines.*
import kotlin.io.encoding.Base64
import kotlin.io.path.*
import kotlin.jvm.optionals.getOrNull
import kotlin.time.Duration.Companion.seconds

private enum class Sample { FIRST, SECOND }

fun main(arguments: Array<String>) {
    val binary = Path.of(arguments.single()).toRealPath()
    for (type in listOf(Unit::class.java, kotlin.jvm.internal.Intrinsics::class.java)) {
        check(Path.of(type.protectionDomain.codeSource.location.toURI()).toRealPath() == binary)
    }
    check(KotlinVersion.CURRENT.toString() == "2.3.20")
    check(listOf(4, 1, 4, 2).distinct().sorted().map { it * 2 } == listOf(2, 4, 8))
    check(sequence { yieldAll(1..3) }.sum() == 6)
    check(mapOf("a" to 2).withDefault { 7 }.getValue("missing") == 7)
    check(Sample.entries.map { it.name } == listOf("FIRST", "SECOND"))
    check("\u0149".replaceFirstChar { it.titlecase() } == "\u02bcN")
    check(Regex("(?<word>sync)").find("syncwatch")!!.groups["word"]!!.value == "sync")
    check(Base64.decode(Base64.encode("Синхронизация".encodeToByteArray())).decodeToString() == "Синхронизация")
    check(Optional.of("present").getOrNull() == "present" && Optional.empty<String>().getOrNull() == null)
    check(3.seconds.inWholeMilliseconds == 3000L && (1u..3u).sum() == 6u)
    check(Double.NaN.isNaN() && Float.NaN.isNaN())
    check(listOf(1.0, Double.NaN).maxOrNull()!!.isNaN())
    check(sequenceOf(1.0, Double.NaN).maxOrNull()!!.isNaN())
    var observed: Int? = null
    val action: suspend () -> Int = { 42 }
    action.startCoroutine(object : Continuation<Int> {
        override val context = EmptyCoroutineContext
        override fun resumeWith(result: Result<Int>) { observed = result.getOrThrow() }
    })
    check(observed == 42)
    val directory = Files.createTempDirectory("stdlib-кино-")
    try {
        val file = directory.resolve("映画.txt")
        file.writeText("movie")
        check(file.readText() == "movie" && directory.listDirectoryEntries().single() == file)
    } finally { directory.toFile().deleteRecursively() }
    for (resource in listOf("kotlin/kotlin.kotlin_builtins", "kotlin/collections/collections.kotlin_builtins",
                             "META-INF/kotlin-stdlib.kotlin_module")) {
        check(Unit::class.java.classLoader.getResources(resource).toList().size == 1)
    }
    println("SYNCWATCH_STDLIB_OK source-owned runtime; collections, Unicode, metadata, coroutine, JDK7/8 and version")
}
