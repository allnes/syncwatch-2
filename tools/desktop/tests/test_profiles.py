import copy
from pathlib import Path
import sys
import unittest
import os
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import generators
import native_sources
import native_objects
import header_scope


class NativeProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = native_sources.profile_data()

    def test_two_sources_cannot_own_the_same_staged_header(self):
        profile = copy.deepcopy(self.profile)
        left, right = profile["sources"]["desktop-libx11"], profile["sources"]["desktop-libxrandr"]
        right["stage"] = left["stage"]
        path = next(iter(left["files"]))
        right["files"][path] = left["files"][path]
        right["exports"] = sorted(right["files"])
        with self.assertRaisesRegex(ValueError, "overwrite"):
            native_sources.validate(profile)

    def test_original_grant_cannot_be_omitted_from_source_export(self):
        profile = copy.deepcopy(self.profile)
        source = profile["sources"]["skia-freetype"]
        del source["files"]["docs/FTL.TXT"]
        source["exports"] = sorted(source["files"])
        with self.assertRaisesRegex(ValueError, "grant inventory"):
            native_sources.validate(profile)

    def test_native_source_package_cannot_claim_application_acceptance(self):
        profile = copy.deepcopy(self.profile)
        profile["nativeRuntimeQualified"] = True
        with self.assertRaisesRegex(ValueError, "prematurely qualified"):
            native_sources.validate(profile)

    def test_raw_decoder_cannot_silently_reenter_the_selected_graph(self):
        profile = copy.deepcopy(self.profile)
        profile["gnArguments"].remove("skia_use_dng_sdk=false")
        with self.assertRaisesRegex(ValueError, "RAW photographic"):
            native_sources.validate(profile)

    def test_new_template_parameters_require_review(self):
        with self.assertRaisesRegex(ValueError, "parameters changed"):
            generators.substitute(b"@POINTER_SIZE@ @UNREVIEWED_ABI@", {"POINTER_SIZE": 8})

    def test_generated_headers_can_be_written_and_archived_as_bytes(self):
        dbus_markers = ("INT64_TYPE", "INT64_MODIFIER", "INT64_CONSTANT", "UINT64_CONSTANT", "INT32_TYPE",
                        "INT16_TYPE", "SIZEOF_VOID_P", "MAJOR_VERSION", "MINOR_VERSION", "MICRO_VERSION", "VERSION")
        originals = {
            "gn": {"build/gen.py": b"contents = '''%s %s %s''' % (mo.group(1), mo.group(1), mo.group(2))"},
            "fontconfig": {
                "meson.build": (b"cacheversion = 12\ncachemincompat = 9\ncachesnapversion = 0\n"
                                b"if cachesnapversion > 0\n  nextcacheversion = cacheversion + 1\n"
                                b"else\n  nextcacheversion = 0\nendif"),
                "fontconfig/fontconfig.h.in": b"@CACHE_VERSION@ @CACHE_MIN_COMPAT_VERSION@ @CACHE_SNAP_VERSION@ @NEXT_CACHE_VERSION@",
                "fontconfig/fcfreetype.h": b"/* synthetic public header */"},
            "desktop-dbus": {"meson.build": b"version: '1.16.2'",
                             "dbus/dbus-arch-deps.h.in": " ".join("@DBUS_" + m + "@" for m in dbus_markers).encode()}}
        generated = generators.headers(originals, self.profile)
        with tempfile.TemporaryDirectory() as work:
            for name, data in generated.items():
                self.assertIsInstance(data, bytes, name)
                native_objects.write(Path(work) / name, data)
                self.assertEqual((Path(work) / name).read_bytes(), data)
        self.assertEqual(generated["gn/last_commit_position.h"], b"2175 2175 b2afae122eeb")

    def test_ambient_header_and_linker_paths_do_not_override_source_owners(self):
        with tempfile.TemporaryDirectory() as work:
            with patch.dict(os.environ, {"CPATH": "/foreign/include", "LIBRARY_PATH": "/foreign/lib"}):
                context = native_objects.Context(Path(work), self.profile)
            self.assertNotIn("CPATH", context.env)
            self.assertNotIn("LIBRARY_PATH", context.env)
            self.assertEqual(context.env["GIT_NO_LAZY_FETCH"], "1")

    def test_system_x11_and_zlib_headers_are_not_compiler_sdk_inputs(self):
        for path in ("/usr/include/X11/Xlib.h", "/usr/include/zlib.h", "/usr/include/unicode/uchar.h",
                     "/usr/include/rpc/rpc.h", "/usr/lib/x86_64-linux-gnu/libX11.so"):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "undeclared application header"):
                header_scope.verify([path], set(), [], Path("/sdk/gcc/include"), Path("/sdk/jdk/include"))

    def test_automake_phony_and_empty_rules_do_not_become_header_paths(self):
        self.assertEqual(header_scope.make_paths(""), [])
        self.assertEqual(header_scope.make_paths("# dummy\n"), [])
        self.assertEqual(header_scope.make_paths("a.o: a.c \\\n a.h\na.h:\n"), ["a.c", "a.h"])

    def test_dynamic_loader_aliases_cannot_be_removed(self):
        profile = copy.deepcopy(self.profile)
        profile["runtimeLibraries"].remove("libdbus-1.so")
        with self.assertRaisesRegex(ValueError, "exact client"):
            native_sources.validate(profile)


if __name__ == "__main__":
    unittest.main()
