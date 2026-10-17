"""Exercise variant, version and integrity boundaries of the offline inspector."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "audit.py"
SPEC = importlib.util.spec_from_file_location("jvm_audit", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def dependency(name="example:leaf", fixed="1.0"):
    group, module = name.split(":")
    return {"group": group, "module": module, "version": {"requires": fixed}}


def module(identity="example:app:1.0", deps=()):
    group, name, fixed = identity.split(":")
    return {"formatVersion": "1.1", "component": {"group": group, "module": name, "version": fixed},
            "variants": [{"name": "jvmRuntime", "attributes": {"org.gradle.usage": "java-runtime",
                          "org.jetbrains.kotlin.platform.type": "jvm"}, "dependencies": list(deps)}]}


def pom(dependencies=""):
    return ('<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion>'
            '<groupId>example</groupId><artifactId>leaf</artifactId><version>1.0</version>'
            f'<dependencies>{dependencies}</dependencies></project>').encode()


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.inventory = {"schemaVersion": 1, "roots": ["example:app:1.0"],
                          "selections": {}, "metadata": {}}
        self.store("example:app:1.0", module(deps=[dependency()]))
        self.store("example:leaf:1.0", module("example:leaf:1.0"))

    def store(self, identity, value, kind="gradle"):
        data = json.dumps(value).encode() if kind == "gradle" else value
        relative = identity.replace(":", "-") + (".module" if kind == "gradle" else ".pom")
        (self.root / relative).write_bytes(data)
        self.inventory["metadata"][identity] = {"path": relative, "sha256": hashlib.sha256(data).hexdigest(), "format": kind}
        key, fixed = MODULE.coordinate(identity)
        self.inventory["selections"][key] = fixed

    def check(self):
        path = self.root / "inventory.json"
        path.write_text(json.dumps(self.inventory))
        return MODULE.audit(path)

    def test_actual_graph_is_offline_and_deterministic_across_inventory_order(self):
        with patch("socket.socket", side_effect=AssertionError("No network allowed")):
            first = self.check()
        self.inventory["metadata"] = dict(reversed(list(self.inventory["metadata"].items())))
        self.inventory["selections"] = dict(reversed(list(self.inventory["selections"].items())))
        self.assertEqual(first, self.check())
        self.assertEqual(first["nodes"][0]["dependencies"], ["example:leaf:1.0"])
        self.assertNotIn(str(self.root), json.dumps(first))

    def test_jvm_variant_does_not_follow_android_or_compile_dependencies(self):
        data = module(deps=[dependency()])
        for platform, usage in [("androidJvm", "java-runtime"), ("jvm", "java-api"), ("common", "kotlin-metadata")]:
            v = copy.deepcopy(data["variants"][0]);v["name"] = platform + usage
            v["attributes"] = {"org.gradle.usage": usage, "org.jetbrains.kotlin.platform.type": platform}
            v["dependencies"] = [dependency("example:wrong")];data["variants"].append(v)
        self.store("example:app:1.0", data)
        self.assertEqual(len(self.check()["nodes"]), 2)

    def test_mpp_redirect_follows_its_exact_platform_module(self):
        data = module();data["variants"][0]["available-at"] = {"group": "example", "module": "leaf", "version": "1.0", "url": "../leaf.module"}
        self.store("example:app:1.0", data)
        self.assertEqual(self.check()["nodes"][0]["redirect"], "example:leaf:1.0")

    def test_mpp_platform_metadata_owner_requires_matching_reverse_redirect(self):
        data = module();data["variants"][0]["available-at"] = {"group": "example", "module": "leaf", "version": "1.0"}
        self.store("example:app:1.0", data)
        child = module("example:app:1.0");child["component"]["url"] = "../app.module"
        self.store("example:leaf:1.0", child)
        self.assertEqual(self.check()["nodes"][1]["owner"], "example:app:1.0")
        self.store("example:app:1.0", module(deps=[dependency()]))
        with self.assertRaisesRegex(MODULE.AuditError, "does not redirect"):
            self.check()

    def test_redirect_cycle_is_rejected(self):
        for name, target in [("app", "leaf"), ("leaf", "app")]:
            data = module(f"example:{name}:1.0");data["variants"][0]["available-at"] = {"group": "example", "module": target, "version": "1.0"}
            self.store(f"example:{name}:1.0", data)
        with self.assertRaisesRegex(MODULE.AuditError, "Cyclic metadata redirect"):
            self.check()

    def test_dependency_cycle_terminates_without_losing_edges(self):
        self.store("example:leaf:1.0", module("example:leaf:1.0", [dependency("example:app")]))
        self.assertEqual(self.check()["nodes"][1]["dependencies"], ["example:app:1.0"])

    def test_missing_version_or_metadata_cannot_produce_a_closed_graph(self):
        for field in ["selections", "metadata"]:
            saved = copy.deepcopy(self.inventory)
            self.inventory[field].pop("example:leaf" if field == "selections" else "example:leaf:1.0")
            if field == "selections":
                self.inventory["metadata"].pop("example:leaf:1.0")
            with self.assertRaisesRegex(MODULE.AuditError, "Missing"):
                self.check()
            self.inventory = saved

    def test_mutated_metadata_and_wrong_identity_fail(self):
        path = self.root / self.inventory["metadata"]["example:leaf:1.0"]["path"]
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(MODULE.AuditError, "digest mismatch"):
            self.check()
        self.store("example:leaf:1.0", module("example:foreign:1.0"))
        with self.assertRaisesRegex(MODULE.AuditError, "identity mismatch"):
            self.check()

    def test_ambiguous_and_unknown_variant_rules_fail(self):
        data = module(deps=[dependency()]);data["variants"].append(copy.deepcopy(data["variants"][0]))
        self.store("example:app:1.0", data)
        with self.assertRaisesRegex(MODULE.AuditError, "unambiguous"):
            self.check()
        data["variants"].pop();data["variants"][0]["attributes"]["unreviewed-platform"] = "value"
        self.store("example:app:1.0", data)
        with self.assertRaisesRegex(MODULE.AuditError, "Unsupported JVM variant attributes"):
            self.check()

    def test_dynamic_and_snapshot_versions_fail(self):
        for fixed in ["1.+", "[1,2)", "latest.release", "1.0-SNAPSHOT", "${version}"]:
            with self.subTest(fixed=fixed), self.assertRaises(MODULE.AuditError):
                MODULE.coordinate("example:leaf:" + fixed)

    def test_explicit_stable_upgrade_honors_lower_bound_and_strict_constraints(self):
        MODULE.satisfies("2.0", {"requires": "1.9.9"})
        MODULE.satisfies("1.0.0", {"requires": "1.0"})
        MODULE.satisfies("2.0", {"requires": "[2.0]"})
        MODULE.satisfies("2.0", {"prefers": "3.0"})
        MODULE.satisfies("2.0", {"requires": "2.0-rc01"})
        for constraint in [{"strictly": "1.0"}, {"requires": "[1.0]"}, {"requires": "3.0"}, {"rejects": ["2.0"]}, {"requires": "3.0-RC1"}]:
            with self.subTest(constraint=constraint), self.assertRaises(MODULE.AuditError):
                MODULE.satisfies("2.0", constraint)

    def test_constraints_apply_only_to_reached_modules(self):
        data = module(deps=[dependency()]);v = data["variants"][0]
        v["dependencyConstraints"] = [dependency("example:unused", "2.0")]
        self.store("example:app:1.0", data);self.assertEqual(len(self.check()["nodes"]), 2)
        v["dependencyConstraints"].append(dependency(fixed="2.0"));self.store("example:app:1.0", data)
        with self.assertRaisesRegex(MODULE.AuditError, "below required"):
            self.check()

    def test_capabilities_exclusions_and_unreviewed_attributes_fail(self):
        for extra in [{"excludes": [{"group": "example", "module": "other"}]},
                      {"attributes": {"org.gradle.category": "platform"}},
                      {"requestedCapabilities": ["custom"]}, {"endorseStrictVersions": True}]:
            data = module(deps=[dependency() | extra]);self.store("example:app:1.0", data)
            with self.subTest(extra=extra), self.assertRaises(MODULE.AuditError):
                self.check()
        data = module(deps=[{"group": "example", "module": "leaf"}]);self.store("example:app:1.0", data)
        self.assertEqual(self.check()["nodes"][0]["dependencies"], ["example:leaf:1.0"])

    def test_platform_constraints_are_checked_for_the_explicit_library_selection(self):
        platform = dependency("example:bom") | {"attributes": {"org.gradle.category": "platform"}, "endorseStrictVersions": True}
        self.store("example:app:1.0", module(deps=[dependency(), platform]))
        bom = module("example:bom:1.0");v = bom["variants"][0]
        v["attributes"]["org.gradle.category"] = "regular-platform"
        v["dependencyConstraints"] = [{"group": "example", "module": "leaf", "version": {"strictly": "1.0"}}]
        self.store("example:bom:1.0", bom)
        self.assertEqual(self.check()["nodes"][1]["category"], "platform")
        v["dependencyConstraints"][0]["version"] = {"strictly": "2.0"};self.store("example:bom:1.0", bom)
        with self.assertRaisesRegex(MODULE.AuditError, "Strict version conflict"):
            self.check()

    def test_unreachable_metadata_or_unused_selections_fail(self):
        self.store("example:unused:1.0", module("example:unused:1.0"))
        with self.assertRaisesRegex(MODULE.AuditError, "unreachable"):
            self.check()
        self.inventory["metadata"].pop("example:unused:1.0")
        with self.assertRaisesRegex(MODULE.AuditError, "unused version"):
            self.check()

    def test_escaped_paths_duplicate_keys_and_bad_digests_fail(self):
        entry = self.inventory["metadata"]["example:leaf:1.0"]
        for path in ["../outside.module", "/absolute.module", "a\\b", "a/../b"]:
            old = entry["path"];entry["path"] = path
            with self.subTest(path=path), self.assertRaises(MODULE.AuditError):self.check()
            entry["path"] = old
        entry["sha256"] = "0" * 63
        with self.assertRaisesRegex(MODULE.AuditError, "SHA-256"):
            self.check()
        with self.assertRaisesRegex(MODULE.AuditError, "Duplicate JSON key"):
            MODULE.load_json('{"x":1,"x":2}')
        with self.assertRaisesRegex(MODULE.AuditError, "Non-finite"):
            MODULE.load_json('{"x":NaN}')

    def test_symlink_cannot_leave_inventory(self):
        with tempfile.TemporaryDirectory() as other:
            outside = Path(other) / "metadata.module";outside.write_bytes(b"{}")
            path = self.root / self.inventory["metadata"]["example:leaf:1.0"]["path"]
            path.unlink()
            try:
                path.symlink_to(outside)
            except OSError:
                self.skipTest("Symlink creation is unavailable")
            with self.assertRaisesRegex(MODULE.AuditError, "symlink leaves"):
                self.check()

    def test_pom_keeps_runtime_and_compile_but_skips_test_provided_and_optional(self):
        dependencies = "".join('<dependency><groupId>example</groupId><artifactId>ignored</artifactId>'
                               '<version>1.0</version>' + attributes + '</dependency>' for attributes in
                               ['<scope>test</scope>', '<scope>provided</scope>', '<optional>true</optional>'])
        self.store("example:leaf:1.0", pom(dependencies), "pom")
        self.assertEqual(self.check()["nodes"][1]["dependencies"], [])
        self.assertEqual(self.check()["nodes"][1]["variant"], "maven-runtime")
        dependencies = ('<dependency><groupId>example</groupId><artifactId>app</artifactId>'
                        '<version>1.0</version><scope>runtime</scope></dependency>')
        self.store("example:leaf:1.0", pom(dependencies), "pom")
        self.assertEqual(self.check()["nodes"][1]["dependencies"], ["example:app:1.0"])

    def test_pom_unsupported_inheritance_management_and_entities_fail(self):
        for fragment in [b'<parent/>', b'<dependencyManagement/>', b'<profiles/>']:
            self.store("example:leaf:1.0", pom().replace(b'<dependencies>', fragment + b'<dependencies>'), "pom")
            with self.subTest(fragment=fragment), self.assertRaisesRegex(MODULE.AuditError, "require review"):
                self.check()
        self.store("example:leaf:1.0", b'<!DOCTYPE project>' + pom(), "pom")
        with self.assertRaisesRegex(MODULE.AuditError, "entities"):
            self.check()

    def test_cli_failure_has_no_success_report(self):
        self.inventory["metadata"].pop("example:leaf:1.0")
        path = self.root / "inventory.json";path.write_text(json.dumps(self.inventory))
        result = subprocess.run([sys.executable, str(SCRIPT), str(path)], text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("Missing metadata", result.stderr)


if __name__ == "__main__":
    unittest.main()
