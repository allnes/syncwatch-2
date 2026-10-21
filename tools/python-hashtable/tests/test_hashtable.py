"""Original source/notices, explicit probe ports, oracle and cache boundaries."""

import copy
import io
from pathlib import Path
import platform
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hashtable_profile import COMPONENT, ROOT, analyze, digest, original_archive, profile_data, read_sources, validate
from hashtable_oracle import corpus_header, operations, transcript
from native_hashtable import fixture, fragments
from hashtable_build import materialize, payload_files, verify_files


class HashtableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = profile_data()
        target = {"Darwin": "macos-arm64", "Linux": "linux-x64", "Windows": "windows-x64"}[platform.system()]
        directory = ROOT / "artifacts/dependencies" / COMPONENT / target
        paths = {name: directory / (Path(source["path"]).name + ".tar") for name, source in cls.profile["sources"].items()}
        cls.sources = read_sources(paths, cls.profile)
        cls.payload = payload_files(cls.sources, cls.profile, {"testFixture": True})

    def test_original_source_archive_and_complete_notices(self):
        validate(self.sources, self.profile)
        with zipfile.ZipFile(io.BytesIO(original_archive(self.sources))) as archive:
            self.assertEqual(len(archive.namelist()), 12)
            for origin, files in self.sources.items():
                for name, data in files.items():
                    self.assertEqual(archive.read(origin + "/" + name), data)
        for origin, source in self.profile["sources"].items():
            for name in source["notices"]:
                self.assertEqual(self.payload["notices/" + source["path"].split("/")[-1] + "/" + name], self.sources[origin][name])

    def test_independent_dictionary_transcript_and_explicit_corpus(self):
        self.assertEqual(transcript(), self.profile["transcript"])
        self.assertEqual(digest(corpus_header()), self.profile["corpusSha256"])
        self.assertEqual(operations()[:256], [(0, n) for n in range(256)])
        self.assertEqual(operations()[256:512], [(1, n) for n in range(256)])
        self.assertIn((3, 0), operations())
        self.assertTrue(corpus_header().isascii())

    def test_complete_original_body_and_declarations_remain_unchanged(self):
        pieces = fragments(self.sources["cpython"])
        content, hashes = fixture(self.sources["cpython"])
        self.assertEqual(len(pieces), 9)
        for name, data in pieces.items():
            self.assertIn(data, content)
            self.assertEqual(hashes[name], digest(data))
        self.assertTrue(pieces["implementation"].endswith(b"ht->alloc.free(ht);\n}\n"))
        self.assertIn(b"#define PyMem_Malloc malloc", content)
        self.assertNotIn(b'#include "Python.h"', content)

    def test_missing_or_ambiguous_original_fragments_rejected(self):
        for name in ["Include/pyport.h", "Include/pymacro.h", "Python/pyhash.c", "Python/hashtable.c"]:
            for replacement in [b"", self.sources["cpython"][name] * 2]:
                changed = dict(self.sources["cpython"]); changed[name] = replacement
                with self.assertRaisesRegex(ValueError, "Missing or ambiguous"):
                    fragments(changed)

    def test_changed_original_bsd_notice_is_rejected(self):
        for origin, name in [("cpython", "Python/hashtable.c"), ("libcfu", "src/cfuhash.c"), ("libcfu", "src/cfuhash.h")]:
            changed = copy.deepcopy(self.sources)
            changed[origin][name] = changed[origin][name].replace(b"2005 Don Owens", b"2006 Don Owens")
            with self.assertRaisesRegex(ValueError, "origin notice"):
                analyze(changed)

    def test_changed_source_or_full_notice_is_rejected(self):
        for origin, name in [("libcfu", "COPYING"), ("libcfu", "AUTHORS"), ("cpython", "LICENSE"), ("cpython", "Python/hashtable.c")]:
            changed = copy.deepcopy(self.sources); changed[origin][name] += b"\n"
            with self.assertRaisesRegex(ValueError, "source or full notice"):
                validate(changed, self.profile)

    def test_corrupt_restored_proof_analysis_or_notice_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); materialize(root, self.payload); verify_files(root, self.payload)
            for name in ["build-report.json", "source-analysis.json", "notices/libcfu/COPYING"]:
                path = root / name; path.write_bytes(path.read_bytes() + b"\n")
                with self.assertRaisesRegex(ValueError, "differs"):
                    verify_files(root, self.payload)
                path.write_bytes(self.payload[name])
            (root / "notices/cpython/LICENSE").unlink()
            with self.assertRaisesRegex(ValueError, "missing or unexpected"):
                verify_files(root, self.payload)

    def test_extra_file_and_symlink_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); materialize(root, self.payload)
            extra = root / "unexpected"; extra.write_bytes(b"extra")
            with self.assertRaisesRegex(ValueError, "differs"):
                verify_files(root, self.payload)
            extra.unlink()
            try:
                extra.symlink_to(root / "sources.zip")
            except OSError:
                self.skipTest("This account cannot create symbolic links")
            with self.assertRaisesRegex(ValueError, "symbolic links"):
                verify_files(root, self.payload)
