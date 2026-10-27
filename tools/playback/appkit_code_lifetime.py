"""Check the native AppKit module owner against real authored Mach-O bundles."""

from pathlib import Path
import shutil
import sys
import tempfile


def check(context, output):
    if sys.platform != "darwin":
        raise ValueError("AppKit module checks require macOS")
    root = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix="appkit-code-", dir=output) as temporary:
        work = Path(temporary)
        libraries = []
        for name in ("missing", "selected", "foreign"):
            folder = work / name / "lib"
            folder.mkdir(parents=True)
            library = folder / "libvlc.dylib"
            library.touch()
            libraries.append(library)
        plugin = libraries[1].parent / "vlc/plugins/selected/libvout_macosx_plugin.dylib"
        plugin.parent.mkdir(parents=True)
        source = work / "authored.c"
        source.write_text("int fixture_identity(void) { return 1; }\n")
        compiler = context.tool(context.env["CC"])
        for index, bundle in enumerate((plugin, work / "ordinary.dylib")):
            context.run("appkit-authored-bundle-" + str(index), [compiler, "-bundle", str(source), "-o", str(bundle)], timeout=30)
        foreign = libraries[2].parent / "vlc/plugins/selected/libvout_macosx_plugin.dylib"
        foreign.parent.mkdir(parents=True)
        shutil.copy2(plugin, foreign)
        alias = work / "alias.dylib"
        alias.symlink_to(libraries[1])
        probe = work / "probe"
        context.run("appkit-module-owner", [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                    str(root / "tools/playback/appkit_module_probe.c"),
                    str(root / "packages/playback-native/src/library.c"), "-o", str(probe)], timeout=30)
        context.run("appkit-module-lifetime", [str(probe), str(libraries[0]), str(libraries[1]),
                    str(plugin), str(alias), str(libraries[2]), str(work / "ordinary.dylib")], timeout=30)
