package syncwatch.playback;

import java.nio.charset.StandardCharsets;
import java.nio.charset.CodingErrorAction;
import java.nio.ByteBuffer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.ArrayList;
import java.util.List;

/** First-party JVM/JNI boundary for the Kotlin client. No Compose or copied-frame GUI.
 * The caller must verify the owned media package before openVerified. */
public final class NativePlayback {
    public record Track(int id, String name) { }
    public record Scope(String clientRunId, long generation) {
        public Scope {
            if (clientRunId == null || !clientRunId.matches("[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
                    || generation < 0 || generation > 9007199254740991L) throw new IllegalArgumentException("scope");
        }
    }
    public record Observation(Scope scope, long sequence, long positionMs, Long durationMs,
            double rate, int status, boolean paused, boolean seekable, boolean buffering,
            boolean ended, int videoOutputs, int width, int height, Double volume, boolean muted) {
        public Observation {
            if (positionMs < 0 || positionMs > 604800000L || durationMs != null
                    && (durationMs < 0 || durationMs > 604800000L || positionMs > durationMs)
                    || !Double.isFinite(rate) || rate < .25 || rate > 4 || status < 0 || status > 3
                    || width < 0 || height < 0 || videoOutputs < 0
                    || volume != null && (!Double.isFinite(volume) || volume < 0 || volume > 1)
                    || status != 2 && (!paused || seekable || rate != 1)
                    || status == 0 && (positionMs != 0 || durationMs != null)) throw new IllegalArgumentException("observation");
        }
    }
    private final AtomicBoolean closing = new AtomicBoolean();
    private final CompletableFuture<Void> closed = new CompletableFuture<>();
    private static final int MAX_REQUESTS = 64;
    private final Semaphore requests = new Semaphore(MAX_REQUESTS);
    private final ThreadPoolExecutor worker = new ThreadPoolExecutor(1, 1, 0, TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<>(MAX_REQUESTS + 1), task -> { Thread thread = new Thread(task, "SyncWatch playback"); thread.setDaemon(true); return thread; });
    private long player;
    private Scope scope;
    private X11Display.Surface videoSurface;
    private static Path loadedBridge;

    @FunctionalInterface private interface Operation<T> { T run() throws Exception; }
    private <T> CompletableFuture<T> submit(Operation<T> operation) {
        CompletableFuture<T> result = new CompletableFuture<>();
        if (closing.get()) { result.completeExceptionally(new IllegalStateException("closed")); return result; }
        if (!requests.tryAcquire()) { result.completeExceptionally(new RejectedExecutionException("busy")); return result; }
        try {
            worker.execute(() -> {
                try {
                    if (result.isCancelled()) return;
                    if (closing.get()) { result.completeExceptionally(new IllegalStateException("closed")); return; }
                    result.complete(operation.run());
                }
                catch (Throwable error) { result.completeExceptionally(error); }
                finally { requests.release(); }
            });
        } catch (RejectedExecutionException error) { requests.release(); result.completeExceptionally(error); }
        return result;
    }
    static synchronized void loadBridge(Path bridge) {
        bridge = bridge.toAbsolutePath().normalize();
        if (loadedBridge != null && !loadedBridge.equals(bridge)) throw new IllegalStateException("bridge-path");
        if (loadedBridge == null) { System.load(bridge.toString()); loadedBridge = bridge; }
    }
    public CompletableFuture<Void> openVerified(Path bridge, Path library, String revision) {
        return submit(() -> {
            if (player != 0 || videoSurface != null || !library.isAbsolute()) throw new IllegalStateException("open");
            loadBridge(bridge); player = open(bytes(library.toString()), bytes(revision)); return null;
        });
    }
    /** The surface's parent window must remain displayable until closeAsync completes. */
    public CompletableFuture<Void> openX11Verified(Path bridge, Path library, String revision, X11Display.Surface surface) {
        return submit(() -> {
            if (player != 0 || videoSurface != null || !library.isAbsolute() || surface == null) throw new IllegalStateException("open");
            loadBridge(bridge);
            long drawable = surface.bindDrawable();
            // Keep the surface even if native open fails; terminal release
            // must also cover resources created before the player instance.
            videoSurface = surface;
            player = openX11(bytes(library.toString()), bytes(revision), drawable);
            return null;
        });
    }
    public CompletableFuture<Void> load(Path file, Scope incoming) {
        return submit(() -> {
            if (player == 0 || !file.isAbsolute() || !Files.isRegularFile(file)) throw new IllegalArgumentException("local-file");
            if (scope != null && !scope.clientRunId().equals(incoming.clientRunId())) throw new IllegalArgumentException("foreign-run");
            if (scope != null && incoming.generation() <= scope.generation()) throw new IllegalArgumentException("stale");
            int result = load(player, incoming.generation(), bytes(file.toString()));
            if (result == 0 || result == 4) scope = incoming;
            if (result != 0) throw new IllegalStateException(result == 1 ? "invalid" : result == 3 ? "stale" : "engine");
            return null;
        });
    }
    private void check(Scope owner) {
        if (player == 0 || scope == null) throw new IllegalStateException("unavailable");
        if (!scope.clientRunId().equals(owner.clientRunId())) throw new IllegalArgumentException("foreign-run");
        if (scope.generation() != owner.generation()) throw new IllegalArgumentException("stale");
    }
    public CompletableFuture<long[]> contentVersion(Scope owner) {
        return submit(() -> {
            check(owner); long[] value = contentVersion(player, owner.generation());
            if (value.length != 8 || value[3] < 0) throw new IllegalStateException("native-identity");
            return value;
        });
    }
    public CompletableFuture<byte[]> readContent(long offset, int capacity, Scope owner) {
        return submit(() -> {
            check(owner);
            if (offset < 0 || capacity < 1 || capacity > 262144) throw new IllegalArgumentException("invalid");
            byte[] value = readContent(player, owner.generation(), offset, capacity);
            if (value.length > capacity) throw new IllegalStateException("native-content");
            return value;
        });
    }
    public CompletableFuture<Observation> observe(Scope owner) {
        return submit(() -> {
            check(owner); long[] v = observe(player, owner.generation());
            if (v.length != 15 || v[0] != owner.generation()) throw new IllegalStateException("native-identity");
            return new Observation(owner, v[1], v[2], v[3] < 0 ? null : v[3], Double.longBitsToDouble(v[4]),
                    Math.toIntExact(v[5]), v[6] != 0, v[7] != 0, v[8] != 0, v[9] != 0,
                    Math.toIntExact(v[10]), Math.toIntExact(v[11]), Math.toIntExact(v[12]),
                    v[13] < 0 ? null : Math.min(100, v[13]) / 100d, v[14] != 0);
        });
    }
    public CompletableFuture<Void> pause(boolean paused, Scope owner) { return submit(() -> { check(owner); pause(player, owner.generation(), paused); return null; }); }
    public CompletableFuture<Void> seek(long position, Scope owner) { return submit(() -> { check(owner); seek(player, owner.generation(), position); return null; }); }
    public CompletableFuture<Void> rate(double rate, Scope owner) { return submit(() -> { check(owner); rate(player, owner.generation(), rate); return null; }); }
    public CompletableFuture<Void> volume(double volume, boolean muted, Scope owner) { return submit(() -> { check(owner); volume(player, owner.generation(), volume, muted); return null; }); }
    public CompletableFuture<Void> stop(Scope owner) { return submit(() -> { check(owner); stop(player, owner.generation()); return null; }); }
    public CompletableFuture<List<Track>> tracks(boolean subtitles, Scope owner) {
        return submit(() -> {
            check(owner); List<Track> tracks = new ArrayList<>();
            for (int id : trackIds(player, owner.generation(), subtitles)) {
                String name = StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                        .onUnmappableCharacter(CodingErrorAction.REPORT)
                        .decode(ByteBuffer.wrap(trackName(player, owner.generation(), subtitles, id))).toString();
                tracks.add(new Track(id, name));
            }
            return List.copyOf(tracks);
        });
    }
    public CompletableFuture<Void> selectTrack(int id, boolean subtitles, Scope owner) {
        return submit(() -> { check(owner); selectTrack(player, owner.generation(), subtitles, id); return null; });
    }
    public CompletableFuture<Void> closeAsync() {
        if (closing.compareAndSet(false, true)) {
            // Normal work has at most MAX_REQUESTS permits. The reserved queue
            // slot lets terminal release run on the same owner even under load.
            worker.execute(() -> {
                try {
                    if (player != 0) { close(player); player = 0; }
                    if (videoSurface != null) videoSurface.retainUntilClosed();
                    videoSurface = null;
                    closed.complete(null);
                } catch (Throwable error) { closed.completeExceptionally(error); }
            });
            worker.shutdown();
        }
        // Cancelling one wait must not complete the resource owner's receipt.
        return closed.copy();
    }
    static byte[] bytes(String value) {
        if (value.indexOf(0) >= 0) throw new IllegalArgumentException("string");
        return value.getBytes(StandardCharsets.UTF_8);
    }
    private static native long open(byte[] library, byte[] revision);
    private static native long openX11(byte[] library, byte[] revision, long drawable);
    private static native int load(long player, long generation, byte[] file);
    private static native long[] observe(long player, long generation);
    private static native long[] contentVersion(long player, long generation);
    private static native byte[] readContent(long player, long generation, long offset, int capacity);
    private static native void pause(long player, long generation, boolean paused);
    private static native void seek(long player, long generation, long position);
    private static native void rate(long player, long generation, double rate);
    private static native void volume(long player, long generation, double volume, boolean muted);
    private static native void stop(long player, long generation);
    private static native int[] trackIds(long player, long generation, boolean subtitles);
    private static native byte[] trackName(long player, long generation, boolean subtitles, int id);
    private static native void selectTrack(long player, long generation, boolean subtitles, int id);
    private static native void close(long player);
}
