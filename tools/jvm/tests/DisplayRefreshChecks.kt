package syncwatch.tests

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.jetbrains.skiko.FrameLimiter

/** Exercise the configured source-built module without loading a native renderer. */
fun main() = runBlocking {
    val normalize = Class.forName("org.jetbrains.skiko.DisplayKt")
        .getDeclaredMethod("normalizeDisplayRefreshRate", Double::class.javaPrimitiveType)
        .apply { isAccessible = true }
    fun rate(input: Double) = normalize.invoke(null, input) as Double
    for (invalid in listOf(0.0, -1.0, Double.NaN, Double.POSITIVE_INFINITY, Double.NEGATIVE_INFINITY))
        check(rate(invalid) == 60.0)
    for (valid in listOf(23.976, 24.0, 50.0, 60.0, 144.0, 240.0)) check(rate(valid) == valid)
    val owner = SupervisorJob()
    try {
        val limiter = FrameLimiter(CoroutineScope(Dispatchers.Default + owner), { (1000 / rate(0.0)).toLong() })
        withTimeout(3000) { repeat(4) { limiter.awaitNextFrame() } }
    } finally { owner.cancelAndJoin() }
    println("SYNCWATCH_DISPLAY_REFRESH_OK")
}
