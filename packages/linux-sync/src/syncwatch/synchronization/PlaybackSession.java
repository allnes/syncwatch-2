package syncwatch.synchronization;

import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import syncwatch.playback.NativePlayback;
import syncwatch.bridge.PipeTransport;
import syncwatch.playback.NativePlayback.Observation;
import syncwatch.playback.NativePlayback.Scope;

/** Single-owner application session for the Kotlin client. It makes no Syncplay policy decisions.
 * This compiled JVM/native boundary does not establish Compose GUI acceptance. */
public final class PlaybackSession {
    public record Endpoint(String host, int port, String room, String username) {
        public Endpoint {
            if (host == null || !host.matches("[A-Za-z0-9.:_-]{1,253}") || port < 1 || port > 65535) throw Json.bad();
            HelperWire.text(room, 256); HelperWire.text(username, 64);
        }
    }
    private record Action(boolean pause, long value) { }
    private record Pending(String kind, long deadline) { }
    private record Completed(byte[] input, byte[] result) { }
    private final NativePlayback player;
    private final Scope scope;
    private final PipeTransport helper;
    private final long duration;
    private final ThreadPoolExecutor worker = new ThreadPoolExecutor(1, 1, 0, TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(1), task -> { Thread thread = new Thread(task, "SyncWatch session"); thread.setDaemon(true); return thread; });
    private final AtomicBoolean closing = new AtomicBoolean(), stepping = new AtomicBoolean();
    private final AtomicBoolean disposing = new AtomicBoolean();
    private final CompletableFuture<Void> closed = new CompletableFuture<>();
    private final ArrayDeque<Action> actions = new ArrayDeque<>();
    private final Map<String, Pending> pending = new HashMap<>();
    private final Map<String, Completed> completed = new HashMap<>();
    private final ArrayDeque<String> completionOrder = new ArrayDeque<>();
    private CompletableFuture<byte[]> incoming;
    private long commands, users, corrections, events, lastPing = System.nanoTime();
    private final long connectionDeadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(15);
    private boolean connectedOnce, readyRequested;
    private volatile boolean connected, ready;
    public boolean connected() { return connected; }
    public boolean ready() { return ready; }

    private PlaybackSession(NativePlayback player, Scope scope, PipeTransport helper, long duration) {
        this.player = player; this.scope = scope; this.helper = helper; this.duration = duration;
    }
    public static CompletableFuture<PlaybackSession> start(NativePlayback player, Scope scope, Path executable, Path runtime,
            String revision, String mediaName, long fileSize, Endpoint endpoint) {
        return CompletableFuture.supplyAsync(() -> {
            PlaybackSession session = null;
            try {
                HelperWire.text(mediaName, 256);
                if (mediaName.contains("/") || mediaName.contains("\\") || fileSize < 0 || fileSize > HelperWire.MAXIMUM) throw Json.bad();
                Observation actual = player.observe(scope).get(3, TimeUnit.SECONDS);
                if (actual.status() != 2 || !actual.paused() || actual.durationMs() == null || actual.durationMs() <= 0) throw Json.bad();
                session = new PlaybackSession(player, scope, PipeTransport.start(executable, runtime), actual.durationMs());
                String hello = session.command("bridge.hello", Map.of("supportedVersions", java.util.List.of(1)));
                HelperWire.Frame reply = session.awaitReply(hello);
                if (!revision.equals(reply.payload().get("syncplayRevision"))) throw Json.bad();
                session.awaitReply(session.command("player.loaded", Map.of("mediaHandle", "selected-media", "name", mediaName,
                    "durationMs", session.duration, "fileSizeBytes", fileSize)));
                session.awaitReply(session.command("sync.connect", Map.of("host", endpoint.host(), "port", endpoint.port(),
                    "room", endpoint.room(), "username", endpoint.username(), "tls", true)));
                return session;
            } catch (Exception error) {
                if (session != null) session.closeAsync().join();
                throw new java.util.concurrent.CompletionException(error);
            }
        });
    }
    private boolean request(Action action) {
        synchronized (actions) {
            if (closing.get() || !connected || actions.size() >= 32 || !action.pause() && (action.value() < 0 || action.value() > duration)) return false;
            actions.add(action); return true;
        }
    }
    public boolean pause(boolean paused) { return request(new Action(true, paused ? 1 : 0)); }
    public boolean seek(long positionMs) { return request(new Action(false, positionMs)); }
    public CompletableFuture<Observation> step() {
        if (closing.get() || !stepping.compareAndSet(false, true)) return CompletableFuture.failedFuture(new IllegalStateException("concurrent-owner"));
        CompletableFuture<Observation> result = new CompletableFuture<>();
        try {
            worker.execute(() -> {
                Observation value;
                try { value = pump(); }
                catch (Exception error) { stop(); stepping.set(false); result.completeExceptionally(error); return; }
                stepping.set(false); result.complete(value);
            });
        } catch (RuntimeException error) { stepping.set(false); result.completeExceptionally(error); }
        return result;
    }
    private Observation pump() throws Exception {
        for (int i = 0; i < 32; i++) {
            Action action; synchronized (actions) { action = actions.poll(); }
            if (action == null) break;
            if (!connected) throw new IllegalStateException("disconnected");
            Observation actual = apply(action.pause() ? "player.setPaused" : "player.setPosition", action.value());
            if (users == HelperWire.MAXIMUM) throw Json.bad(); publish(actual, ++users);
        }
        for (int i = 0; i < 64; i++) {
            if (incoming == null) incoming = helper.read(); if (!incoming.isDone()) break;
            byte[] frame = incoming.get(5, TimeUnit.SECONDS); incoming = null;
            receive(HelperWire.decode(frame, scope));
        }
        if (pending.values().stream().anyMatch(p -> System.nanoTime() > p.deadline())
                || !connectedOnce && System.nanoTime() > connectionDeadline) throw new IllegalStateException("helper-timeout");
        if (System.nanoTime() - lastPing > TimeUnit.SECONDS.toNanos(2)) { command("bridge.ping", Map.of()); lastPing = System.nanoTime(); }
        Observation actual = observe(); publish(actual, null);
        if (connected && !readyRequested) { command("sync.setReady", Map.of("ready", true)); readyRequested = true; }
        return actual;
    }
    private Observation observe() throws Exception {
        if (closing.get()) throw new IllegalStateException("closed");
        Observation actual = player.observe(scope).get(3, TimeUnit.SECONDS);
        if (!scope.equals(actual.scope()) || actual.status() != 2 || actual.durationMs() == null || actual.durationMs() != duration || actual.ended()) throw new IllegalStateException("media-unavailable");
        return actual;
    }
    private Observation apply(String kind, double value) throws Exception {
        if (closing.get()) throw new IllegalStateException("closed");
        switch (kind) {
            case "player.setPaused" -> player.pause(value != 0, scope).get(3, TimeUnit.SECONDS);
            case "player.setPosition" -> {
                if (value > duration) throw Json.bad(); player.seek((long)value, scope).get(3, TimeUnit.SECONDS);
            }
            case "player.setSpeed" -> player.rate(value, scope).get(3, TimeUnit.SECONDS);
            default -> { }
        }
        long started = System.nanoTime();
        while (true) {
            Observation actual = observe();
            boolean applied = switch (kind) {
                case "player.setPaused" -> actual.paused() == (value != 0);
                case "player.setPosition" -> Math.abs(actual.positionMs() - value) <= 1000;
                case "player.setSpeed" -> Math.abs(actual.rate() - value) < .01;
                default -> true;
            };
            if (applied) return actual;
            if (System.nanoTime() - started > TimeUnit.SECONDS.toNanos(2)) throw new IllegalStateException("player-timeout");
            Thread.sleep(20);
        }
    }
    private void publish(Observation actual, Long user) throws Exception {
        helper.send(HelperWire.encode(scope, "player.state", Map.of("status", "ready", "positionMs", actual.positionMs(),
            "durationMs", duration, "paused", actual.paused(), "rate", actual.rate(), "seekable", actual.seekable()), null, null, user)).get(5, TimeUnit.SECONDS);
    }
    private String command(String kind, Map<String, Object> payload) throws Exception {
        if (pending.size() >= 16 || commands == HelperWire.MAXIMUM) throw new IllegalStateException("queueFull");
        String id = "cmd-" + ++commands;
        pending.put(id, new Pending(kind, System.nanoTime() + TimeUnit.SECONDS.toNanos(5)));
        helper.send(HelperWire.encode(scope, kind, payload, id, null, null)).get(5, TimeUnit.SECONDS); return id;
    }
    private HelperWire.Frame awaitReply(String id) throws Exception {
        while (true) {
            if (!pending.containsKey(id) || System.nanoTime() > pending.get(id).deadline()) throw new IllegalStateException("helper-timeout");
            HelperWire.Frame frame = HelperWire.decode(helper.read().get(5, TimeUnit.SECONDS), scope); receive(frame);
            if (frame.reply() && frame.id().equals(id)) return frame;
        }
    }
    private void receive(HelperWire.Frame frame) throws Exception {
        if (frame.reply()) {
            Pending request = pending.remove(frame.id());
            if (request == null || !frame.kind().equals(request.kind().equals("bridge.hello") ? "bridge.ready" : "bridge.result")) throw new IllegalStateException("helper-result");
            return;
        }
        if (frame.after() != null) {
            Completed replay = completed.get(frame.id());
            if (replay != null) {
                if (!Arrays.equals(replay.input(), frame.bytes())) throw new IllegalStateException("conflicting-replay");
                helper.send(replay.result()).get(5, TimeUnit.SECONDS); return;
            }
            long number = Long.parseLong(frame.id().substring(4));
            if (number <= corrections || frame.after() > users) throw new IllegalStateException("correction-order"); corrections = number;
            byte[] result;
            if (frame.after() < users) result = HelperWire.encode(scope, "bridge.error", Map.of("code", "cancelled", "message", "cancelled", "retryable", false), null, frame.id(), null);
            else {
                double value = switch (frame.kind()) {
                    case "player.setPaused" -> HelperWire.flag(frame.payload().get("paused")) ? 1 : 0;
                    case "player.setPosition" -> HelperWire.position(frame.payload().get("positionMs"));
                    case "player.setSpeed" -> ((Number)frame.payload().get("rate")).doubleValue();
                    default -> 0;
                };
                if (frame.kind().equals("player.openFile") && !"selected-media".equals(frame.payload().get("mediaHandle"))) throw new IllegalStateException("media-selection");
                Observation actual = apply(frame.kind(), value);
                result = HelperWire.encode(scope, "player.result", Map.of("status", "applied", "positionMs", actual.positionMs(), "paused", actual.paused()), null, frame.id(), null);
            }
            completed.put(frame.id(), new Completed(frame.bytes(), result)); completionOrder.add(frame.id());
            if (completionOrder.size() > 64) completed.remove(completionOrder.remove());
            helper.send(result).get(5, TimeUnit.SECONDS); return;
        }
        long number = Long.parseLong(frame.id().substring(6)); if (number <= events) throw Json.bad(); events = number;
        if (frame.kind().equals("sync.connection")) {
            connected = "connected".equals(frame.payload().get("state"));
            if (!connected && connectedOnce) throw new IllegalStateException("disconnected"); connectedOnce |= connected;
        } else if (frame.kind().equals("sync.readiness")) ready = HelperWire.flag(frame.payload().get("ready"));
    }
    private void stop() {
        closing.set(true); connected = ready = false; synchronized (actions) { actions.clear(); }
        try { player.stop(scope).get(3, TimeUnit.SECONDS); } catch (Exception ignored) { }
        try { helper.closeAsync().get(5, TimeUnit.SECONDS); } catch (Exception ignored) { }
    }
    public CompletableFuture<Void> closeAsync() {
        if (disposing.compareAndSet(false, true)) {
            closing.set(true); worker.shutdown();
            Thread release = new Thread(() -> {
                try { while (!worker.awaitTermination(1, TimeUnit.SECONDS)) { } stop(); closed.complete(null); }
                catch (Exception error) { closed.completeExceptionally(error); }
            }, "SyncWatch session release"); release.setDaemon(true); release.start();
        }
        return closed;
    }
}
