import com.jetbrains.Extensions;
import com.jetbrains.FontMetricsAccessor;
import com.jetbrains.JBR;
import com.jetbrains.WindowDecorations;

/** Compiles actual service, extension and callback APIs against the Java 8 surface. */
final class JbrApiConsumer {
    static WindowDecorations decorations() {
        return JBR.getWindowDecorations(Extensions.BUILTIN_DISPLAY_CHECKER);
    }

    static FontMetricsAccessor.Overrider overrider() {
        return codePoint -> Float.NaN;
    }
}
