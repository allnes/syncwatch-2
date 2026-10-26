"""Exercise native local-file ownership without a player, network or UI."""

import ctypes
import json
import os
from pathlib import Path
import shutil
import tempfile


class Version(ctypes.Structure):
    _fields_ = [("words", ctypes.c_uint64 * 8)]


def check_input(library, output):
    api = ctypes.CDLL(str(Path(library).resolve()))
    handle = ctypes.c_void_p
    api.sw_media_input_open.argtypes = [ctypes.c_char_p, ctypes.POINTER(handle)]
    api.sw_media_input_open.restype = ctypes.c_int
    api.sw_media_input_version.argtypes = [handle, ctypes.POINTER(Version)]
    api.sw_media_input_version.restype = ctypes.c_int
    api.sw_media_input_descriptor.argtypes = [handle]
    api.sw_media_input_descriptor.restype = ctypes.c_int
    api.sw_media_input_read_at.argtypes = [handle, ctypes.c_uint64, ctypes.c_void_p,
                                          ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    api.sw_media_input_read_at.restype = ctypes.c_int
    api.sw_media_input_close.argtypes = [handle]
    api.sw_media_input_close.restype = None

    def open_input(path, expected=0):
        value = handle()
        assert api.sw_media_input_open(str(path).encode("utf-8"), ctypes.byref(value)) == expected
        assert bool(value) == (expected == 0)
        return value

    def owned_handle_count():
        if os.name != "nt":
            return len(os.listdir("/dev/fd"))
        kernel = ctypes.windll.kernel32
        kernel.GetCurrentProcess.restype = handle
        kernel.GetProcessHandleCount.argtypes = [handle, ctypes.POINTER(ctypes.c_ulong)]
        count = ctypes.c_ulong()
        assert kernel.GetProcessHandleCount(kernel.GetCurrentProcess(), ctypes.byref(count))
        return count.value

    proof = {"platform": os.name, "versionBytes": ctypes.sizeof(Version), "playerIntegration": False}
    with tempfile.TemporaryDirectory(prefix="owned-input-", dir=output) as temporary:
        root = Path(temporary).resolve()
        media = root / "Movie кино 映画.avi"
        content = b"authored input bytes"
        media.write_bytes(content)
        modified = media.stat().st_mtime_ns
        for path, expected in [("relative.avi", 1), ("https://example.test/movie", 1), (root, 2)]:
            open_input(path, expected)
        value = open_input(media)
        try:
            version = Version()
            assert api.sw_media_input_version(value, ctypes.byref(version)) == 0
            assert version.words[3] == len(content)
            borrowed = api.sw_media_input_descriptor(value)
            assert borrowed >= 0
            # The test acts as a VLC descriptor borrower; positional hashing must
            # not alter the borrower's stream position, including on Windows CRT.
            assert os.read(borrowed, 1) == content[:1]
            position = os.lseek(borrowed, 0, os.SEEK_CUR)
            buffer = ctypes.create_string_buffer(8)
            count = ctypes.c_size_t()
            assert api.sw_media_input_read_at(value, 4, buffer, 8, ctypes.byref(count)) == 0
            assert count.value == 8 and buffer.raw == content[4:12]
            assert os.lseek(borrowed, 0, os.SEEK_CUR) == position
            assert api.sw_media_input_read_at(value, len(content), buffer, 8, ctypes.byref(count)) == 0
            assert count.value == 0
            assert api.sw_media_input_read_at(value, len(content) + 1, buffer, 8, ctypes.byref(count)) == 1
            assert count.value == 0
            assert api.sw_media_input_read_at(value, 0, buffer, 262145, ctypes.byref(count)) == 1
            if os.name == "nt":
                for operation in [lambda: media.write_bytes(b"x" * len(content)),
                                  lambda: media.rename(root / "replacement.avi")]:
                    try:
                        operation()
                    except PermissionError:
                        pass
                    else:
                        raise AssertionError("Pinned Windows input allowed write or replacement")
                proof["writeAndReplacementExcluded"] = True
            else:
                media.write_bytes(b"x" * len(content))
                os.utime(media, ns=(media.stat().st_atime_ns, modified))
                assert media.stat().st_mtime_ns == modified and media.stat().st_size == len(content)
                assert api.sw_media_input_version(value, ctypes.byref(version)) == 3
                assert list(version.words) == [0] * 8
                media.write_bytes(content)
                os.utime(media, ns=(media.stat().st_atime_ns, modified))
                assert api.sw_media_input_read_at(value, 0, buffer, 8, ctypes.byref(count)) == 3
                assert count.value == 0 and api.sw_media_input_descriptor(value) == -1
                proof["sameSizeRestoredMtimeInvalidated"] = True
                proof["invalidationLatched"] = True
        finally:
            api.sw_media_input_close(value)
        media.write_bytes(content)  # Ownership ended; writes must work again.
        long_root = root
        for index in range(4):
            long_root /= str(index) + "x" * 59
        # The fixture does not depend on the host's long-path policy or alter it.
        fixture_root = Path("\\\\?\\" + str(long_root)) if os.name == "nt" else long_root
        try:
            fixture_root.mkdir(parents=True)
            (fixture_root / "Movie кино.avi").write_bytes(content)
            value = open_input(long_root / "Movie кино.avi")
            api.sw_media_input_close(value)
            if os.name == "nt":
                value = open_input(long_root.as_posix() + "/./Movie кино.avi")
                api.sw_media_input_close(value)
        finally:
            first = root / ("0" + "x" * 59)
            shutil.rmtree(Path("\\\\?\\" + str(first)) if os.name == "nt" else first)
        proof["longPath"] = True
        if os.name != "nt":
            value = open_input(media)
            try:
                media.rename(root / "original.avi")
                media.write_bytes(content)
                os.utime(media, ns=(media.stat().st_atime_ns, modified))
                assert api.sw_media_input_version(value, ctypes.byref(Version())) == 3
                proof["replacementInvalidated"] = True
            finally:
                api.sw_media_input_close(value)
            symbolic = root / "symbolic.avi"
            symbolic.symlink_to(media)
            open_input(symbolic, 2)
            fifo = root / "pipe.avi"
            os.mkfifo(fifo)
            open_input(fifo, 2)
            proof["symlinkAndPipeRejected"] = True
        handles = owned_handle_count()
        for _ in range(32):
            value = open_input(media)
            api.sw_media_input_close(value)
        api.sw_media_input_close(None)
        assert owned_handle_count() == handles
        proof.update(positionalReadIsolated=True, eofAndBounds=True, repeatedOwnership=True,
                     noHandleGrowth=True, unicodePath=True)
    assert not root.exists()
    proof["temporaryFilesRemoved"] = True
    (Path(output) / "media-input-proof.json").write_text(json.dumps(proof, indent=2) + "\n")
    return proof


if __name__ == "__main__":
    import sys
    print(json.dumps(check_input(Path(sys.argv[1]), Path(sys.argv[2])), sort_keys=True))
