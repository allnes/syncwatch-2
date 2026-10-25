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

    def test_unlinked_object_package_cannot_claim_runtime_acceptance(self):
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

    def test_ambient_header_and_linker_paths_do_not_override_source_owners(self):
        with tempfile.TemporaryDirectory() as work:
            with patch.dict(os.environ, {"CPATH": "/foreign/include", "LIBRARY_PATH": "/foreign/lib"}):
                context = native_objects.Context(Path(work), self.profile)
            self.assertNotIn("CPATH", context.env)
            self.assertNotIn("LIBRARY_PATH", context.env)
            self.assertEqual(context.env["GIT_NO_LAZY_FETCH"], "1")

    def test_system_x11_and_zlib_headers_are_not_compiler_sdk_inputs(self):
        for path in ("/usr/include/X11/Xlib.h", "/usr/include/zlib.h", "/usr/include/unicode/uchar.h"):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "undeclared application header"):
                header_scope.verify([path], set(), [], Path("/sdk/gcc/include"), Path("/sdk/jdk/include"))


if __name__ == "__main__":
    unittest.main()
