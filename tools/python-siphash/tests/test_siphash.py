"""Original known answers, source/notice boundaries, corpus and restored-payload rejection."""

import copy
import io
from pathlib import Path
import platform
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from siphash_profile import COMPONENT, ROOT, analyze, digest, original_archive, profile_data, read_sources, validate
from siphash_oracle import KEYS, corpus_header, seeded_key, siphash, source_answers, transcript
from native_siphash import fixture, fragments
from siphash_build import materialize, payload_files, verify_files
from c_probe import compile_transcript


class SipHashTests(unittest.TestCase):
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
            self.assertEqual(len(archive.namelist()), 10)
            for origin, files in self.sources.items():
                for name, data in files.items():
                    self.assertEqual(archive.read(origin + "/" + name), data)
        for origin, source in self.profile["sources"].items():
            for name in source["notices"]:
                self.assertEqual(self.payload["notices/" + source["path"].split("/")[-1] + "/" + name], self.sources[origin][name])

    def test_both_original_known_answer_sets_and_invalid_parameters(self):
        cases, answers = source_answers(self.sources)
        self.assertEqual((len(cases), len(answers["siphash24"])), (5, 64))
        self.assertEqual(siphash(b"", KEYS[0], 2, 4), 0x726FDB47DD0E0E31)
        self.assertEqual(siphash(b"abc", seeded_key(0), 1, 3), -4594863902769663758 & ((1 << 64) - 1))
        self.assertEqual(siphash(b"abc", seeded_key(42), 2, 4), -4501618152524544106 & ((1 << 64) - 1))
        for key, rounds in ((b"short", (1, 3)), (KEYS[0], (3, 4))):
            with self.assertRaisesRegex(ValueError, "parameters"):
                siphash(b"test", key, *rounds)

    def test_changed_original_known_answers_are_rejected(self):
        changed = copy.deepcopy(self.sources)
        changed["csiphash"]["test.c"] = changed["csiphash"]["test.c"].replace(b"0x726fdb47dd0e0e31", b"0x726fdb47dd0e0e30", 1)
        with self.assertRaisesRegex(ValueError, "original SipHash24 known answers"):
            source_answers(changed)
        changed = copy.deepcopy(self.sources)
        changed["cpython"]["Lib/test/test_hash.py"] = changed["cpython"]["Lib/test/test_hash.py"].replace(b"-4594863902769663758", b"-4594863902769663757")
        with self.assertRaisesRegex(ValueError, "original CPython known answers"):
            source_answers(changed)

    def test_frozen_corpus_transcript_and_unsigned_portable_C_data(self):
        self.assertEqual(transcript(self.sources), self.profile["transcript"])
        header = corpus_header(self.sources)
        self.assertEqual(digest(header), self.profile["corpusSha256"])
        self.assertTrue(header.isascii())
        self.assertIn(b"static const unsigned char fixture_keys", header)
        self.assertIn(b"#define FIXTURE_ALIGNMENTS 8", header)
        self.assertEqual(source_answers(self.sources)[0][-1][1], bytes.fromhex("e400fa0011220721"))

    def test_missing_notice_and_changed_original_attribution(self):
        for original, replacement in ((b"<MIT License>", b"<Missing notice>"),
                                      (b"Copyright (c) 2013", b"Copyright (c) 2014"),
                                      (b"Modified for Python by Christian Heimes:", b"Removed attribution:")):
            changed = copy.deepcopy(self.sources)
            changed["cpython"]["Python/pyhash.c"] = changed["cpython"]["Python/pyhash.c"].replace(original, replacement)
            with self.assertRaisesRegex(ValueError, "notice|attribution"):
                analyze(changed)

    def test_original_native_fragment_missing_or_ambiguous(self):
        content, _hashes = fixture(self.sources["cpython"])
        self.assertIn(fragments(self.sources["cpython"])["attribution"], content)
        self.assertEqual(set(fragments(self.sources["cpython"])), {"attribution", "pointerType", "sizeType", "algorithmConstants", "algorithms"})
        for name in ("Include/pyport.h", "Include/pyhash.h", "Python/pyhash.c"):
            for replacement in (b"", self.sources["cpython"][name] * 2):
                changed = dict(self.sources["cpython"])
                changed[name] = replacement
                with self.assertRaisesRegex(ValueError, "Missing or ambiguous"):
                    fragments(changed)

    def test_changed_sources_and_full_notices_are_rejected(self):
        for origin, name in (("csiphash", "README.md"), ("csiphash", "csiphash.c"), ("cpython", "LICENSE")):
            changed = copy.deepcopy(self.sources)
            changed[origin][name] += b"\n"
            with self.assertRaisesRegex(ValueError, "source or full notice"):
                validate(changed, self.profile)

    def test_cached_proof_analysis_and_missing_notice_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            materialize(root, self.payload)
            verify_files(root, self.payload)
            for name in ("build-report.json", "source-analysis.json", "notices/csiphash/csiphash.c"):
                path = root / name
                path.write_bytes(path.read_bytes() + b"\n")
                with self.assertRaisesRegex(ValueError, "differs"):
                    verify_files(root, self.payload)
                path.write_bytes(self.payload[name])
            (root / "notices/cpython/LICENSE").unlink()
            with self.assertRaisesRegex(ValueError, "missing or unexpected"):
                verify_files(root, self.payload)

    def test_extra_and_symlink_payload_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            materialize(root, self.payload)
            extra = root / "unknown"
            extra.write_bytes(b"extra")
            with self.assertRaisesRegex(ValueError, "differs"):
                verify_files(root, self.payload)
            extra.unlink()
            try:
                extra.symlink_to(root / "sources.zip")
            except OSError:
                self.skipTest("This account cannot create symbolic links")
            with self.assertRaisesRegex(ValueError, "symbolic links"):
                verify_files(root, self.payload)

    def test_shared_native_boundary_rejects_unbounded_or_escaping_configuration(self):
        for size in (0, 64 * 1024 * 1024 + 1):
            with self.assertRaisesRegex(ValueError, "size"):
                compile_transcript(Path("unused"), {}, {"bytes": size}, "unused", [])
        for name in ("../escape.h", "/escape.h", "", "back\\slash.h"):
            with self.assertRaisesRegex(ValueError, "filenames"):
                compile_transcript(Path("unused"), {name: b""}, {"bytes": 1}, "unused", [])


if __name__ == "__main__":
    unittest.main()
