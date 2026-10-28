"""Verify scoped external stream attachment and native descriptor release."""

import ctypes
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time

from player_input_checks import Observation

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vlc"))
from fixtures import external_tracks


def check_external_inputs(library, libvlc, revision, fixture, output):
    api = ctypes.CDLL(str(library))
    handle, generation = ctypes.c_void_p, ctypes.c_uint64
    signatures = {
        "sw_playback_open": [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, handle, ctypes.POINTER(handle)],
        "sw_playback_load": [handle, generation, ctypes.c_char_p],
        "sw_playback_attach_track": [handle, generation, ctypes.c_int, ctypes.c_char_p],
        "sw_playback_observe": [handle, generation, ctypes.POINTER(Observation)],
        "sw_playback_pause": [handle, generation, ctypes.c_int],
        "sw_playback_stop": [handle, generation],
        "sw_playback_tracks": [handle, generation, ctypes.c_int, ctypes.POINTER(ctypes.c_int32),
                               ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)],
        "sw_playback_selected_track": [handle, generation, ctypes.c_int, ctypes.POINTER(ctypes.c_int32)],
    }
    for name, arguments in signatures.items():
        function = getattr(api, name)
        function.argtypes, function.restype = arguments, ctypes.c_int
    api.sw_playback_close.argtypes, api.sw_playback_close.restype = [handle], None
    player = handle()
    proof = {"platform": os.name, "physicalOutputAccepted": False}
    with tempfile.TemporaryDirectory(prefix="external Кино spaces-", dir=output) as temporary:
        directory = Path(temporary).resolve()
        media = directory / "Movie кино 映画.avi"
        shutil.copyfile(fixture, media)
        subtitle = directory / "Movie English.srt"
        subtitle.write_text("1\n00:00:00,000 --> 00:00:03,900\nOwned external caption\n", encoding="utf-8")
        encoded = str(subtitle).encode("utf-8")
        audio = external_tracks(directory)["external-audio"]

        def observe(scope):
            value = Observation()
            assert api.sw_playback_observe(player, scope, ctypes.byref(value)) == 0
            return value

        def ready(scope):
            until = time.monotonic() + 12
            while time.monotonic() < until:
                value = observe(scope)
                assert value.status != 3
                if value.status == 2 and value.paused:
                    return value
                time.sleep(.02)
            raise AssertionError("External-input native player did not become paused/ready")

        def selected_track(scope, subtitles=True, excluded=()):
            until = time.monotonic() + 8
            while time.monotonic() < until:
                ids, count, selected = (ctypes.c_int32 * 256)(), ctypes.c_size_t(), ctypes.c_int32(-1)
                assert api.sw_playback_tracks(player, scope, int(subtitles), ids, 256, ctypes.byref(count)) == 0
                assert api.sw_playback_selected_track(player, scope, int(subtitles), ctypes.byref(selected)) == 0
                if selected.value >= 0 and selected.value not in excluded and selected.value in list(ids)[:count.value]:
                    return selected.value
                time.sleep(.02)
            raise AssertionError("External track attachment was not acknowledged by actual VLC")

        try:
            assert api.sw_playback_open(str(libvlc).encode(), revision.encode(), 0, None, ctypes.byref(player)) == 0
            assert api.sw_playback_attach_track(player, 0, 1, encoded) == 2
            for scope in range(1, 5):
                assert api.sw_playback_load(player, scope, str(media).encode()) == 0
                initial = ready(scope)
                assert api.sw_playback_attach_track(player, scope - 1, 1, encoded) == 3
                assert api.sw_playback_attach_track(player, scope, 2, encoded) == 1
                assert api.sw_playback_attach_track(player, scope, 1, b"https://invalid.example/sub.srt") == 1
                assert api.sw_playback_attach_track(player, scope, 1, str(directory / "missing.srt").encode()) == 2
                assert observe(scope).status == 2
                assert api.sw_playback_attach_track(player, scope, 1, encoded) == 0
                selected = selected_track(scope)
                after = observe(scope)
                assert after.paused and after.generation == scope and abs(after.position_ms - initial.position_ms) < 100
                original_audio = selected_track(scope, False)
                assert api.sw_playback_attach_track(player, scope, 0, str(audio).encode()) == 0
                selected_track(scope, False, (original_audio,))
                assert api.sw_playback_pause(player, scope, 0) == 0
                until = time.monotonic() + 4
                while observe(scope).position_ms < 200:
                    assert time.monotonic() < until
                    time.sleep(.02)
                assert api.sw_playback_pause(player, scope, 1) == 0
                assert selected_track(scope) == selected
                ready(scope)
                if os.name == "nt":
                    try:
                        subtitle.write_bytes(b"replacement")
                    except PermissionError:
                        pass
                    else:
                        raise AssertionError("External Windows input did not exclude mutation")
                assert api.sw_playback_stop(player, scope) == 0
                # Stop must release the sidecar before the next watch can own it.
                moved = subtitle.with_suffix(".released")
                subtitle.rename(moved)
                moved.rename(subtitle)
            proof.update(pausedAttachment=True, actualSelectedID=True, scopedGeneration=True,
                         localOnly=True, rejectedMissingInputPreservesWatch=True,
                         repeatedRelease=True, transportPreserved=True, externalAudioSelectedID=True)
            if os.name != "nt":
                assert api.sw_playback_load(player, 5, str(media).encode()) == 0
                ready(5)
                assert api.sw_playback_attach_track(player, 5, 1, encoded) == 0
                selected_track(5)
                subtitle.write_text("changed owned sidecar", encoding="utf-8")
                assert observe(5).status == 3
                assert api.sw_playback_load(player, 6, str(media).encode()) == 0
                ready(6)
                proof["changedExternalInputFailsAndNextWatchRecovers"] = True
        finally:
            if player.value:
                api.sw_playback_close(player)
    proof["temporaryFilesRemoved"] = True
    (Path(output) / "external-input-proof.json").write_text(json.dumps(proof, sort_keys=True) + "\n")
    print(json.dumps(proof, sort_keys=True))
    return proof


if __name__ == "__main__":
    check_external_inputs(*sys.argv[1:])
