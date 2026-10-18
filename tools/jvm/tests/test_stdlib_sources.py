import copy
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stdlib_sources as stdlib


class StdlibSourcesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.files = {"Example.kt": b"/* Copyright Fixture. Apache 2.0 license. */\npackage example\n",
                      "license/README.md": b"applies to all code in this repository which is copyright by Fixture\n"}
        self.profile = {"roles": {"common": ["Example.kt"]}, "repositoryLicensedFiles": []}
        self.specification = {"revision": "a" * 40, "files": {n: stdlib.digest(d) for n, d in self.files.items()}}
        for n, d in self.files.items():
            path = self.source / n
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(d)

    def archive(self, revision, extra=None):
        path = self.root / "source.tar"
        with tarfile.open(path, "w", format=tarfile.PAX_FORMAT, pax_headers={"comment": revision}) as output:
            for n, d in self.files.items():
                item = tarfile.TarInfo(n)
                item.size = len(d)
                output.addfile(item, io.BytesIO(d))
            if extra:
                output.addfile(extra)
        return path

    def test_directory_and_pinned_archive_have_identical_reviewed_bytes(self):
        self.assertEqual(stdlib.source_files(self.source, self.specification), self.files)
        self.assertEqual(stdlib.source_files(self.archive("a" * 40), self.specification), self.files)

    def test_rewritten_missing_and_extra_source_files_fail(self):
        path = self.source / "Example.kt"
        path.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "digest changed"):
            stdlib.source_files(self.source, self.specification)
        path.unlink()
        with self.assertRaisesRegex(ValueError, "file inventory"):
            stdlib.source_files(self.source, self.specification)
        path.write_bytes(self.files["Example.kt"])
        (self.source / "Unexpected.java").write_bytes(b"extra")
        with self.assertRaisesRegex(ValueError, "file inventory"):
            stdlib.source_files(self.source, self.specification)

    def test_wrong_archive_commit_duplicate_and_link_fail(self):
        with self.assertRaisesRegex(ValueError, "Git revision"):
            stdlib.source_files(self.archive("b" * 40), self.specification)
        for item in (tarfile.TarInfo("Example.kt"), tarfile.TarInfo("link")):
            if item.name == "link":
                item.type = tarfile.SYMTYPE
                item.linkname = "Example.kt"
            with self.subTest(name=item.name), self.assertRaisesRegex(ValueError, "unique regular files"):
                stdlib.source_files(self.archive("a" * 40, item), self.specification)

    def test_header_forms_and_reviewed_exceptions(self):
        stdlib.check_licenses(self.files, self.profile)
        self.files["Example.kt"] = b"  /* Licensed under the Apache License, Version 2.0. */"
        stdlib.check_licenses(self.files, self.profile)
        self.files["Example.kt"] = b"package example"
        with self.assertRaisesRegex(ValueError, "headers differ"):
            stdlib.check_licenses(self.files, self.profile)
        self.profile["repositoryLicensedFiles"] = ["Example.kt"]
        stdlib.check_licenses(self.files, self.profile)
        self.files["license/README.md"] = b"removed declaration"
        with self.assertRaisesRegex(ValueError, "repository-wide"):
            stdlib.check_licenses(self.files, self.profile)

    def test_missing_duplicate_and_extra_code_roles_fail(self):
        for roles in ({}, {"a": ["Example.kt"], "b": ["Example.kt"]}, {"a": ["Unexpected.kt"]}):
            with self.subTest(roles=roles), self.assertRaisesRegex(ValueError, "exact selected code"):
                stdlib.check_licenses(self.files, self.profile | {"roles": roles})

    def test_titlecase_evaluation_uses_data_lowercase_and_excludes_contextual_rules(self):
        # Synthetic records: N lowercases to n; the host Unicode version is irrelevant.
        fields = ["004E", "FIXTURE", "Lu", "0", "L", "", "", "", "", "N", "", "", "", "006E", ""]
        data = (";".join(fields) + "\n").encode()
        special = b"0149; 0149; 02BC 004E; 02BC 004E; # fixture\n0049; 0069; 0049; 0049; tr; # conditional\n"
        self.assertEqual(stdlib.titlecase_mappings(data, special), {"0149": ["02BC", "004E"]})
        self.assertEqual(stdlib.titlecase_mappings(data, b"0041; 0061; 0041 006E; 0041 004E;\n"), {})

    def test_invalid_duplicate_and_disagreeing_unicode_records_fail(self):
        for data, special, error in [(b"invalid\n", b"", "Invalid UnicodeData"),
                                     (b"", b"0149; 0149; 02BC 004E; 02BC 004E;\n" * 2, "Unreviewed"),
                                     (b"", b"0041; 0061; 0042; 0043;\n", "disagree"),
                                     (b"", b"10000; 10000; 0041 0042; 0043;\n", "Unreviewed")]:
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                stdlib.titlecase_mappings(data, special)

    def test_unicode_publication_version_and_mapping_checks_cannot_be_hidden_by_rehashing_source(self):
        profile = json.loads((stdlib.ROOT / "tools/jvm/stdlib_sources.json").read_text())
        unicode = {item["source"]: b"modified" for item in profile["unicodePublication"]["files"].values()}
        with self.assertRaisesRegex(ValueError, "published release"):
            stdlib.unicode_report({}, unicode, profile)
        for item in profile["unicodePublication"]["files"].values():
            item["sha256"] = stdlib.digest(b"modified")
        with self.assertRaisesRegex(ValueError, "generator version"):
            stdlib.unicode_report({stdlib.GENERATOR: b"wrong version"}, unicode, profile)
        with self.assertRaisesRegex(ValueError, "SpecialCasing version"):
            stdlib.unicode_report({stdlib.GENERATOR: b'private const val unicodeVersion = "13.0.0"'}, unicode, profile)

    def test_source_artifact_is_reverified_against_exact_bytes_and_notices(self):
        expected = {"sources.zip": b"source bytes", "notices/LICENSE": b"complete license"}
        for n, d in expected.items():
            path = self.root / "payload" / n
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(d)
        stdlib.verify(self.root / "payload", expected)
        (self.root / "payload/notices/LICENSE").write_bytes(b"truncated")
        with self.assertRaisesRegex(ValueError, "complete notices changed"):
            stdlib.verify(self.root / "payload", expected)
        (self.root / "payload/notices/LICENSE").unlink()
        with self.assertRaisesRegex(ValueError, "missing or unexpected"):
            stdlib.verify(self.root / "payload", expected)

    def test_changed_generated_function_and_mapping_set_fail(self):
        profile = json.loads((stdlib.ROOT / "tools/jvm/stdlib_sources.json").read_text())
        unicode = {item["source"]: (b"# SpecialCasing-13.0.0.txt\n" if n == "SpecialCasing.txt" else b"fixture")
                   for n, item in profile["unicodePublication"]["files"].items()}
        for item in profile["unicodePublication"]["files"].values():
            item["sha256"] = stdlib.digest(unicode[item["source"]])
        kotlin = {stdlib.GENERATOR: b'private const val unicodeVersion = "13.0.0"', stdlib.GENERATED: b"changed function"}
        with patch.object(stdlib, "titlecase_mappings", return_value=profile["titlecaseMappings"]):
            with self.assertRaisesRegex(ValueError, "Committed Kotlin titlecase function"):
                stdlib.unicode_report(kotlin, unicode, profile)
        with patch.object(stdlib, "titlecase_mappings", return_value={}):
            with self.assertRaisesRegex(ValueError, "mapping.*inventory"):
                stdlib.unicode_report(kotlin, unicode, profile)

    def test_profile_source_license_exports_and_reachability_match_the_registry(self):
        original = stdlib.ROOT
        profile = json.loads((original / "tools/jvm/stdlib_sources.json").read_text())
        registry = json.loads((original / "tools/dependencies/components.json").read_text())
        for name, data in [("tools/jvm/stdlib_sources.json", profile), ("tools/dependencies/components.json", registry)]:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data))
        for key, value in [("revision", "f" * 40), ("license", "unknown"), ("exports", ["compiler"]), ("requires", [])]:
            altered = copy.deepcopy(registry)
            altered["components"][stdlib.COMPONENT]["sources"]["3rdparty/kotlin-stdlib"][key] = value
            (self.root / "tools/dependencies/components.json").write_text(json.dumps(altered))
            with self.subTest(key=key), patch.object(stdlib, "ROOT", self.root), self.assertRaisesRegex(ValueError, "registered graph"):
                stdlib.profile_data()
        (self.root / "tools/dependencies/components.json").write_text(json.dumps(registry))
        with patch.object(stdlib, "ROOT", self.root):
            self.assertEqual(stdlib.profile_data(), profile)
        profile["binaryReady"] = True
        (self.root / "tools/jvm/stdlib_sources.json").write_text(json.dumps(profile))
        with patch.object(stdlib, "ROOT", self.root), self.assertRaisesRegex(ValueError, "source-only"):
            stdlib.profile_data()


if __name__ == "__main__":
    unittest.main()
