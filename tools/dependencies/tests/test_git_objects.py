import contextlib
import io
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build
import git_objects


class GitObjectReadTests(unittest.TestCase):
    def test_transient_failure_discards_partial_output_and_exports_actual_git_blobs(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            contents = b"original pinned bytes\r\n\x00\xff"
            (root / "LICENSE").write_bytes(contents)
            subprocess.run(["git", "add", "LICENSE"], cwd=root, check=True)
            subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                            "commit", "-qm", "source"], cwd=root, check=True)
            revision = build.git(root, "rev-parse", "HEAD").decode().strip()
            entries = build.exported_entries(root, ["LICENSE"])
            actual_run = subprocess.run
            attempts = []

            def transport(command, **options):
                attempts.append((command, options["input"]))
                if len(attempts) == 1:
                    return subprocess.CompletedProcess(command, 128, b"partial must be discarded",
                                                       b"fatal: requested URL returned error: 500\n")
                return actual_run(command, **options)

            diagnostics = io.StringIO()
            archive = root / "source.tar"
            with patch.object(git_objects.subprocess, "run", side_effect=transport), \
                    patch.object(git_objects.time, "sleep") as delay, contextlib.redirect_stderr(diagnostics):
                build.export_original_blobs(root, archive, entries, revision)
            self.assertEqual(attempts[0], attempts[1])
            self.assertEqual(len(attempts), 2)
            delay.assert_called_once_with(1)
            self.assertIn("returned error: 500", diagnostics.getvalue())
            self.assertIn("attempt 1/3", diagnostics.getvalue())
            build.verify_source_export(archive, entries, revision, ["LICENSE"])
            with tarfile.open(archive) as source:
                self.assertEqual(source.extractfile("LICENSE").read(), contents)

    def test_server_failures_are_bounded_and_every_original_diagnostic_is_retained(self):
        diagnostics = io.StringIO()
        failures = [subprocess.CompletedProcess(["git"], 128, b"partial", f"fatal: HTTP 503 attempt-{i}\n".encode())
                    for i in range(3)]
        with patch.object(git_objects.subprocess, "run", side_effect=failures) as run, \
                patch.object(git_objects.time, "sleep") as delay, contextlib.redirect_stderr(diagnostics):
            with self.assertRaises(subprocess.CalledProcessError) as failed:
                git_objects.read_blobs(Path("."), ["a" * 40])
        self.assertEqual(run.call_count, 3)
        self.assertEqual([call.args for call in delay.call_args_list], [(1,), (2,)])
        self.assertEqual(failed.exception.stderr, failures[-1].stderr)
        for i in range(3):
            self.assertIn(f"attempt-{i}", diagnostics.getvalue())

    def test_permission_missing_revision_and_corruption_errors_are_not_retried(self):
        for message in (b"fatal: URL returned error: 401", b"fatal: URL returned error: 404",
                        b"fatal: permission denied", b"fatal: not our ref", b"fatal: object hash mismatch"):
            with self.subTest(message=message), contextlib.redirect_stderr(io.StringIO()), \
                    patch.object(git_objects.subprocess, "run", return_value=subprocess.CompletedProcess(["git"], 128, b"", message)) as run, \
                    patch.object(git_objects.time, "sleep") as delay:
                with self.assertRaises(subprocess.CalledProcessError):
                    git_objects.read_blobs(Path("."), ["a" * 40])
                run.assert_called_once()
                delay.assert_not_called()

    def test_success_is_returned_once_without_reinterpreting_blob_content(self):
        # An upstream source file may itself contain text mentioning HTTP errors.
        contents = b"original source containing HTTP 500\x00\xff"
        with patch.object(git_objects.subprocess, "run", return_value=subprocess.CompletedProcess(["git"], 0, contents, b"")) as run, \
                patch.object(git_objects.time, "sleep") as delay:
            self.assertEqual(git_objects.read_blobs(Path("."), ["a" * 40]), contents)
            run.assert_called_once()
            delay.assert_not_called()

    def test_successful_transport_cannot_bypass_pinned_object_validation(self):
        with tempfile.TemporaryDirectory() as scratch:
            archive = Path(scratch) / "source.tar"
            response = subprocess.CompletedProcess(["git"], 0, b"wrong-object blob 1\nx\n", b"")
            with patch.object(git_objects.subprocess, "run", return_value=response) as run, \
                    patch.object(git_objects.time, "sleep") as delay:
                with self.assertRaisesRegex(ValueError, "unexpected type"):
                    build.export_original_blobs(Path(scratch), archive, {"LICENSE": ("100644", "a" * 40)}, "b" * 40)
                self.assertFalse(archive.exists())
                run.assert_called_once()
                delay.assert_not_called()


if __name__ == "__main__":
    unittest.main()
