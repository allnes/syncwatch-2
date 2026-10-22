from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from native_audit import audit


class NativeImportTests(unittest.TestCase):
    def proof(self, exports):
        def inspect(args, **kwargs):
            if '/exports' in args:
                return exports
            return '' if args[-1].endswith('python3.dll') else '    KERNEL32.dll\n'
        with patch('native_audit.subprocess.check_output', side_effect=inspect):
            return audit([Path('python3.dll'), Path('python312.dll')], 'windows-x64',
                         {'compiler': 'MSVC 14.44.35207'}, ['-DCMAKE_GENERATOR_INSTANCE=C:/BuildTools'])

    def test_stable_abi_shim_must_forward_every_export_to_owned_python(self):
        exports = '  2 number of names\n  PyA (forwarded to python312.PyA)\n  PyB (forwarded to python312.PyB)\n'
        self.assertEqual(self.proof(exports)['python3.dll'], ['PYTHON312.DLL'])
        for bad in [exports.replace('python312.PyB', 'foreign.PyB'),
                    exports.replace('2 number', '3 number'),
                    exports.replace('(forwarded to python312.PyB)', '')]:
            with self.subTest(exports=bad), self.assertRaisesRegex(ValueError, 'undeclared'):
                self.proof(bad)

    def test_empty_imports_are_not_a_general_sdk_exception(self):
        with patch('native_audit.subprocess.check_output', return_value=''):
            with self.assertRaisesRegex(ValueError, 'undeclared'):
                audit([Path('foreign.dll')], 'windows-x64', {'compiler': 'MSVC 14.44.35207'},
                      ['-DCMAKE_GENERATOR_INSTANCE=C:/BuildTools'])


if __name__ == '__main__':
    unittest.main()
