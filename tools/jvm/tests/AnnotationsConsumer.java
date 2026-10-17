import java.util.List;
import org.intellij.lang.annotations.Language;
import org.jetbrains.annotations.Contract;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;

final class AnnotationsConsumer {
    @Contract("null -> null; !null -> !null")
    static @Nullable String identity(@Nullable String value) {
        return value;
    }

    static @NotNull String first(List<@NotNull String> values) {
        @Language("SQL") String query = "select 1";
        return values.isEmpty() ? query : values.get(0);
    }
}
