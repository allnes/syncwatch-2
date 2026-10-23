package syncwatch.bridge;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/** Inherited pipes only; a single in-flight read/write bounds each executor. */
public final class PipeTransport {
    private final Process process;
    private final ExecutorService reader = worker("SyncWatch helper read"), writer = worker("SyncWatch helper write");
    private final AtomicBoolean reading = new AtomicBoolean(), writing = new AtomicBoolean(), closing = new AtomicBoolean();
    private final CompletableFuture<Void> closed = new CompletableFuture<>();
    private PipeTransport(Process process) {
        this.process = process;
        Thread errors = new Thread(() -> {
            try { byte[] discard = new byte[1024]; while (process.getErrorStream().read(discard) >= 0) { } }
            catch (IOException ignored) { }
        }, "SyncWatch helper diagnostics"); errors.setDaemon(true); errors.start();
    }
    public static PipeTransport start(Path executable, Path runtime) throws IOException {
        if (!executable.isAbsolute() || !runtime.isAbsolute()) throw new IllegalArgumentException("helper-path");
        ProcessBuilder builder = new ProcessBuilder(executable.toString(), runtime.toString()).directory(runtime.toFile());
        builder.environment().keySet().removeIf(key -> key.toUpperCase(java.util.Locale.ROOT).startsWith("PYTHON"));
        return new PipeTransport(builder.start());
    }
    private static ExecutorService worker(String name) {
        return Executors.newSingleThreadExecutor(task -> { Thread thread = new Thread(task, name); thread.setDaemon(true); return thread; });
    }
    @FunctionalInterface private interface Work<T> { T run() throws Exception; }
    private <T> CompletableFuture<T> submit(ExecutorService executor, AtomicBoolean busy, Work<T> work) {
        CompletableFuture<T> result = new CompletableFuture<>();
        if (closing.get() || !busy.compareAndSet(false, true)) return CompletableFuture.failedFuture(new IOException("queueFull"));
        result.whenComplete((value, error) -> { if (result.isCancelled()) process.destroyForcibly(); });
        try {
            executor.execute(() -> {
                T value;
                try { value = work.run(); }
                catch (Exception error) { busy.set(false); process.destroyForcibly(); result.completeExceptionally(error); return; }
                busy.set(false); result.complete(value);
            });
        } catch (RuntimeException error) { busy.set(false); result.completeExceptionally(error); }
        return result;
    }
    private static void validate(byte[] frame) throws IOException {
        if (frame.length < 2 || frame.length > 65536 || frame[frame.length - 1] != 10) throw new IOException("frame");
        for (int i = 0; i < frame.length; i++) if (frame[i] == 13 || i < frame.length - 1 && frame[i] == 10) throw new IOException("frame");
        StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(frame));
    }
    public CompletableFuture<byte[]> read() {
        return submit(reader, reading, () -> {
            ByteArrayOutputStream result = new ByteArrayOutputStream();
            while (true) {
                int b = process.getInputStream().read(); if (b < 0) throw new IOException("helper-stopped");
                result.write(b); if (result.size() > 65536) throw new IOException("frameTooLarge");
                if (b == 10) { byte[] frame = result.toByteArray(); validate(frame); return frame; }
            }
        });
    }
    public CompletableFuture<Void> send(byte[] frame) {
        byte[] owned = frame.clone();
        return submit(writer, writing, () -> { validate(owned); process.getOutputStream().write(owned); process.getOutputStream().flush(); return null; });
    }
    public CompletableFuture<Void> closeAsync() {
        if (closing.compareAndSet(false, true)) {
            Thread watchdog = new Thread(() -> {
                try { if (!process.waitFor(3, TimeUnit.SECONDS)) process.destroyForcibly(); }
                catch (InterruptedException error) { Thread.currentThread().interrupt(); process.destroyForcibly(); }
            }, "SyncWatch helper watchdog"); watchdog.setDaemon(true); watchdog.start();
            Thread release = new Thread(() -> {
                try {
                    try { process.getOutputStream().close(); } catch (IOException ignored) { }
                    process.waitFor(); reader.shutdown(); writer.shutdown();
                    while (!reader.awaitTermination(1, TimeUnit.SECONDS) || !writer.awaitTermination(1, TimeUnit.SECONDS)) { }
                    process.getInputStream().close(); process.getErrorStream().close(); closed.complete(null);
                } catch (Exception error) { process.destroyForcibly(); closed.completeExceptionally(error); }
            }, "SyncWatch helper release"); release.setDaemon(true); release.start();
        }
        return closed;
    }
}
