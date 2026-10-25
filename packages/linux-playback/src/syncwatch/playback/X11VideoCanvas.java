package syncwatch.playback;

import java.awt.Canvas;
import java.awt.EventQueue;
import java.awt.event.ComponentAdapter;
import java.awt.event.ComponentEvent;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CancellationException;
import java.util.function.Supplier;

/** Native surface lifetime and physical geometry only. Composition belongs to SyncWatch Design. */
public final class X11VideoCanvas extends Canvas {
    private static final long serialVersionUID = 1L;
    private final transient X11Display display;
    private final transient Supplier<CompletableFuture<Void>> closeOwner;
    private final transient CompletableFuture<X11Display.Surface> attached = new CompletableFuture<>();
    private transient volatile X11Display.Surface surface;
    private boolean detaching;
    private transient CompletableFuture<Void> released;

    @java.io.Serial private Object writeReplace() throws java.io.ObjectStreamException {
        throw new java.io.NotSerializableException("Native X11 canvas");
    }
    @java.io.Serial private void readObject(java.io.ObjectInputStream input) throws java.io.IOException {
        throw new java.io.NotSerializableException("Native X11 canvas");
    }

    public X11VideoCanvas(X11Display display, Supplier<CompletableFuture<Void>> closeOwner) {
        this.display = java.util.Objects.requireNonNull(display);
        this.closeOwner = java.util.Objects.requireNonNull(closeOwner);
        // XComponentPeer otherwise reports its current bounds as its minimum
        // and preferred size. Native video has no intrinsic layout size.
        setMinimumSize(new java.awt.Dimension(0, 0));
        setPreferredSize(new java.awt.Dimension(0, 0));
        addComponentListener(new ComponentAdapter() {
            @Override public void componentResized(ComponentEvent event) {
                if (surface != null && !detaching) surface.resize();
            }
        });
    }

    public CompletableFuture<X11Display.Surface> surface() { return attached.copy(); }

    @Override public void addNotify() {
        super.addNotify();
        EventQueue.invokeLater(() -> {
            if (detaching || !isDisplayable() || attached.isDone()) return;
            try {
                surface = display.acquireOwned(this);
                attached.complete(surface);
            } catch (Throwable error) { attached.completeExceptionally(error); }
        });
    }

    /** Call on the event thread; keep the owning window until the returned receipt completes. */
    public CompletableFuture<Void> releaseAfter(CompletableFuture<Void> nativeRelease) {
        if (!EventQueue.isDispatchThread()) throw new IllegalStateException("surface-event-thread");
        if (released != null) return released.copy();
        detaching = true;
        attached.completeExceptionally(new CancellationException("surface-detached"));
        released = nativeRelease.thenRun(() -> {
            X11Display.Surface owned = surface;
            if (owned != null) owned.retainUntilClosed();
        });
        return released.copy();
    }

    @Override public void removeNotify() {
        // Preserve the independent drawable before AWT destroys the Canvas peer.
        if (surface != null) surface.park();
        releaseAfter(closeOwner.get());
        super.removeNotify();
    }
}
