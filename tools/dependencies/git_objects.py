"""Read immutable source blobs, retrying only transient HTTP server failures."""

import re
import subprocess
import sys
import time


MAXIMUM_ATTEMPTS = 3
TRANSIENT_HTTP = re.compile(rb"(?:URL returned error:|HTTP)\s+(?:500|502|503|504)\b")


def read_blobs(source, objects):
    # A partial clone may fetch a promised blob from inside cat-file itself.
    # Retrying clone/fetch alone does not cover that read. Discard partial stdout
    # and repeat the identical pinned IDs; the caller still verifies every blob.
    command = ["git", "cat-file", "--batch"]
    request = ("\n".join(objects) + "\n").encode()
    for attempt in range(1, MAXIMUM_ATTEMPTS + 1):
        result = subprocess.run(command, cwd=source, input=request,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.stderr:
            sys.stderr.write(result.stderr.decode("utf-8", errors="replace"))
            sys.stderr.flush()
        if result.returncode == 0:
            return result.stdout
        error = subprocess.CalledProcessError(result.returncode, command, output=result.stdout, stderr=result.stderr)
        if attempt == MAXIMUM_ATTEMPTS or not TRANSIENT_HTTP.search(result.stderr):
            raise error
        print(f"Source blob read: transient HTTP failure, attempt {attempt}/{MAXIMUM_ATTEMPTS}; retrying identical object IDs",
              file=sys.stderr, flush=True)
        time.sleep(attempt)
    raise AssertionError("unreachable source read")
