import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configuration import unix_setup, windows_setup, relocatable_makefile
from source_profile import ROOT, profile_data, read_sources, validate
from runtime_package import inventory, verify


class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = profile_data()
        target = "windows-x64" if sys.platform == "win32" else "macos-arm64" if sys.platform == "darwin" else "linux-x64"
        cls.sources = read_sources({n: ROOT / "artifacts/dependencies/cpython-embedded" / target / (n + ".tar")
                                   for n in ["cpython", "zlib"]}, cls.profile)

    def test_original_grants_cannot_be_replaced_by_a_short_label(self):
        sources = copy.deepcopy(self.sources); profile = copy.deepcopy(self.profile)
        from source_profile import digest
        sources["cpython"]["Python/dtoa.c"] = b"SPDX-License-Identifier: LicenseRef-Lucene\n"
        profile["source"]["files"]["Python/dtoa.c"] = digest(sources["cpython"]["Python/dtoa.c"])
        with self.assertRaisesRegex(ValueError, "complete grant"):
            validate(sources, profile)

    def test_unix_configuration_disables_ambient_optional_extensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / "source"; (source / "Modules").mkdir(parents=True)
            (source / "Modules/Setup.stdlib.in").write_bytes(self.sources["cpython"]["Modules/Setup.stdlib.in"])
            unix_setup(source, root / "build", root / "zlib", root / "libz.a", self.profile)
            text = (root / "build/Modules/Setup.local").read_text()
            self.assertIn("zlib zlibmodule.c -DZ_PREFIX ", text)
            self.assertNotIn("-DZ_PREFIX=", text)
            disabled = text.split("*disabled*\n")[1].splitlines()
            self.assertIn("_ssl", disabled); self.assertIn("_ctypes", disabled)
            self.assertNotIn("array", disabled)

    def test_windows_keeps_import_bootstrap_and_freeze_dependencies(self):
        import xml.etree.ElementTree as ET
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            for name in ["Modules/Setup.bootstrap.in", "PC/config.c", "PCbuild/pythoncore.vcxproj", "PCbuild/pcbuild.proj",
                         "PCbuild/_socket.vcxproj", "PCbuild/select.vcxproj"]:
                path = source / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(self.sources["cpython"][name])
            windows_setup(source, self.profile)
            config = (source / "PC/config.c").read_text()
            self.assertIn('{"_imp", PyInit__imp}', config)
            self.assertIn('{"_string", PyInit__string}', config)
            self.assertNotIn('{"_random",', config)
            ns = {"m": "http://schemas.microsoft.com/developer/msbuild/2003"}
            tree = ET.parse(source / "PCbuild/pcbuild.proj")
            self.assertIsNotNone(tree.find(".//m:FreezeProjects[@Include='_freeze_module.vcxproj']", ns))
            self.assertIsNotNone(tree.find(".//m:FreezeProjects/m:BuildTarget", ns))

    def test_mac_library_owns_static_dependencies_and_rejects_unresolved_symbols(self):
        with tempfile.TemporaryDirectory() as tmp:
            build = Path(tmp)
            (build / "Makefile").write_text('-Wl,-install_name,$(prefix)/lib/libpython$(LDVERSION).dylib\n'
                '$(DTRACE_OBJS) $(SHLIBS) $(LIBC) $(LIBM);\n-undefined dynamic_lookup -Wl,-install_name,\n'
                '-DVPATH=\'"$(VPATH)"\'\n')
            relocatable_makefile(build, "macos-arm64")
            text = (build / "Makefile").read_text()
            self.assertIn("$(MODLIBS)", text); self.assertIn("-Wl,-undefined,error", text)
            self.assertIn('@rpath/libpython', text); self.assertIn('"../cpython"', text)

    def test_missing_extra_and_corrupt_payload_fail_before_native_execution(self):
        sdk = {"target": "linux-x64"}
        from source_profile import digest, encoded
        for operation in ["missing", "extra", "corrupt"]:
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); original = root / "library"; original.write_bytes(b"original")
                report = {"schemaVersion": 1, "sdk": sdk, "profileSha256": digest(encoded(self.profile)),
                          "pinnedRuntimeBuilt": True, "pinnedEmbeddingAbiVerified": True,
                          "syncplayRuntimeReady": False, "files": inventory(root)}
                (root / "build-report.json").write_bytes(encoded(report))
                if operation == "missing": original.unlink()
                elif operation == "extra": (root / "extra").write_bytes(b"extra")
                else: original.write_bytes(b"corrupt!")
                with patch("runtime_package.relocated_probe") as native:
                    with self.assertRaisesRegex(ValueError, "missing, extra or changed"):
                        verify(root, self.sources, self.profile, sdk, [])
                    native.assert_not_called()


if __name__ == "__main__":
    unittest.main()
