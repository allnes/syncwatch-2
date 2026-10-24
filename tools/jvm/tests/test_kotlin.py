"""Compiler SDK integrity and separation from application runtime inputs."""

import copy
from contextlib import nullcontext
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kotlin
from build_support import digest


class KotlinSdkTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data = {"kotlinc/lib/kotlin-compiler.jar": b"Fixture, never executed",
                     "kotlinc/license/LICENSE.txt": b"Complete fixture vendor legal notice"}
        self.spec = copy.deepcopy(kotlin.specification())
        self.spec["files"] = {n: digest(b) for n, b in self.data.items()}
        self.spec["compilerFiles"] = ["kotlinc/lib/kotlin-compiler.jar"]
        self.archive = self.root / "vendor.zip"
        with zipfile.ZipFile(self.archive, "w") as archive:
            for n, b in self.data.items():
                archive.writestr(n, b)
        self.sbom = self.root / "vendor.json"
        self.sbom.write_bytes(b'{"fixture":"vendor SBOM"}\n')
        for name, path in (("archive", self.archive), ("sbom", self.sbom)):
            self.spec[name] |= {"sha256": digest(path.read_bytes()), "bytes": path.stat().st_size}

    def install(self):
        return kotlin.provision(self.spec, self.root / "installed", self.archive, self.sbom)

    def test_offline_provision_and_reuse_preserve_complete_vendor_inputs(self):
        with patch.object(kotlin.urllib.request, "urlretrieve", side_effect=AssertionError("No network")):
            home = self.install()
            self.assertEqual(self.install(), home)
        for name, data in self.data.items():
            self.assertEqual((home / name).read_bytes(), data)
        self.assertEqual((home / kotlin.SBOM).read_bytes(), self.sbom.read_bytes())

    def test_archive_and_sbom_must_both_match_pins(self):
        for path in (self.archive, self.sbom):
            with self.subTest(path=path):
                before = path.read_bytes()
                path.write_bytes(before + b"modified")
                with self.assertRaisesRegex(ValueError, "differs from its pin"):
                    self.install()
                self.assertFalse((self.root / "installed/kotlin-2.3.20").exists())
                path.write_bytes(before)

    def test_cached_extra_missing_or_mutated_legal_and_compiler_files_fail(self):
        home = self.install()
        for name in [*self.data, kotlin.SBOM, "unexpected.jar"]:
            with self.subTest(name=name):
                path = home / name
                before = path.read_bytes() if path.exists() else None
                path.write_bytes(b"changed")
                with self.assertRaisesRegex(ValueError, "complete vendor files"):
                    kotlin.verify(home, self.spec)
                path.unlink()
                if before is not None:
                    with self.assertRaisesRegex(ValueError, "complete vendor files"):
                        kotlin.verify(home, self.spec)
                    path.write_bytes(before)

    def test_unapproved_download_origin_fails_before_network(self):
        self.spec["archive"]["url"] = "https://example.invalid/sdk.zip"
        with patch.object(kotlin.urllib.request, "urlretrieve") as download:
            with self.assertRaisesRegex(ValueError, "official release"):
                self.install()
            download.assert_not_called()

    def test_unsafe_duplicate_symlink_or_missing_members_fail(self):
        for name, mode in [("../escape", 0o100644), ("C:/escape", 0o100644), ("kotlinc/link", 0o120777),
                           ("kotlinc/lib/kotlin-compiler.jar", 0o100644), ("KOTLINC/lib/kotlin-compiler.jar", 0o100644)]:
            with self.subTest(name=name):
                stream = io.BytesIO()
                with zipfile.ZipFile(stream, "w") as archive:
                    archive.writestr("kotlinc/lib/kotlin-compiler.jar", self.data["kotlinc/lib/kotlin-compiler.jar"])
                    item = zipfile.ZipInfo(name)
                    item.external_attr = mode << 16
                    with self.assertWarns(UserWarning) if name == "kotlinc/lib/kotlin-compiler.jar" else nullcontext():
                        archive.writestr(item, b"x")
                with self.assertRaises(ValueError):
                    kotlin.extract(stream, self.root / "unpacked", self.spec)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("kotlinc/lib/kotlin-compiler.jar", self.data["kotlinc/lib/kotlin-compiler.jar"])
        with self.assertRaisesRegex(ValueError, "missing vendor files"):
            kotlin.extract(stream, self.root / "unpacked", self.spec)
        self.assertFalse((self.root / "escape").exists())

    def test_sdk_jars_cannot_become_target_runtime_or_classpath(self):
        for arguments in [["-include-runtime"], ["-kotlin-home", str(self.root)],
                          ["-include-runtime=true"], ["-kotlin-home=" + str(self.root)],
                          ["-Xplugin=" + str(self.root / "plugin.jar")], ["-P", "plugin:arbitrary:option=true"],
                          ["-classpath", str(self.root / "kotlinc/lib/kotlin-stdlib.jar")],
                          ["-classpath=" + str(self.root / "kotlinc/lib/kotlin-stdlib.jar")]]:
            with patch.object(kotlin, "java") as execute:
                with self.assertRaises(ValueError):
                    kotlin.compile(arguments, self.root, self.root, self.root)
                execute.assert_not_called()

    def test_named_plugins_use_only_their_exact_sdk_files(self):
        policy = kotlin.plugin_specification(kotlin.specification())
        for name in policy:
            data = ("Reviewed fixture compiler plugin " + name).encode()
            path = self.root / policy[name]["file"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            policy[name]["sha256"] = digest(data)
        with patch.object(kotlin, "plugin_specification", return_value=policy):
            self.assertEqual(kotlin.plugin_arguments((), self.root, self.spec), [])
            expected = ["-Xplugin=" + str(self.root / policy[n]["file"]) for n in sorted(policy)]
            self.assertEqual(kotlin.plugin_arguments(tuple(policy), self.root, self.spec), expected)
            for names in [("unreviewed",), ("compose", "compose"), "serialization"]:
                with self.subTest(names=names), self.assertRaises(ValueError):
                    kotlin.plugin_arguments(names, self.root, self.spec)
            for name in policy:
                path = self.root / policy[name]["file"]
                data = path.read_bytes()
                path.write_bytes(data + b"tampered")
                with self.subTest(plugin=name), self.assertRaisesRegex(ValueError, "exact SDK inventory"):
                    kotlin.plugin_arguments((name,), self.root, self.spec)
                path.unlink()
                with self.assertRaisesRegex(ValueError, "exact SDK inventory"):
                    kotlin.plugin_arguments((name,), self.root, self.spec)
                path.write_bytes(data)

    def test_plugins_require_the_sdk_source_revision_and_build_only_scope(self):
        import json
        spec = kotlin.specification()
        original = (kotlin.ROOT / "tools/jvm/compiler_plugins.json").read_text()
        for name in json.loads(original)["plugins"]:
            for key, value in [("scope", "runtime"), ("sourceRevision", "0" * 40),
                               ("sourcePath", "3rdparty/unreviewed"), ("sha256", "0" * 64)]:
                changed = json.loads(original)
                changed["plugins"][name][key] = value
                original_read = Path.read_text
                def read(path, *args, **kwargs):
                    return json.dumps(changed) if path.name == "compiler_plugins.json" else original_read(path, *args, **kwargs)
                with self.subTest(plugin=name, key=key), patch.object(Path, "read_text", read):
                    with self.assertRaisesRegex(ValueError, "reviewed SDK/source scope"):
                        kotlin.plugin_specification(spec)

    def test_argfiles_quote_paths_and_reject_record_injection(self):
        path = self.root / "arguments.txt"
        kotlin.argument_file(["#comment", "Синхронизация movie", 'C:\\some path\\quote".kt', "@literal"], path)
        self.assertEqual(path.read_text(encoding="utf-8"), '"#comment"\n"Синхронизация movie"\n"C:\\\\some path\\\\quote\\\".kt"\n"@literal"\n')
        for value in ["a\nb", "a\rb", "a\x00b"]:
            with self.assertRaises(ValueError):
                kotlin.argument_file([value], path)

    def test_long_unicode_compiler_inputs_are_read_by_the_utf8_tool_parser(self):
        sources = [str(self.root / "Кино 映画" / ("source-" + str(n) + ".kt")) for n in range(2400)]
        self.assertGreater(len(" ".join(sources)), 32767)
        def execute(command, directory, home):
            self.assertLess(len(" ".join(command)), 4096)
            self.assertTrue(command[-1].startswith("@"))
            self.assertTrue(command[-1].isascii())
            data = (directory / command[-1][1:]).read_text(encoding="utf-8")
            self.assertIn("Кино 映画", data)
            self.assertIn("source-2399.kt", data)
            self.assertIn('"-no-stdlib"', data)
            return "compiler fixture"
        with patch.object(kotlin, "java", side_effect=execute):
            self.assertEqual(kotlin.compile(sources, self.root, self.root, self.root), "compiler fixture")

    def test_launcher_classpath_uses_folded_ascii_file_uris_without_losing_paths(self):
        directory = self.root / "Кино 映画"
        directory.mkdir()
        paths = [directory, self.root / ("library " + "x" * 120 + ".jar")]
        def execute(command, **options):
            relative = command[command.index("-cp") + 1]
            self.assertTrue(relative.isascii())
            self.assertFalse(Path(relative).is_absolute())
            with zipfile.ZipFile(directory / relative) as archive:
                manifest = archive.read("META-INF/MANIFEST.MF")
            self.assertTrue(all(len(line) <= 70 for line in manifest.split(b"\r\n")))
            unfolded = manifest.replace(b"\r\n ", b"").decode("ascii")
            expected = "Class-Path: " + paths[0].resolve().as_uri() + "/ " + paths[1].resolve().as_uri() + "\r\n"
            self.assertIn(expected, unfolded)
            self.assertEqual(options["cwd"], directory)
            return "runtime fixture"
        with patch.object(kotlin.subprocess, "check_output", side_effect=execute):
            self.assertEqual(kotlin.java(["-cp", os.pathsep.join(map(str, paths)), "Fixture"], directory, self.root), "runtime fixture")


if __name__ == "__main__":
    unittest.main()
