package syncwatch.playback;

import java.awt.Canvas;
import java.awt.EventQueue;
import java.nio.file.Path;

/** Explicit process display owner. Initialize before creating an AWT/Compose toolkit.
 * The verified Xlib remains loaded for the process: AWT has no public toolkit
 * shutdown that would permit unloading its display library independently.
 * This developer/native boundary does not qualify a packaged JVM distribution. */
public final class X11Display {
    private static X11Display processDisplay;
    private final Path library;
    private final long nativeLibrary;

    public static final class Surface {
        private final X11Display display;
        private final Canvas canvas;
        private final long drawable;

        private Surface(X11Display display, Canvas canvas, long drawable) {
            this.display = display;
            this.canvas = canvas;
            this.drawable = drawable;
        }

        long drawable() { return drawable; }
        void retainUntilClosed() {
            java.lang.ref.Reference.reachabilityFence(canvas);
            java.lang.ref.Reference.reachabilityFence(display);
        }
    }

    private X11Display(Path library, long nativeLibrary) {
        this.library = library;
        this.nativeLibrary = nativeLibrary;
    }

    /** Caller verifies the source-owned bridge/Xlib package before this call. */
    public static synchronized X11Display initializeVerified(Path bridge, Path library) throws java.io.IOException {
        library = library.toRealPath();
        if (processDisplay != null) {
            if (!processDisplay.library.equals(library)) throw new IllegalStateException("display-path");
            return processDisplay;
        }
        NativePlayback.loadBridge(bridge);
        long handle = initialize(NativePlayback.bytes(library.toString()));
        if (handle == 0) throw new IllegalStateException("display-initialization");
        processDisplay = new X11Display(library, handle);
        return processDisplay;
    }

    /** Acquire on the event thread after attachment; retain the parent until native close. */
    public Surface acquire(Canvas canvas) {
        if (!EventQueue.isDispatchThread() || canvas == null || !canvas.isDisplayable())
            throw new IllegalStateException("displayable-event-thread-surface");
        Path jawt = Path.of(System.getProperty("java.home"), "lib", "libjawt.so").toAbsolutePath().normalize();
        long id = drawable(nativeLibrary, canvas, NativePlayback.bytes(jawt.toString()));
        if (id <= 0 || id > 0xffffffffL) throw new IllegalStateException("x11-drawable");
        return new Surface(this, canvas, id);
    }

    private static native long initialize(byte[] library);
    private static native long drawable(long library, Canvas canvas, byte[] jawtLibrary);
}
