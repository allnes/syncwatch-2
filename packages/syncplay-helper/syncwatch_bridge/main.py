"""Bounded inherited pipes; only the reactor thread may touch the engine."""

import os
from pathlib import Path
import queue
import sys
import threading

import fastjsonschema
from syncwatch_ipc.contracts import ContractError, Registry
from syncwatch_ipc.stream import Frames
from syncwatch_syncplay.reactor import install

from .controller import Controller


class QuietOutput:
    def write(self, text):
        return len(text)

    def flush(self):
        pass


def main():
    # Upstream console output is neither IPC nor a sanitized diagnostic.
    # The writer owns raw fd 1; no Python text writer can corrupt its frames.
    sys.stdout = sys.stderr = QuietOutput()
    reactor = install()
    from twisted.internet import task
    from .engine import Engine
    root = Path(__file__).resolve().parents[1]
    registry = Registry(root / "contracts", fastjsonschema)
    revision = (root / "syncplay-revision.txt").read_text(encoding="ascii").strip()
    outgoing = queue.Queue(maxsize=64)
    incoming = queue.Queue(maxsize=64)
    wake = threading.Event()
    writer_finished = threading.Event()
    terminal = threading.Event()
    draining = [False]
    frames = Frames(registry.manifest["maxFrameBytes"])

    def send(data):
        try:
            outgoing.put_nowait(data)
        except queue.Full as error:
            raise ContractError("queueFull") from error

    def stop():
        if not draining[0]:
            draining[0] = True
            terminal.set()
            reactor.callLater(2, reactor.stop)

    controller = Controller(registry, send, stop, Engine, revision)

    def abort():
        try:
            controller.abort()
        except Exception:
            stop()

    def pump():
        try:
            while True:
                try:
                    data = incoming.get_nowait()
                except queue.Empty:
                    break
                if data is None:
                    frames.eof()
                    abort()
                    break
                for frame in frames.feed(data):
                    controller.receive(frame)
        except Exception:
            abort()
        finally:
            wake.clear()

    def tick():
        if not incoming.empty():
            pump()
        try:
            controller.tick()
        except Exception:
            abort()
        if draining[0] and writer_finished.is_set():
            reactor.stop()

    def read():
        try:
            while not terminal.is_set():
                data = os.read(0, 4096)
                incoming.put(data or None, timeout=1)
                if not wake.is_set():
                    wake.set()
                    reactor.callFromThread(pump)
                if not data:
                    return
        except Exception:
            reactor.callFromThread(abort)

    def write():
        try:
            while not terminal.is_set() or not outgoing.empty():
                try:
                    data = outgoing.get(timeout=0.05)
                except queue.Empty:
                    continue
                while data:
                    count = os.write(1, data)
                    if count <= 0:
                        raise OSError("closed pipe")
                    data = data[count:]
        except Exception:
            reactor.callFromThread(abort)
        finally:
            writer_finished.set()

    threading.Thread(target=read, name="helper-input", daemon=True).start()
    threading.Thread(target=write, name="helper-output", daemon=True).start()
    task.LoopingCall(tick).start(0.05)
    reactor.run(installSignalHandlers=False)
