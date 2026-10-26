package syncwatch.room;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.http.HttpResponse;
import java.nio.ByteBuffer;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Flow;

/** Bound response bytes before allocating the body; no unconsumed stream escapes. */
final class RoomBodySubscriber implements HttpResponse.BodySubscriber<byte[]> {
    private static final int LIMIT = 65536;
    private final ByteArrayOutputStream bytes = new ByteArrayOutputStream();
    private final CompletableFuture<byte[]> result = new CompletableFuture<>();
    private Flow.Subscription subscription;
    RoomBodySubscriber(long expectedLength) {
        if (expectedLength > LIMIT) result.completeExceptionally(new IOException("frameTooLarge"));
    }
    @Override public CompletionStage<byte[]> getBody() { return result; }
    @Override public void onSubscribe(Flow.Subscription value) {
        if (subscription != null || result.isDone()) { value.cancel(); return; }
        subscription = value; value.request(1);
    }
    @Override public void onNext(List<ByteBuffer> items) {
        if (result.isDone()) { subscription.cancel(); return; }
        long incoming = 0;
        for (ByteBuffer item : items) incoming += item.remaining();
        if (incoming > LIMIT - bytes.size()) {
            subscription.cancel(); bytes.reset(); result.completeExceptionally(new IOException("frameTooLarge")); return;
        }
        for (ByteBuffer item : items) {
            byte[] buffer = new byte[item.remaining()]; item.get(buffer); bytes.writeBytes(buffer);
        }
        subscription.request(1);
    }
    @Override public void onError(Throwable error) { bytes.reset(); result.completeExceptionally(error); }
    @Override public void onComplete() { result.complete(bytes.toByteArray()); bytes.reset(); }
}
