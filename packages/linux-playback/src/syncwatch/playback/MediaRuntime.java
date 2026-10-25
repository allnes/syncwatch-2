package syncwatch.playback;

import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.Map;
import java.util.Set;
import syncwatch.ipc.Json;

/** Development integrity receipt, not release authentication or an atomic filesystem seal. */
public record MediaRuntime(Path library, String revision) {
    private static IOException invalid(String code) { return new IOException("runtime-" + code); }

    public static MediaRuntime verify(Path packageDirectory) throws IOException {
        Path root = packageDirectory.toAbsolutePath().normalize();
        if (Files.isSymbolicLink(root) || !Files.isDirectory(root, LinkOption.NOFOLLOW_LINKS)) throw invalid("root");
        Path receipt = root.resolve("build-report.json");
        if (!Files.isRegularFile(receipt, LinkOption.NOFOLLOW_LINKS) || Files.size(receipt) > 16 * 1024 * 1024)
            throw invalid("receipt");
        Map<String, Object> report;
        Map<String, Object> files;
        String revision;
        try {
            report = Json.object(Json.parse(Files.readString(receipt)));
            Object target = Json.object(report.get("sdk")).get("target");
            if (!"Linux".equals(System.getProperty("os.name"))
                    || !Set.of("amd64", "x86_64").contains(System.getProperty("os.arch"))
                    || !"linux-x64".equals(target)) throw invalid("target");
            Object pin = Json.object(Json.object(report.get("sources")).get("vlc")).get("revision");
            if (!(pin instanceof String text) || !text.matches("[0-9a-f]{40}")) throw invalid("revision");
            revision = text;
            files = Json.object(report.get("files"));
        } catch (IllegalArgumentException error) { throw invalid("receipt"); }
        if (!files.containsKey("lib/libvlc.so.5")) throw invalid("library");
        for (var entry : files.entrySet()) {
            String name = entry.getKey();
            if (name.isEmpty() || name.contains("\\") || name.contains(":")
                    || name.chars().anyMatch(value -> value < 32)
                    || java.util.Arrays.stream(name.split("/", -1)).anyMatch(part -> part.isEmpty() || part.equals(".") || part.equals(".."))
                    || !(entry.getValue() instanceof String digest) || !digest.matches("[0-9a-f]{64}"))
                throw invalid("membership");
        }
        Set<String> observed = new HashSet<>();
        byte[] buffer = new byte[1024 * 1024];
        Files.walkFileTree(root, new SimpleFileVisitor<>() {
            @Override public FileVisitResult visitFile(Path file, BasicFileAttributes attributes) throws IOException {
                if (!attributes.isRegularFile() || attributes.isSymbolicLink()) throw invalid("file");
                String name = root.relativize(file).toString().replace('\\', '/');
                if (name.equals("build-report.json")) return FileVisitResult.CONTINUE;
                if (!observed.add(name) || !files.containsKey(name)) throw invalid("membership");
                MessageDigest digest;
                try { digest = MessageDigest.getInstance("SHA-256"); }
                catch (NoSuchAlgorithmException error) { throw new IllegalStateException(error); }
                try (var input = Files.newInputStream(file, LinkOption.NOFOLLOW_LINKS)) {
                    int read;
                    while ((read = input.read(buffer)) != -1) digest.update(buffer, 0, read);
                }
                if (!HexFormat.of().formatHex(digest.digest()).equals(files.get(name))) throw invalid("digest");
                return FileVisitResult.CONTINUE;
            }
        });
        if (!observed.equals(files.keySet())) throw invalid("membership");
        return new MediaRuntime(root.resolve("lib/libvlc.so.5"), revision);
    }
}
