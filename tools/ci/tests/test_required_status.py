import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from required_status import validate_results


class RequiredStatusChecks(unittest.TestCase):
    def test_all_selected_jobs_must_succeed(self):
        validate_results({"repository": {"result": "success"}, "tests": {"result": "success"}}, ["repository", "tests"])

    def test_non_success_results_fail_closed(self):
        for result in ("failure", "cancelled", "skipped", "pending", "neutral", "unknown", None):
            with self.subTest(result=result), self.assertRaises(ValueError):
                validate_results({"tests": {"result": result}}, ["tests"])

    def test_missing_result_fails(self):
        with self.assertRaises(ValueError):
            validate_results({"tests": {}}, ["tests"])

    def test_missing_job_fails(self):
        with self.assertRaises(ValueError):
            validate_results({}, ["tests"])

    def test_unexpected_job_fails(self):
        with self.assertRaises(ValueError):
            validate_results({"tests": {"result": "success"}, "extra": {"result": "failure"}}, ["tests"])

    def test_empty_job_set_cannot_pass(self):
        with self.assertRaises(ValueError):
            validate_results({}, [])

    def test_duplicate_expected_jobs_fail(self):
        with self.assertRaises(ValueError):
            validate_results({"tests": {"result": "success"}}, ["tests", "tests"])

    def test_cli_propagates_failure(self):
        script = Path(__file__).resolve().parents[1] / "required_status.py"
        environment = dict(os.environ, CI_NEEDS_JSON=json.dumps({"tests": {"result": "failure"}}))
        result = subprocess.run([sys.executable, str(script), "tests"], env=environment, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("did not succeed", result.stderr)


if __name__ == "__main__":
    unittest.main()
