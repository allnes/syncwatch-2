import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from source_profile import ROOT, read


class SourceProfileTests(unittest.TestCase):
    def test_runtime_and_dynamic_clients_match_actual_indexed_submodule_pins(self):
        for filename in ("jvm-profile.json", "linux-clients.json"):
            with self.subTest(profile=filename):
                read(ROOT / "tools/application" / filename)

    def test_changed_source_pin_missing_build_entry_and_lost_grant_are_rejected(self):
        profile = json.loads((ROOT / "tools/application/jvm-profile.json").read_text())
        changed_pin = copy.deepcopy(profile)
        changed_pin["sources"]["openjdk"]["revision"] = "0" * 40
        missing_entry = copy.deepcopy(profile)
        missing_entry["sources"]["openjdk"]["exports"].remove("Makefile")
        missing_grant = copy.deepcopy(profile)
        missing_grant["sources"]["openjdk"]["exports"].remove("ASSEMBLY_EXCEPTION")
        with tempfile.TemporaryDirectory(prefix="sw-source-profile-") as temporary:
            path = Path(temporary) / "profile.json"
            for label, invalid in (("source pin", changed_pin), ("Makefile", missing_entry), ("grant", missing_grant)):
                with self.subTest(invalid=label):
                    path.write_text(json.dumps(invalid))
                    with self.assertRaises(ValueError):
                        read(path)
