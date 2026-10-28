"""Keep the configured subtitle aliases narrow, reproducible and source-disclosed."""

import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configuration import vlc_files


class ConfigurationChecks(unittest.TestCase):
    def setUp(self):
        self.original = {
            "configure.ac": b"VERSION_DATE=$(git date\n)\n",
            "lib/media_player.c": b'    var_Create (mp, "audio-filter", VLC_VAR_STRING);',
            "modules/common.am": b"AM_LDFLAGS += $(top_builddir)/modules/module.rc.lo -Wc,-static",
            "modules/codec/avcodec/fourcc.c": b"/* Original LGPL grant remains here. */\n"
                b"    { VLC_CODEC_SUBT, AV_CODEC_ID_TEXT },\n"
                b"    { VLC_CODEC_SSA, AV_CODEC_ID_SSA },\n"
                b"    /* ffmpeg only: AV_CODEC_ID_SUBRIP */\n"
                b"    /* ffmpeg only: AV_CODEC_ID_ASS */\n",
        }
        self.profile = {"sourceDateEpoch": 1, "sources": {"vlc": {"revision": "a" * 40}}}

    def test_aliases_keep_original_bytes_and_existing_reverse_mapping(self):
        before = copy.deepcopy(self.original)
        first = vlc_files(self.original, self.profile)
        self.assertEqual(first, vlc_files(self.original, self.profile))
        self.assertEqual(self.original, before)
        result = first["modules/codec/avcodec/fourcc.c"]
        self.assertTrue(result.startswith(b"/* Original LGPL grant remains here. */"))
        for pair in [b"VLC_CODEC_SUBT, AV_CODEC_ID_TEXT", b"VLC_CODEC_SSA, AV_CODEC_ID_SSA",
                     b"VLC_CODEC_SUBT, AV_CODEC_ID_SUBRIP", b"VLC_CODEC_SSA, AV_CODEC_ID_ASS"]:
            self.assertEqual(result.count(pair), 1)
        self.assertIn(b"SyncWatch modified 2026-10-28", result)

    def test_source_drift_and_reapplying_a_derivative_are_rejected(self):
        key = "modules/codec/avcodec/fourcc.c"
        for content in [self.original[key].replace(b"SUBRIP", b"UNKNOWN"),
                        self.original[key] + b"    /* ffmpeg only: AV_CODEC_ID_ASS */",
                        vlc_files(self.original, self.profile)[key]]:
            with self.subTest(content=content), self.assertRaises(ValueError):
                vlc_files(self.original | {key: content}, self.profile)


if __name__ == "__main__":
    unittest.main()
