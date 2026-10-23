package syncwatch.synchronization;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.CharacterCodingException;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import syncwatch.playback.NativePlayback.Scope;

final class HelperWire {
    static final long MAXIMUM = 9007199254740991L;
    record Frame(String kind, String id, boolean reply, Long after, Map<String, Object> payload, byte[] bytes) { }
    static Map<String, Object> keys(Object value, String... names) {
        Map<String, Object> map = Json.object(value); if (!map.keySet().equals(Set.of(names))) throw Json.bad(); return map;
    }
    static String text(Object value, int maximum) {
        if (!(value instanceof String s) || s.isEmpty() || s.codePointCount(0, s.length()) > maximum
                || s.chars().anyMatch(c -> c < 32 || c == 127)) throw Json.bad(); return s;
    }
    static long counter(Object value) {
        if (!(value instanceof Number n) || !Double.isFinite(n.doubleValue()) || n.doubleValue() < 0
                || n.doubleValue() > MAXIMUM || n.doubleValue() != Math.rint(n.doubleValue())) throw Json.bad(); return n.longValue();
    }
    static long position(Object value) { long n = counter(value); if (n > 604800000) throw Json.bad(); return n; }
    static boolean flag(Object value) { if (!(value instanceof Boolean b)) throw Json.bad(); return b; }
    static Frame decode(byte[] bytes, Scope scope) throws CharacterCodingException {
        String json = StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString();
        Map<String, Object> root = Json.object(Json.parse(json));
        String kind = text(root.get("type"), 64);
        boolean correction = Set.of("player.setPaused", "player.setPosition", "player.setSpeed", "player.openFile").contains(kind);
        boolean reply = Set.of("bridge.ready", "bridge.result", "bridge.error", "bridge.stopped").contains(kind);
        if (!correction && !reply && !Set.of("sync.connection", "sync.readiness", "sync.participants").contains(kind)) throw Json.bad();
        keys(root, correction ? new String[]{"v", "type", "clientRunId", "mediaGeneration", "payload", "id", "afterUserAction"}
            : new String[]{"v", "type", "clientRunId", "mediaGeneration", "payload", reply ? "replyTo" : "id"});
        if (counter(root.get("v")) != 1 || !scope.clientRunId().equals(text(root.get("clientRunId"), 64))
                || scope.generation() != counter(root.get("mediaGeneration"))) throw Json.bad();
        String id = text(root.get(reply ? "replyTo" : "id"), 64), prefix = reply || correction ? "cmd-" : "event-";
        if (!id.startsWith(prefix) || !id.substring(prefix.length()).matches("[1-9][0-9]*")
                || Long.parseLong(id.substring(prefix.length())) > MAXIMUM) throw Json.bad();
        Map<String, Object> p = Json.object(root.get("payload"));
        switch (kind) {
            case "player.setPaused" -> { keys(p, "paused"); flag(p.get("paused")); }
            case "player.setPosition" -> { keys(p, "positionMs"); position(p.get("positionMs")); }
            case "player.setSpeed" -> {
                keys(p, "rate"); if (!(p.get("rate") instanceof Number n) || !Double.isFinite(n.doubleValue()) || n.doubleValue() < .25 || n.doubleValue() > 4) throw Json.bad();
            }
            case "player.openFile" -> { keys(p, "mediaHandle"); new Scope(text(p.get("mediaHandle"), 64), 0); }
            case "bridge.ready" -> { keys(p, "syncplayRevision"); if (!text(p.get("syncplayRevision"), 40).matches("[a-f0-9]{40}")) throw Json.bad(); }
            case "bridge.result" -> { keys(p, "status"); if (!"applied".equals(p.get("status"))) throw Json.bad(); }
            case "bridge.error" -> { keys(p, "code", "message", "retryable"); text(p.get("code"), 64); text(p.get("message"), 1024); flag(p.get("retryable")); }
            case "bridge.stopped" -> keys(p);
            case "sync.connection" -> { keys(p, "state"); if (!Set.of("connecting", "connected", "disconnected").contains(p.get("state"))) throw Json.bad(); }
            case "sync.readiness" -> { keys(p, "ready"); flag(p.get("ready")); }
            case "sync.participants" -> {
                keys(p, "participants"); if (!(p.get("participants") instanceof List<?> users) || users.size() > 64) throw Json.bad();
                for (Object user : users) { var u = keys(user, "username", "ready"); text(u.get("username"), 64); flag(u.get("ready")); }
            }
            default -> throw Json.bad();
        }
        return new Frame(kind, id, reply, correction ? counter(root.get("afterUserAction")) : null, Map.copyOf(p), bytes.clone());
    }
    static byte[] encode(Scope scope, String kind, Map<String, Object> payload, String id, String reply, Long user) {
        Map<String, Object> root = new LinkedHashMap<>(Map.of("v", 1, "type", kind, "clientRunId", scope.clientRunId(), "mediaGeneration", scope.generation(), "payload", payload));
        if (id != null) root.put("id", id); if (reply != null) root.put("replyTo", reply);
        if (kind.equals("player.state")) { root.put("origin", user == null ? "observation" : "user"); if (user != null) root.put("actionSequence", user); }
        return (Json.write(root) + "\n").getBytes(StandardCharsets.UTF_8);
    }
}
