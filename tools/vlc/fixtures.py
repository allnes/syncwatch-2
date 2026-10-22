"""Create deterministic, first-party media fixtures without an external encoder."""

import argparse
import math
from pathlib import Path
import struct

WIDTH, HEIGHT, FPS, SECONDS, RATE = 320, 180, 25, 4, 48000


def chunk(kind, data):
    return kind + struct.pack("<I", len(data)) + data + (b"\0" if len(data) % 2 else b"")


def listing(kind, data):
    return chunk(b"LIST", kind + data)


def avi():
    frames = FPS * SECONDS
    image_size = WIDTH * HEIGHT * 3 // 2
    audio_size = RATE // FPS * 4
    main = struct.pack("<14I", 1000000 // FPS, (image_size + audio_size) * FPS,
                       0, 0x10, frames, 0, 2, image_size, WIDTH, HEIGHT, 0, 0, 0, 0)
    video_header = struct.pack("<4s4sIHH8I4h", b"vids", b"I420", 0, 0, 0,
                               0, 1, FPS, 0, frames, image_size, 0xffffffff, 0,
                               0, 0, WIDTH, HEIGHT)
    video_format = struct.pack("<IiiHH4sIiiII", 40, WIDTH, HEIGHT, 1, 12, b"I420",
                               image_size, 0, 0, 0, 0)
    audio_header = struct.pack("<4s4sIHH8I4h", b"auds", b"\0" * 4, 0, 0, 0,
                               0, 4, RATE * 4, 0, RATE * SECONDS,
                               audio_size, 0xffffffff, 4, 0, 0, 0, 0)
    audio_format = struct.pack("<HHIIHH", 1, 2, RATE, RATE * 4, 4, 16)
    headers = chunk(b"avih", main)
    headers += listing(b"strl", chunk(b"strh", video_header) + chunk(b"strf", video_format))
    headers += listing(b"strl", chunk(b"strh", audio_header) + chunk(b"strf", audio_format))
    media, index, offset = [], [], 4
    for number in range(frames):
        # Every decoded frame identifies its actual position through luminance.
        video = bytes([40 + number * 2]) * (WIDTH * HEIGHT)
        video += bytes([128]) * (WIDTH * HEIGHT // 2)
        samples = bytearray()
        for sample in range(RATE // FPS):
            position = number * (RATE // FPS) + sample
            value = round(7000 * math.sin(2 * math.pi * 440 * position / RATE))
            samples.extend(struct.pack("<hh", value, value))
        for kind, data in [(b"00dc", video), (b"01wb", bytes(samples))]:
            encoded = chunk(kind, data)
            media.append(encoded)
            index.append(struct.pack("<4sIII", kind, 0x10, offset, len(data)))
            offset += len(encoded)
    body = b"AVI " + listing(b"hdrl", headers) + listing(b"movi", b"".join(media))
    return chunk(b"RIFF", body + chunk(b"idx1", b"".join(index)))


def create(directory):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "owned-i420-pcm.avi"
    path.write_bytes(avi())
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    print(create(parser.parse_args().directory))
