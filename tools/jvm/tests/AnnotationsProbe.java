import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.nio.file.Paths;
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;
import org.intellij.lang.annotations.Language;
import org.jetbrains.annotations.Contract;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;

final class AnnotationsProbe {
    private static int assertions;

    private static void check(boolean condition) {
        if (!condition) throw new AssertionError("Annotations API assertion " + (assertions + 1));
        assertions++;
    }

    public static void main(String[] arguments) throws Exception {
        check(NotNull.class.isAnnotation());
        check(NotNull.class.getAnnotation(Retention.class).value() == RetentionPolicy.CLASS);
        check(Nullable.class.getAnnotation(Retention.class).value() == RetentionPolicy.CLASS);
        Set<ElementType> targets = Arrays.stream(NotNull.class.getAnnotation(Target.class).value()).collect(Collectors.toSet());
        check(targets.contains(ElementType.TYPE_USE));
        check(targets.contains(ElementType.PARAMETER));
        check(NotNull.class.getMethod("value").getDefaultValue().equals(""));
        check(NotNull.class.getMethod("exception").getDefaultValue() == Exception.class);
        check(Contract.class.getMethod("pure").getDefaultValue().equals(false));
        check(Language.class.getMethod("prefix").getDefaultValue().equals(""));
        check(Language.class.getMethod("suffix").getDefaultValue().equals(""));
        ModuleDescriptor module = ModuleFinder.of(Paths.get(arguments[0])).find("org.jetbrains.annotations").orElseThrow(AssertionError::new).descriptor();
        check(module.name().equals("org.jetbrains.annotations"));
        check(!module.isAutomatic());
        check(module.exports().stream().map(ModuleDescriptor.Exports::source).collect(Collectors.toSet()).equals(Set.of("org.jetbrains.annotations", "org.intellij.lang.annotations")));
        check(module.requires().stream().anyMatch(r -> r.name().equals("java.desktop") && r.modifiers().contains(ModuleDescriptor.Requires.Modifier.STATIC)));
        System.out.println("Verified " + assertions + " compiled annotation/JPMS API assertions");
    }
}
