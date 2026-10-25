package syncwatch.playback;

import java.awt.BorderLayout;
import java.awt.Canvas;
import java.awt.Dimension;
import java.awt.EventQueue;
import java.awt.event.KeyAdapter;
import java.awt.event.KeyEvent;
import java.awt.event.WindowAdapter;
import java.awt.event.WindowEvent;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Predicate;
import javax.swing.JFrame;
import javax.swing.WindowConstants;

/** Visible native-output fixture. It is not the Compose application or a design gallery.
 * Escape/window close retain the drawable until the native owner finishes release. */
public final class X11SurfaceProbe {
    private static <T> T await(CompletableFuture<T> value) throws Exception {
        return value.get(20, TimeUnit.SECONDS);
    }

    private static NativePlayback.Observation waitFor(NativePlayback player, NativePlayback.Scope scope,
            Predicate<NativePlayback.Observation> condition) throws Exception {
        NativePlayback.Observation last = null;
        for (int attempt = 0; attempt < 400; attempt++) {
            var value = await(player.observe(scope));
            last = value;
            if (!value.ended() && condition.test(value)) return value;
            if (value.status() == 3 || value.ended()) throw new IllegalStateException("native-transition: " + value);
            Thread.sleep(20);
        }
        throw new IllegalStateException("native-transition-timeout: " + last);
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 6 || args.length > 7 || args.length == 7 && !"--lifecycle-check".equals(args[6]))
            throw new IllegalArgumentException("bridge, VLC, revision, media, Xlib, report, optional --lifecycle-check");
        boolean lifecycleCheck = args.length == 7;
        Path report = Path.of(args[5]);
        // This must precede the first AWT/Compose toolkit call in the process.
        X11Display display = X11Display.initializeVerified(Path.of(args[0]), Path.of(args[4]));
        NativePlayback player = new NativePlayback();
        var scope = new NativePlayback.Scope("x11-native-surface", 1);
        AtomicReference<JFrame> frame = new AtomicReference<>();
        AtomicReference<Canvas> canvasOwner = new AtomicReference<>();
        AtomicReference<X11Display.Surface> surface = new AtomicReference<>();
        AtomicBoolean closing = new AtomicBoolean();
        AtomicBoolean escape = new AtomicBoolean();
        CompletableFuture<Void> disposed = new CompletableFuture<>();
        Runnable close = () -> {
            if (closing.compareAndSet(false, true)) {
                player.closeAsync().whenComplete((ignored, error) -> EventQueue.invokeLater(() -> {
                    if (error != null) { disposed.completeExceptionally(error); return; }
                    if (frame.get() != null) frame.get().dispose();
                    disposed.complete(null);
                }));
            }
        };
        boolean controls = false;
        boolean cancelledStart = false;
        boolean resized = false;
        boolean inputWaitExpired = false;
        try {
            EventQueue.invokeAndWait(() -> {
                JFrame window = new JFrame("SyncWatch native output fixture");
                frame.set(window);
                window.setDefaultCloseOperation(WindowConstants.DO_NOTHING_ON_CLOSE);
                Canvas canvas = new Canvas();
                canvasOwner.set(canvas);
                canvas.setPreferredSize(new Dimension(640, 360));
                canvas.addKeyListener(new KeyAdapter() {
                    @Override public void keyPressed(KeyEvent event) {
                        if (event.getKeyCode() == KeyEvent.VK_ESCAPE) { escape.set(true); close.run(); }
                    }
                });
                window.addWindowListener(new WindowAdapter() {
                    @Override public void windowClosing(WindowEvent event) { close.run(); }
                });
                window.add(canvas, BorderLayout.CENTER);
                window.pack();
                window.setLocationByPlatform(true);
                window.setVisible(true);
                surface.set(display.acquire(canvas));
                canvas.requestFocusInWindow();
            });
            await(player.openX11Verified(Path.of(args[0]), Path.of(args[1]), args[2], surface.get()));
            await(player.load(Path.of(args[3]), scope));
            var initial = waitFor(player, scope, v -> v.status() == 2 && v.paused() && v.seekable());
            if (initial.durationMs() == null || initial.durationMs() != 4000) throw new IllegalStateException("duration");
            await(player.pause(false, scope));
            waitFor(player, scope, v -> !v.paused() && v.positionMs() >= 450
                    && v.videoOutputs() == 1 && v.width() == 320 && v.height() == 180);
            await(player.pause(true, scope));
            waitFor(player, scope, v -> v.paused());
            await(player.volume(.5, false, scope));
            await(player.seek(2500, scope));
            waitFor(player, scope, v -> v.paused() && v.positionMs() >= 2300 && v.positionMs() <= 2700);
            await(player.pause(false, scope));
            waitFor(player, scope, v -> !v.paused() && v.positionMs() >= 2300);
            await(player.pause(true, scope));
            waitFor(player, scope, v -> v.paused());
            await(player.seek(250, scope));
            waitFor(player, scope, v -> v.paused() && v.positionMs() <= 650);
            await(player.volume(.5, true, scope));
            var audio = await(player.tracks(false, scope));
            if (audio.stream().noneMatch(v -> v.id() >= 0)) throw new IllegalStateException("tracks");
            controls = true;
            if (lifecycleCheck) {
                int[] originalWidth = new int[1];
                EventQueue.invokeAndWait(() -> {
                    originalWidth[0] = canvasOwner.get().getWidth();
                    frame.get().setSize(900, 540);
                    frame.get().validate();
                });
                waitFor(player, scope, v -> v.paused() && v.videoOutputs() == 1);
                boolean[] changed = new boolean[1];
                EventQueue.invokeAndWait(() -> changed[0] = canvasOwner.get().getWidth() != originalWidth[0]);
                if (!changed[0]) throw new IllegalStateException("native-resize");
                resized = true;
                EventQueue.invokeLater(close);
            }
            Files.writeString(report, "{\"nativeSurfaceCreated\":true,\"nativeControlsPassed\":true,"
                    + "\"waitingForWindowClose\":true,\"guiObserved\":false,\"applicationIntegrationReady\":false,"
                    + "\"physicalOutputAccepted\":false,\"pid\":" + ProcessHandle.current().pid() + "}\n");
            // Keep the real drawable available for independent CUA observation
            // and user-input close; no screenshot or synthetic input is used here.
            try { disposed.get(10, TimeUnit.MINUTES); }
            catch (java.util.concurrent.TimeoutException error) { inputWaitExpired = true; }
        } catch (java.util.concurrent.ExecutionException error) {
            Throwable cause = error.getCause();
            if (!closing.get() || !(cause instanceof IllegalStateException && "closed".equals(cause.getMessage())
                    || cause instanceof java.util.concurrent.RejectedExecutionException)) throw error;
            cancelledStart = true;
        } finally {
            EventQueue.invokeLater(close);
            disposed.get(25, TimeUnit.SECONDS);
        }
        Files.writeString(report, "{\"nativeSurfaceCreated\":true,\"nativeControlsPassed\":" + controls
                + ",\"closedBeforeDrawableDisposal\":true,\"escapeRequested\":" + escape.get()
                + ",\"cancelledDuringStartup\":" + cancelledStart
                + ",\"nativeResizeChecked\":" + resized + ",\"inputWaitExpired\":" + inputWaitExpired
                + ",\"guiObserved\":false,\"applicationIntegrationReady\":false,\"physicalOutputAccepted\":false}\n");
        System.out.println("Native X11 output fixture closed after serialized release");
    }
}
