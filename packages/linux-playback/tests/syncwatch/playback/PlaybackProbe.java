package syncwatch.playback;

import java.nio.file.Path;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.function.Predicate;

/** Actual JNI/libVLC lifecycle acceptance; no GUI or physical output claim. */
public final class PlaybackProbe {
    private static <T> T await(CompletableFuture<T> future) throws Exception {
        return future.get(20, TimeUnit.SECONDS);
    }
    private static void require(boolean condition) {
        if (!condition) throw new AssertionError("native playback observation");
    }
    private static void rejected(CompletableFuture<?> future) throws Exception {
        try { await(future); }
        catch (ExecutionException expected) { return; }
        throw new AssertionError("request was accepted");
    }
    private static NativePlayback.Observation waitFor(NativePlayback player, NativePlayback.Scope scope,
            Predicate<NativePlayback.Observation> predicate) throws Exception {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(15);
        while (System.nanoTime() < deadline) {
            var value = await(player.observe(scope));
            require(value.status() != 3);
            if (predicate.test(value)) return value;
            Thread.sleep(40);
        }
        throw new AssertionError("native observation timeout");
    }
    public static void main(String[] arguments) throws Exception {
        Path bridge = Path.of(arguments[0]), library = Path.of(arguments[1]), file = Path.of(arguments[3]);
        MediaRuntime runtime = MediaRuntime.verify(library.getParent().getParent());
        require(runtime.library().equals(library) && runtime.revision().equals(arguments[2]));
        var scope = new NativePlayback.Scope("jni-owned-run", 1);
        for (int iteration = 0; iteration < 3; iteration++) {
            NativePlayback player = new NativePlayback();
            try {
                await(player.openVerified(bridge, library, arguments[2]));
                // Rejection must not consume the run or generation in the managed port.
                rejected(player.load(file, new NativePlayback.Scope("rejected-run", 0)));
                await(player.load(file, scope));
                var initial = waitFor(player, scope, v -> v.status() == 2 && v.paused() && v.seekable());
                require(initial.durationMs() == 4000 && initial.positionMs() < 300);
                await(player.pause(false, scope));
                var playing = waitFor(player, scope, v -> !v.paused() && v.positionMs() >= 450);
                require(playing.sequence() > initial.sequence());
                await(player.pause(true, scope));
                var paused = waitFor(player, scope, NativePlayback.Observation::paused);
                Thread.sleep(250);
                require(Math.abs(await(player.observe(scope)).positionMs() - paused.positionMs()) <= 60);
                await(player.seek(2500, scope));
                waitFor(player, scope, v -> v.paused() && v.positionMs() >= 2300 && v.positionMs() <= 2700);
                await(player.seek(250, scope));
                waitFor(player, scope, v -> v.paused() && v.positionMs() < 650);
                await(player.rate(1.25, scope));
                require(await(player.observe(scope)).rate() == 1.25);
                await(player.rate(1, scope));
                var audio = await(player.tracks(false, scope));
                require(audio.stream().anyMatch(track -> track.id() >= 0 && !track.name().isEmpty()));
                await(player.selectTrack(audio.stream().filter(track -> track.id() >= 0).findFirst().orElseThrow().id(), false, scope));
                rejected(player.rate(Double.NaN, scope));
                rejected(player.seek(5000, scope));
                rejected(player.pause(false, new NativePlayback.Scope("foreign", 1)));
                await(player.stop(scope));
                await(player.stop(scope));
                require(await(player.observe(scope)).status() == 0);
                rejected(player.pause(false, scope));
                var next = new NativePlayback.Scope(scope.clientRunId(), 2);
                await(player.load(file, next));
                waitFor(player, next, v -> v.status() == 2 && v.paused());
                rejected(player.observe(scope));
                rejected(player.load(file, scope));
            } finally { await(player.closeAsync()); await(player.closeAsync()); }
            rejected(player.observe(scope));
        }
        NativePlayback busy = new NativePlayback();
        await(busy.openVerified(bridge, library, arguments[2]));
        await(busy.load(file, scope));
        java.util.List<java.util.concurrent.CompletableFuture<?>> pending = new java.util.ArrayList<>();
        for (int index = 0; index < 256; index++) pending.add(busy.observe(scope));
        var cancelledWait = busy.closeAsync();
        cancelledWait.cancel(false);
        await(busy.closeAsync());
        for (var operation : pending) await(operation.handle((value, error) -> null));
        rejected(busy.observe(scope));
        System.out.println("{\"success\":true,\"ordinaryUtf8Paths\":true,\"nativeClock\":true,"
                + "\"generationTransaction\":true,\"tracks\":true,\"repeatedClose\":true,"
                + "\"guiAccepted\":false,\"physicalOutputAccepted\":false}");
    }
}
