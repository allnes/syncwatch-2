package syncwatch.playback;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.Map;
import syncwatch.ipc.Json;

/** The JVM must reject the same missing, modified, extra and linked SDK members as its peers. */
public final class MediaRuntimeProbe {
    private static final String REVISION = "1234567890123456789012345678901234567890";
    private static void rejected(Path packageDirectory) throws IOException {
        try { MediaRuntime.verify(packageDirectory); }
        catch (IOException expected) { return; }
        throw new AssertionError("invalid SDK was accepted");
    }
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("syncwatch-media-integrity-");
        try {
            Path library = root.resolve("lib/libvlc.so.5");
            Files.createDirectory(library.getParent());
            byte[] original = "owned SDK fixture".getBytes(java.nio.charset.StandardCharsets.UTF_8);
            Files.write(library, original);
            String hash = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(original));
            Path report = root.resolve("build-report.json");
            Map<String, Object> receipt = Map.of("sdk", Map.of("target", "linux-x64"),
                    "sources", Map.of("vlc", Map.of("revision", REVISION)), "files", Map.of("lib/libvlc.so.5", hash));
            String text = Json.write(receipt);
            Files.writeString(report, text);
            if (!MediaRuntime.verify(root).revision().equals(REVISION)) throw new AssertionError("valid SDK");
            Files.writeString(library, "modified"); rejected(root);
            Files.delete(library); rejected(root);
            Files.write(library, original);
            Path extra = root.resolve("unexpected-plugin.so");
            Files.writeString(extra, "unlisted"); rejected(root); Files.delete(extra);
            Files.move(library, extra); Files.createSymbolicLink(library, extra);
            rejected(root); Files.delete(library); Files.move(extra, library);
            for (String invalid : new String[] {
                    text.replace("linux-x64", "windows-x64"), text.replace(REVISION, "invalid"),
                    text.replace("lib/libvlc.so.5", "../foreign"),
                    text.replace("\"target\":\"linux-x64\"", "\"target\":\"linux-x64\",\"target\":\"linux-x64\"")}) {
                Files.writeString(report, invalid); rejected(root);
            }
            Files.writeString(report, text);
            MediaRuntime.verify(root);
            System.out.println("{\"success\":true,\"membership\":true,\"hashes\":true,\"links\":true,\"target\":true,\"strictReceipt\":true}");
        } finally {
            try (var paths = Files.walk(root)) {
                for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) Files.delete(path);
            }
        }
    }
}
