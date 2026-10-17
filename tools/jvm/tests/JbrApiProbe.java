import com.jetbrains.Extensions;
import com.jetbrains.FontMetricsAccessor;
import com.jetbrains.JBR;
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.reflect.Method;
import java.nio.file.Paths;
import java.util.Set;

/** Checks safe optional-service behavior on the pinned, ordinary Temurin JDK. */
public final class JbrApiProbe {
    private static int assertions;

    private static void check(boolean condition, String message) {
        assertions++;
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) throws Exception {
        String mode = args[0];
        check(!JBR.isAvailable(), "Temurin must not pretend to implement JBR services");
        check("UNKNOWN".equals(JBR.getImplVersion()), "Unavailable implementation has UNKNOWN version");
        String version = mode.equals("module") ? "1.9.0" : mode.equals("java8-overlay") ? "UNKNOWN" : "SNAPSHOT";
        check(version.equals(JBR.getApiVersion()), "Wrong module/classpath/Java 8 API version: " + JBR.getApiVersion());
        check(JBR.class.getModule().isNamed() == mode.equals("module"), "Incorrect module loading mode");
        if (!mode.equals("java8-overlay")) {
            ModuleDescriptor descriptor = ModuleFinder.of(Paths.get(args[1])).find("jetbrains.runtime.api").get().descriptor();
            check(descriptor.rawVersion().get().equals("1.9.0"), "Missing module version");
            check(descriptor.exports().stream().anyMatch(e -> e.source().equals("com.jetbrains")), "Missing API export");
            check(descriptor.requires().size() == 2, "Unexpected module dependencies");
            check(descriptor.requires().stream().anyMatch(r -> r.name().equals("java.base")), "Missing base module");
            check(descriptor.requires().stream().anyMatch(r -> r.name().equals("java.desktop")
                    && r.modifiers().containsAll(Set.of(ModuleDescriptor.Requires.Modifier.STATIC,
                                                       ModuleDescriptor.Requires.Modifier.TRANSITIVE))), "Lost optional desktop requirement");
        }
        for (Extensions extension : Extensions.values()) {
            check(!JBR.isExtensionSupported(extension), "Unavailable extension reported supported");
        }
        int services = 0;
        for (Method method : JBR.class.getMethods()) {
            if (!method.getName().startsWith("get") || method.getParameterCount() != 0
                    || !method.getReturnType().getName().startsWith("com.jetbrains.")) continue;
            services++;
            Object instance = method.invoke(null);
            boolean fallback = method.getName().equals("getFontMetricsAccessor");
            check((instance != null) == fallback, "Wrong optional service/fallback: " + method.getName());
            String name = method.getName().substring(3);
            check((Boolean) JBR.class.getMethod("is" + name + "Supported").invoke(null) == fallback,
                  "Support predicate disagrees with getter: " + name);
            Object withExtensions = JBR.class.getMethod(method.getName(), Extensions[].class)
                    .invoke(null, (Object) new Extensions[0]);
            check((withExtensions != null) == fallback, "Empty extension set changed fallback: " + name);
        }
        check(services == 20, "Generated service surface changed: " + services);
        FontMetricsAccessor accessor = JBR.getFontMetricsAccessor();
        check(accessor != null && !accessor.hasOverride(null), "Ordinary-JDK font fallback is unavailable or fabricates overrides");
        accessor.removeAllOverrides();
        System.out.println(mode + ": " + assertions + " JBR API assertions passed; optional services and font fallback verified");
    }
}
