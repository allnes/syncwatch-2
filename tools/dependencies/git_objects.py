"""Read immutable source blobs, retrying only transient HTTP server failures."""

from git_transport import run


def read_blobs(source, objects):
    # A partial clone may fetch a promised blob from inside cat-file itself.
    # Retrying clone/fetch alone does not cover that read. Discard partial stdout
    # and repeat the identical pinned IDs; the caller still verifies every blob.
    request = ("\n".join(objects) + "\n").encode()
    return run(["cat-file", "--batch"], cwd=source, input=request, capture_output=True).stdout
