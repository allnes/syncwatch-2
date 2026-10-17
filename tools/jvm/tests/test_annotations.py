import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import annotations


class AnnotationsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name);self.source = self.root / "source";self.output = self.root / "payload"
        java = "src/jvmMain/java/fixture/Annotation.java"
        unheaded = "src/jvmMain/java/fixture/RepositoryLicensed.java"
        self.files = {java: b'/* Fixture copyright. Licensed under the Apache License, Version 2.0 */\npackage fixture;\n',
                      unheaded: b'package fixture;\n', "LICENSE.txt": b"Fixture license text\n",
                      "README.md": b"Fixture License-Apache%202.0 declaration\n", "gradle.properties": b"projectVersion=26.0.2\n", "build.gradle.kts": b"Fixture publishing declaration\n"}
        for name, data in self.files.items():
            p = self.source / name;p.parent.mkdir(parents=True, exist_ok=True);p.write_bytes(data)
        self.profile = {"schemaVersion": 1, "coordinate": "org.jetbrains:annotations:26.0.2", "sourcePath": "3rdparty/jvm-annotations",
                        "revision": "f" * 40, "license": "Apache-2.0", "javaRelease": 8, "moduleRelease": 9,
                        "sources": {n: annotations.digest(self.files[n]) for n in [java, unheaded]},
                        "notices": {n: annotations.digest(self.files[n]) for n in self.files if n not in [java, unheaded]},
                        "repositoryLicensedFiles": [unheaded]}
        common = {"META-INF/LICENSE.txt": self.files["LICENSE.txt"], "META-INF/UPSTREAM-README.md": self.files["README.md"],
                  "META-INF/THIRD-PARTY-NOTICES.txt": annotations.notices(self.files, self.profile),
                  "META-INF/source-inventory.json": annotations.encoded(annotations.metadata(self.profile, "fixture"))}
        products = {annotations.BINARY: annotations.jar_bytes({"fixture/Annotation.class": b"Fixture class bytes"} | common),
                    annotations.SOURCES: annotations.jar_bytes({n: self.files[n] for n in self.profile["sources"]} | common)}
        self.profile["expectedJars"] = {n: annotations.digest(d) for n, d in products.items()}
        for name, data in (products | annotations.support_files(self.files, self.profile, "fixture")).items():
            p = self.output / name;p.parent.mkdir(parents=True, exist_ok=True);p.write_bytes(data)

    def verify(self):
        return annotations.verify(self.output, self.files, self.profile, "fixture")

    def test_complete_notice_inventory_and_unmodified_source_jar_pass(self):
        self.assertEqual(annotations.source_files(self.source, self.profile), self.files)
        self.verify()

    def test_missing_notice_file_and_changed_source_inventory_fail(self):
        path = self.output / "THIRD-PARTY-NOTICES.txt";path.unlink()
        with self.assertRaisesRegex(ValueError, "missing or unexpected"):
            self.verify()
        path.write_bytes(annotations.notices(self.files, self.profile))
        (self.output / "source-inventory.json").write_bytes(b"{}")
        with self.assertRaisesRegex(ValueError, "source inventory changed"):
            self.verify()

    def test_changed_jar_fails_even_if_external_cache_manifest_was_rewritten(self):
        path = self.output / annotations.BINARY;path.write_bytes(path.read_bytes() + b"modified binary")
        with self.assertRaisesRegex(ValueError, "reviewed source/compiler output"):
            self.verify()

    def test_missing_embedded_license_fails_even_with_a_different_reviewed_jar_digest(self):
        path = self.output / annotations.BINARY
        with zipfile.ZipFile(path) as archive:entries = {n: archive.read(n) for n in archive.namelist() if n != "META-INF/LICENSE.txt"}
        path.write_bytes(annotations.jar_bytes(entries));self.profile["expectedJars"][annotations.BINARY] = annotations.digest(path.read_bytes())
        with self.assertRaises((ValueError, KeyError)):
            self.verify()

    def test_changed_source_bytes_or_unreviewed_extra_java_file_fail(self):
        name = next(iter(self.profile["sources"]));path = self.source / name;original = path.read_bytes();path.write_bytes(original + b"modified")
        with self.assertRaisesRegex(ValueError, "digest changed"):
            annotations.source_files(self.source, self.profile)
        path.write_bytes(original);(path.parent / "Unexpected.java").write_bytes(original)
        with self.assertRaisesRegex(ValueError, "reviewed inventory"):
            annotations.source_files(self.source, self.profile)

    def test_unreviewed_header_removal_cannot_be_hidden_by_rehashing(self):
        name = next(iter(self.profile["sources"]));path = self.source / name;path.write_bytes(b"package fixture;\n")
        self.profile["sources"][name] = annotations.digest(path.read_bytes())
        with self.assertRaisesRegex(ValueError, "Apache declaration"):
            annotations.source_files(self.source, self.profile)

    def test_archive_bytes_are_independent_of_insertion_order(self):
        first = annotations.jar_bytes({"b": b"second", "a": b"first"})
        self.assertEqual(first, annotations.jar_bytes({"a": b"first", "b": b"second"}))

    def test_source_archive_requires_the_exact_pinned_git_commit(self):
        for revision in (self.profile["revision"], "e" * 40, None):
            with self.subTest(revision=revision):
                archive = self.root / "source.tar"
                headers = {"comment": revision} if revision else {}
                with tarfile.open(archive, "w", format=tarfile.PAX_FORMAT, pax_headers=headers) as output:
                    for name, data in self.files.items():
                        member = tarfile.TarInfo(name)
                        member.size = len(data)
                        output.addfile(member, io.BytesIO(data))
                if revision == self.profile["revision"]:
                    self.assertEqual(annotations.source_files(archive, self.profile), self.files)
                else:
                    with self.assertRaisesRegex(ValueError, "different Git revision"):
                        annotations.source_files(archive, self.profile)

    def test_profile_revision_license_and_runtime_graph_must_match_registration(self):
        directory = self.root / "tools/jvm"
        directory.mkdir(parents=True)
        (directory / "annotations.json").write_text(json.dumps(self.profile))
        (directory / "toolchains.json").write_text(json.dumps({"version": "fixture"}))
        registry = self.root / "tools/dependencies/components.json"
        registry.parent.mkdir(parents=True)
        source = {"revision": self.profile["revision"], "license": self.profile["license"], "requires": []}
        for change in ({}, {"revision": "e" * 40}, {"license": "Different-License"}, {"requires": ["3rdparty/undeclared"]}):
            with self.subTest(change=change), patch.object(annotations, "ROOT", self.root):
                registry.write_text(json.dumps({"components": {"jvm-annotations": {"sources": {self.profile["sourcePath"]: source | change}}}}))
                if change:
                    with self.assertRaisesRegex(ValueError, "differs from the registered graph"):
                        annotations.profile_data()
                else:
                    self.assertEqual(annotations.profile_data(), (self.profile, {"version": "fixture"}))


if __name__ == "__main__":
    unittest.main()
