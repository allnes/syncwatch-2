"""Require an explicit successful result from every selected CI job."""

import argparse
import json
import os
import sys


def validate_results(results: object, expected: list[str]) -> None:
    if not isinstance(results, dict):
        raise ValueError("job results must be an object")
    if not expected or len(set(expected)) != len(expected):
        raise ValueError("expected job names must be nonempty and unique")
    if set(results) != set(expected):
        raise ValueError("reported jobs do not match the required job set")
    for name in expected:
        job = results[name]
        if not isinstance(job, dict) or job.get("result") != "success":
            raise ValueError(f"required job did not succeed: {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jobs", nargs="+")
    args = parser.parse_args()
    try:
        results = json.loads(os.environ["CI_NEEDS_JSON"])
        validate_results(results, args.jobs)
    except (KeyError, ValueError) as error:
        print(f"Required CI failed: {error}", file=sys.stderr)
        return 1
    print("All required CI jobs succeeded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
