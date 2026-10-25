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
        private long owner;
        private boolean parked;
        private boolean bound;
        private boolean released;

        private Surface(X11Display display, Canvas canvas, long drawable) {
            this.display = display;
            this.canvas = canvas;
            this.drawable = drawable;
        }

        private Surface(X11Display display, Canvas canvas, long drawable, long owner) {
            this(display, canvas, drawable);
            this.owner = owner;
        }

        synchronized long bindDrawable() {
            if (bound || released) throw new IllegalStateException("surface-owned-or-closed");
            bound = true;
            return drawable;
        }
        synchronized void retainUntilClosed() {
            if (owner != 0) { destroyOwned(owner); owner = 0; }
            released = true;
            java.lang.ref.Reference.reachabilityFence(canvas);
            java.lang.ref.Reference.reachabilityFence(display);
        }
        synchronized void resize() { if (owner != 0 && !parked) resizeOwned(owner); }
        synchronized void park() {
            if (owner != 0 && !parked) { parkOwned(owner); parked = true; }
        }
        /** Development lifecycle observation; no physical pixel/output claim. */
        public synchronized boolean isParkedAndAlive() { return owner != 0 && isParkedOwned(owner); }
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

    Surface acquireOwned(Canvas canvas) {
        if (!EventQueue.isDispatchThread() || canvas == null || !canvas.isDisplayable())
            throw new IllegalStateException("displayable-event-thread-surface");
        Path jawt = Path.of(System.getProperty("java.home"), "lib", "libjawt.so").toAbsolutePath().normalize();
        long[] value = createOwned(nativeLibrary, canvas, NativePlayback.bytes(jawt.toString()));
        if (value.length != 2 || value[0] == 0 || value[1] <= 0 || value[1] > 0xffffffffL)
            throw new IllegalStateException("owned-x11-drawable");
        return new Surface(this, canvas, value[1], value[0]);
    }

    private static native long initialize(byte[] library);
    private static native long drawable(long library, Canvas canvas, byte[] jawtLibrary);
    private static native long[] createOwned(long library, Canvas canvas, byte[] jawtLibrary);
    private static native void resizeOwned(long owner);
    private static native void parkOwned(long owner);
    private static native boolean isParkedOwned(long owner);
    private static native void destroyOwned(long owner);
}
