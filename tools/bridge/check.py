"""Build and exercise the real helper with owned CPython and a real TLS server."""

import argparse
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys

from build import ROOT, build, digest, inventory

sys.path[:0] = [str(ROOT / "tools/python-runtime"), str(ROOT / "tools/python-build")]
from native_probe import exercise_sdk
from runtime_package import layout


def signal_policy(binary, runtime):
    if os.name == "nt":
        return {"target": "windows", "posixSignalApplicable": False}
    # Embedded CPython does not install the normal Python executable's signal
    # handlers. A closed TLS socket must become an I/O error, not kill the helper.
    child = subprocess.Popen([str(binary), str(runtime)], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    hello = {"v": 1, "id": "cmd-1", "type": "bridge.hello", "clientRunId": "signal-check",
             "mediaGeneration": 1, "payload": {"supportedVersions": [1]}}
    try:
        child.stdin.write((json.dumps(hello) + "\n").encode())
        child.stdin.flush()
        data = b""
        import time
        deadline = time.monotonic() + 10
        while b"\n" not in data:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([child.stdout], [], [], remaining)[0]:
                raise ValueError("Signal probe handshake timed out")
            chunk = os.read(child.stdout.fileno(), 65537)
            if not chunk or len(data) + len(chunk) > 65536:
                raise ValueError("Signal probe handshake failed")
            data += chunk
        if json.loads(data)["type"] != "bridge.ready":
            raise ValueError("Signal probe handshake was not acknowledged")
        os.kill(child.pid, signal.SIGPIPE)
        shutdown = hello | {"id": "cmd-2", "type": "bridge.shutdown", "payload": {}}
        output, diagnostic = child.communicate((json.dumps(shutdown) + "\n").encode(), timeout=10)
        if child.returncode != 0 or diagnostic or json.loads(output)["type"] != "bridge.stopped":
            raise ValueError("Owned helper did not survive SIGPIPE: exit=" + str(child.returncode))
        return {"posixSignalApplicable": True, "brokenPipeSignalSurvives": True, "shutdown": True}
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)
        for stream in (child.stdin, child.stdout, child.stderr):
            stream.close()


def session(binary, runtime):
    def command(number, kind, payload):
        return {"v": 1, "id": "cmd-" + str(number), "type": kind, "clientRunId": "pipe-check",
                "mediaGeneration": 2, "payload": payload}
    hello = command(1, "bridge.hello", {"supportedVersions": [1]})
    commands = [hello, hello, command(2, "player.loaded", {"mediaHandle": "media-1", "name": "Movie.mkv",
                "durationMs": 60000, "fileSizeBytes": 1234}), command(3, "bridge.shutdown", {})]
    data = b"".join((json.dumps(value) + "\n").encode() for value in commands)
    result = subprocess.run([str(binary), str(runtime)], input=data, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=10, check=True)
    replies = [json.loads(line) for line in result.stdout.splitlines()]
    if ([v["type"] for v in replies] != ["bridge.ready", "bridge.ready", "bridge.result", "bridge.stopped"]
            or replies[0] != replies[1] or result.stderr):
        raise ValueError("Real pipe handshake/replay/shutdown failed")
    # An oversized unfinished frame must terminate without reflecting its data.
    rejected = subprocess.run([str(binary), str(runtime)], input=b"x" * 65537, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=10)
    if rejected.stdout or rejected.stderr != b"Helper stopped: frameTooLarge\n":
        raise ValueError("Invalid pipe input was echoed")
    return {"coalescedFrames": True, "identicalReplay": True, "shutdown": True, "oversizedInputClosed": True,
            "signalPolicy": signal_policy(binary, runtime)}


def check(runtime, output):
    binary = build(runtime, output)
    receipt = json.loads((output / "helper-report.json").read_text(encoding="utf-8"))
    before = inventory(output)
    if {k: v for k, v in before.items() if k != "helper-report.json"} != receipt["files"]:
        raise ValueError("Helper receipt does not match")
    report = {"sourceCommit": receipt["sourceCommit"], "target": receipt["target"],
              "helperReceiptSha256": digest(output / "helper-report.json"), "session": session(binary, output)}
    captured = []
    def capture(_, data):
        for line in data.decode("utf-8").splitlines():
            if line.startswith("SYNCWATCH_PIPE_ENGINE_PROOF "):
                captured.append(json.loads(line.removeprefix("SYNCWATCH_PIPE_ENGINE_PROOF ")))
    code = "BRIDGE_RUNTIME = " + repr(str(output)) + "\n"
    code += (ROOT / "tools/syncplay-runtime/engine_fixture.py").read_text(encoding="utf-8")
    code += (ROOT / "tools/bridge/engine_checks.py").read_text(encoding="utf-8")
    report["embedding"] = exercise_sdk(layout(output, receipt["target"]), code,
                                        selected_cases=("success",), on_output=capture, case_timeout=60)
    if len(captured) != 1 or inventory(output) != before:
        raise ValueError("Missing real pipe proof or changed deliverable")
    report["engine"] = captured[0]
    (output.parent / (output.name + "-acceptance.json")).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    check(args.runtime.resolve(), args.output.resolve())
