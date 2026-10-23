import java.util.List;
import java.util.Map;
import syncwatch.ipc.Json;
import syncwatch.playback.NativePlayback;

/** Executable JVM/value boundary checks; deliberately makes no Kotlin/Compose/application claim. */
public final class BoundaryChecks {
    private BoundaryChecks() { }
    private static void reject(Runnable operation) {
        try { operation.run(); } catch (IllegalArgumentException expected) { return; }
        throw new IllegalStateException("Invalid input was accepted");
    }
    public static void main(String[] arguments) {
        new NativePlayback.Scope("scope-1", 9007199254740991L);
        reject(() -> new NativePlayback.Scope("scope-1", 9007199254740992L));
        reject(() -> new NativePlayback.Scope("scope-1", -1));
        reject(() -> new NativePlayback.Scope("../foreign", 1));
        reject(() -> new NativePlayback.Scope("\u03bc", 1));
        NativePlayback.Scope scope = new NativePlayback.Scope("scope-1", 2);
        new NativePlayback.Observation(scope, 0, 0, null, 1, 0, true, false, false, false, 0, 0, 0, null, false);
        reject(() -> new NativePlayback.Observation(scope, 0, 0, null, 1, 0, false, false, false, false, 0, 0, 0, null, false));
        reject(() -> new NativePlayback.Observation(scope, 0, 11, 10L, 1, 2, true, true, false, false, 0, 0, 0, null, false));
        reject(() -> new NativePlayback.Observation(scope, 0, 0, null, Double.NaN, 2, true, true, false, false, 0, 0, 0, null, false));
        Map<String, Object> value = Map.of("text", "Unicode \ud83c\udfac", "paused", true, "counter", 9007199254740991L);
        if (!Json.object(Json.parse(Json.write(value))).equals(value)) throw new IllegalStateException("JSON roundtrip");
        for (String bad : List.of("{\"v\":1,\"v\":2}", "{\"v\":1,\"\\u0076\":2}", "[1,]", "[NaN]", "\"\\ud800\"", "01")) {
            reject(() -> Json.parse(bad));
        }
        System.out.println("SYNCWATCH_LINUX_JVM_BOUNDARY_OK scope observation strict-json; applicationBuilt=false guiAccepted=false");
    }
}
