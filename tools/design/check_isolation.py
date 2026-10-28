"""Require screen bindings to consume the declarative library, not construct native designs."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
# The Linux popup host is a focused part of the primitive adapter: it renders
# document-provided content above heavyweight native media, without screen data.
ADAPTERS = {"macos/DesignSurface.swift", "windows/DesignSurface.cs", "linux/DesignSurface.kt",
            "linux/NativeDesignPopover.kt"}
PRIMITIVES = {
    ".swift": [r"\b(?:HStack|VStack|ZStack|GeometryReader|Text|Button|Slider|Toggle|Picker|Menu|ScrollView|Spacer|Color|RoundedRectangle|Circle|Path|DesignNode)\s*(?:\(|\{)", r"\.(?:frame|padding|font|foregroundStyle|background|clipShape|overlay|offset|opacity|buttonStyle|toggleStyle)\s*\("],
    ".cs": [r"\bnew\s+(?:Grid|StackPanel|Border|TextBlock|TextBox|Button|Slider|CheckBox|ComboBox|Canvas|Viewbox|SolidColorBrush|Thickness|CornerRadius|Window|DesignNode)\b", r"\.(?:Width|Height|MinWidth|MinHeight|FontSize|FontWeight|FontFamily|Margin|Padding|Foreground|Background|BorderBrush|BorderThickness|CornerRadius|Opacity)\s*="],
    ".kt": [r"\b(?:Row|Column|Box|BoxWithConstraints|BasicText|BasicTextField|Canvas|Popup|Spacer|Color|DesignNode)\s*(?:\(|\{)", r"\.(?:size|width|height|widthIn|heightIn|padding|background|border|clip|alpha|offset)\s*\("],
}


def check(root: Path = ROOT) -> list[str]:
    errors = []
    for platform in ("macos", "windows", "linux"):
        for path in sorted((root / "packages/design" / platform).rglob("*")):
            if path.suffix not in PRIMITIVES or path.relative_to(root / "packages/design").as_posix() in ADAPTERS:
                continue
            source = path.read_text()
            for pattern in PRIMITIVES[path.suffix]:
                for match in re.finditer(pattern, source):
                    line = source.count("\n", 0, match.start()) + 1
                    errors.append(f"{path.relative_to(root)}:{line}: native design belongs in layouts.json and the primitive adapter")
    return errors


def main() -> None:
    errors = check()
    if errors:
        raise SystemExit("\n".join(errors))
    print("All screen/model bindings are isolated from native layout, palette and typography construction")


if __name__ == "__main__":
    main()
