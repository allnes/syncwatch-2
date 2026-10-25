"""Fail before compilation when a selected desktop output loses its loader closure."""

import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import source_profile
from configuration import pulse_version


class OutputProfileTests(unittest.TestCase):
    def setUp(self):
        self.profile = json.loads((source_profile.ROOT / "tools/vlc/profile.json").read_text())

    def test_missing_vlc_audio_helper_is_rejected_before_compile(self):
        self.profile["platformHelperLibraries"]["linux-x64"].remove("libvlc_pulse.so.0")
        with self.assertRaisesRegex(ValueError, "closure is incomplete"):
            source_profile.output_libraries(self.profile, "linux-x64")

    def test_private_audio_client_cannot_be_omitted(self):
        self.profile["platformPrivateLibraries"]["linux-x64"] = []
        with self.assertRaisesRegex(ValueError, "closure is incomplete"):
            source_profile.output_libraries(self.profile, "linux-x64")

    def test_helper_path_cannot_escape_the_module_build_directory(self):
        self.profile["platformHelperLibraries"]["linux-x64"] = ["../libvlc_pulse.so.0"]
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            source_profile.output_libraries(self.profile, "linux-x64")

    def test_both_consumers_use_the_exact_original_x11_sources(self):
        renderer = json.loads((source_profile.ROOT / "tools/desktop/profile.json").read_text())
        for name, source in self.profile["sources"].items():
            if name.startswith("desktop-"):
                for field in ("revision", "files", "executables"):
                    with self.subTest(source=name, field=field):
                        self.assertEqual(source[field], renderer["sources"][name][field])

    def test_wrong_distribution_version_cannot_replace_original_release_metadata(self):
        original = {"NEWS": b"PulseAudio 0.0\n", "meson.build": b"'.tarball-version'", "git-version-gen": b".tarball-version"}
        with self.assertRaisesRegex(ValueError, "distribution-version"):
            pulse_version(original, self.profile)


if __name__ == "__main__":
    unittest.main()
