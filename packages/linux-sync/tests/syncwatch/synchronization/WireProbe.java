package syncwatch.synchronization;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import syncwatch.playback.NativePlayback.Scope;

public final class WireProbe {
    private WireProbe() { }
    public static void main(String[] args) throws Exception {
        if (!(Json.parse(Files.readString(Path.of(args[0]))) instanceof List<?> fixtures)) throw Json.bad();
        for (Object fixture : fixtures) {
            var row = Json.object(fixture); boolean accepted;
            try {
                HelperWire.decode((row.get("json") + "\n").getBytes(StandardCharsets.UTF_8), new Scope("session-test", 2)); accepted = true;
            } catch (Exception error) { accepted = false; }
            if (accepted != HelperWire.flag(row.get("accepted"))) throw new IllegalStateException(row.get("name").toString());
        }
        if (fixtures.size() != 30) throw Json.bad();
        System.out.println("SYNCWATCH_SESSION_WIRE_OK " + fixtures.size());
    }
}
