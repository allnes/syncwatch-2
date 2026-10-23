import java.lang.module.ModuleFinder;
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleReference;
import java.nio.file.Paths;
import java.util.Set;
import java.util.stream.Collectors;

public final class StdlibModuleProbe {
    public static void main(String[] arguments) throws Exception {
        Set<ModuleReference> modules = ModuleFinder.of(Paths.get(arguments[0])).findAll();
        if (modules.size() != 1) throw new AssertionError("Exactly one owned module required");
        ModuleDescriptor descriptor = modules.iterator().next().descriptor();
        if (descriptor.isAutomatic() || !descriptor.name().equals("kotlin.stdlib")
            || !descriptor.requires().stream().allMatch(r -> r.name().equals("java.base"))
            || !descriptor.exports().stream().map(e -> e.source()).collect(Collectors.toSet()).containsAll(
                Set.of("kotlin", "kotlin.collections", "kotlin.io.path", "kotlin.streams.jdk8", "kotlin.io.encoding")))
            throw new AssertionError("Original JPMS descriptor");
        Class<?> type = Class.forName("kotlin.KotlinVersion");
        if (!type.getModule().isNamed() || !type.getModule().getName().equals("kotlin.stdlib")
            || !type.getField("CURRENT").get(null).toString().equals("2.3.20")) throw new AssertionError("Owned module execution");
        System.out.println("SYNCWATCH_STDLIB_MODULE_OK original named module and source-built KotlinVersion");
    }
}
