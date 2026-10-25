"""SDK loader search is scoped to build tools, not target/application processes."""

import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_context import BuildContext
import native_context


class SdkToolEnvironmentTests(unittest.TestCase):
    def test_private_sdk_libraries_do_not_enter_the_target_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library = root / "sdk/usr/lib/x86_64-linux-gnu/libgettext-test.so"
            library.parent.mkdir(parents=True)
            library.write_bytes(b"declared SDK support")
            with patch.dict(os.environ, {"SYNCWATCH_VLC_EXTRA_TOOLS_ROOT": str(root / "sdk")}), \
                    patch.object(native_context, "native_target", return_value="linux-x64"), \
                    patch.object(BuildContext, "tool", return_value=sys.executable):
                context = BuildContext(root / "work", 0)
            inherited = context.env["LD_LIBRARY_PATH"]
            with patch.object(BuildContext, "tool", return_value=sys.executable):
                command = context.sdk_command("msgfmt", "--version")
                compiler = context.sdk_command("gcc")
            self.assertEqual(command[0], "/usr/bin/env")
            self.assertIn(str(library.parent), command[1])
            self.assertEqual(context.env["LD_LIBRARY_PATH"], inherited)
            self.assertNotIn(str(library.parent), inherited)
            self.assertEqual(compiler, [sys.executable])
            self.assertEqual(context.sdk_support()[library.relative_to(root / "sdk").as_posix()],
                             hashlib.sha256(library.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
