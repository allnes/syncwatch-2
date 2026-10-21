"""Source provenance, independent answers and rejected artifact/child-process cases."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/hashing"))
import fixtures
import hacl_build
import native_build
import source_profile as source


class HashChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = source.profile_data()
        directory = ROOT / "artifacts/dependencies/hacl-hash" / {"darwin": "macos-arm64", "win32": "windows-x64"}.get(sys.platform, "linux-x64")
        cls.sources = source.read_sources({name: directory / (name + ".tar") for name in cls.profile["sources"]}, cls.profile)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)

    def validate_mutation(self, origin, path, original, changed, message):
        sources = copy.deepcopy(self.sources)
        self.assertIn(original, sources[origin][path])
        sources[origin][path] = sources[origin][path].replace(original, changed)
        profile = copy.deepcopy(self.profile)
        profile["sourceArchiveSha256"] = source.digest(source.original_archive(sources))
        with self.assertRaisesRegex(ValueError, message):
            source.validate_sources(sources, profile)

    def test_original_selected_sources_and_notices(self):
        source.validate_sources(self.sources, self.profile)
        self.assertEqual(sum(map(len, self.sources.values())), 48)
        for name, spec in self.profile["sources"].items():
            for notice in spec["notices"]:
                self.assertTrue(self.sources[name][notice])

    def test_raw_source_change_fails_before_compile(self):
        sources = copy.deepcopy(self.sources)
        sources["hacl-star"]["dist/gcc-compatible/Hacl_Hash_MD5.c"] += b"\n"
        with self.assertRaisesRegex(ValueError, "archive differs"):
            source.validate_sources(sources, self.profile)

    def test_cpython_hacl_pin_correspondence(self):
        revision = self.profile["sources"]["hacl-star"]["revision"].encode()
        self.validate_mutation("cpython", "Modules/_hacl/refresh.sh", revision, b"0"*40, "different HACL")

    def test_cpython_compiled_source_selection(self):
        self.validate_mutation("cpython", "Modules/_hacl/refresh.sh", b"Hacl_Hash_MD5.c", b"Hacl_Hash_OTHER.c", "selection differs")

    def test_karamel_generation_pin_correspondence(self):
        revision = self.profile["sources"]["karamel"]["revision"].encode()
        self.validate_mutation("hacl-star", "dist/gcc-compatible/INFO.txt", revision, b"0"*40, "different KaRaMeL")

    def test_embedded_runtime_header_correspondence(self):
        path = next(iter(self.profile["karamelHaclCorrespondence"]))
        original = self.sources["karamel"][path][:20]
        self.validate_mutation("karamel", path, original, original+b" ", "vendor copy")

    def test_cited_embedded_endian_origin(self):
        self.validate_mutation("arduinolibs", "libraries/Crypto/utility/EndianUtil.h", b"#define htobe64(x)", b"#define missing(x)", "macro correspondence")

    def test_namespace_wraps_symbols_without_modifying_vendor_headers(self):
        headers = source.public_headers(self.sources, self.profile)
        mapping = headers["include/syncwatch_hacl_namespace.h"]
        for name in self.profile["requiredSymbols"]:
            self.assertIn(("#define " + name + " python_hashlib_" + name).encode(), mapping)
        for path, data in self.sources["hacl-star"].items():
            if path.startswith("dist/gcc-compatible/") and path.endswith(".h"):
                self.assertEqual(headers["include/"+path.removeprefix("dist/gcc-compatible/")], data)
        self.assertNotIn(b"#define Hacl_Hash_SHA3_SHA3_224 ", mapping)

    def test_frozen_answers_against_independent_sdk(self):
        vectors = fixtures.fixture_data(ROOT / "tools/hashing/vectors.json", self.profile["algorithms"])
        for data, answers in vectors:
            for suffix, expected in [(b"", answers[0]), (b"Z", answers[1])]:
                for name, value in zip(self.profile["algorithms"], expected):
                    state = hashlib.new(name, data+suffix)
                    self.assertEqual(state.hexdigest(192) if name.startswith("shake_") else state.hexdigest(), value)

    def test_corrupt_or_unbounded_fixture_rejected(self):
        original = json.loads((ROOT / "tools/hashing/vectors.json").read_text(encoding="utf-8"))
        changes = [lambda d: d.update(shakeBytes=16), lambda d: d.update(vectors=[]),
                   lambda d: d["vectors"][0].update(inputHex="01"),
                   lambda d: d["vectors"][1].update(inputHex="01"*4097),
                   lambda d: d["vectors"][0]["answers"].update(md5="00"),
                   lambda d: d["vectors"][0]["appended"].pop("sha256")]
        path = self.folder / "vectors.json"
        for change in changes:
            with self.subTest(change=change):
                data = copy.deepcopy(original); change(data)
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises(ValueError):
                    fixtures.header(path, self.profile["algorithms"])

    def test_payload_retains_full_notices_and_source_archive(self):
        result = hacl_build.payload_files(self.sources, self.profile, {"target":"macos-arm64"}, b"!<arch>\n", [], fixtures.expected_report(19))
        self.assertEqual(result["sources.zip"], source.original_archive(self.sources))
        for name, spec in self.profile["sources"].items():
            for notice in spec["notices"]:
                self.assertEqual(result["notices/"+name+"/"+notice], self.sources[name][notice])
        report = json.loads(result["build-report.json"])
        self.assertIs(report["runtimeReady"], False)
        self.assertIs(report["originalSourcesUnchanged"], True)
        self.assertEqual(report["files"], {k:source.digest(v) for k,v in result.items() if k!="build-report.json"})

    def test_missing_extra_or_modified_cache_file_rejected(self):
        expected = {"lib/library.a":b"archive", "notices/license":b"full notice"}
        for mode in ["missing", "extra", "modified"]:
            payload = self.folder / mode
            native_build.materialize(payload, expected)
            if mode == "missing": (payload / "notices/license").unlink()
            elif mode == "extra": (payload / "unreviewed.dll").write_bytes(b"extra")
            else: (payload / "lib/library.a").write_bytes(b"changed")
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                hacl_build.verify_files(payload, expected)

    def test_recompiled_archive_must_match_exactly(self):
        for actual in [b"changed", b"archive-extra", b""]:
            with self.subTest(actual=actual), self.assertRaisesRegex(ValueError, "archive bytes"):
                native_build.require_identical(b"archive", actual)

    def test_unprefixed_missing_or_failed_symbol_inventory_rejected(self):
        valid = b"\n".join(b"000000 T python_hashlib_"+s.encode() for s in self.profile["requiredSymbols"])
        for output, code in [(valid+b"\n000 T Hacl_other",0), (b"",0), (valid,1), (b"x"*(1024*1024+1),0)]:
            result = subprocess.CompletedProcess([], code, output, b"")
            with self.subTest(code=code, size=len(output)), patch.object(native_build.subprocess, "run", return_value=result), self.assertRaises(ValueError):
                native_build.inspect_symbols("nm", self.folder/"library.a", "linux-x64", self.profile)

    def test_native_symbol_formats_on_all_platforms(self):
        for target in ["macos-arm64", "windows-x64", "linux-x64"]:
            prefix = "_" if target=="macos-arm64" else ""
            symbols = sorted("python_hashlib_"+s for s in self.profile["requiredSymbols"])
            output = "\n".join("0000 T "+prefix+s for s in symbols).encode()
            with self.subTest(target=target), patch.object(native_build.subprocess, "run", return_value=subprocess.CompletedProcess([],0,output,b"")):
                self.assertEqual(native_build.inspect_symbols("tool", self.folder/"library", target, self.profile), symbols)

    def test_failed_oversized_or_inexact_probe_report_rejected(self):
        expected = fixtures.expected_report(19)
        wrong_bool = expected | {"copyResetAppend":1}
        cases = [(json.dumps(expected).encode(),1), (b"x"*4097,0), (b"invalid",0),
                 (json.dumps(wrong_bool).encode(),0), (json.dumps(expected|{"unexpected":True}).encode(),0)]
        for output, code in cases:
            with self.subTest(code=code, size=len(output)), patch.object(native_build.subprocess, "run", return_value=subprocess.CompletedProcess([],code,output,b"")), self.assertRaises(ValueError):
                native_build.probe(self.folder/"probe", expected)


if __name__ == "__main__":
    unittest.main()
