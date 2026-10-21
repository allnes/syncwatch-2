"""Reject regression to the vendor's unchecked allocating hash constructor."""
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import package_sdk

class ImportChecks(unittest.TestCase):
    def test_native_hash_import_formats(self):
        expected=json.loads((package_sdk.ROOT/'tools/python-package/profile.json').read_text(encoding='utf-8'))['hashImports']
        for target in ['macos-arm64','windows-x64','linux-x64']:
            tag='000 UNDEF notype () External | ' if target=='windows-x64' else ' U '+('_' if target=='macos-arm64' else '')
            data='\n'.join(tag+n for n in expected).encode()
            with self.subTest(target=target),patch.object(package_sdk.subprocess,'run',return_value=subprocess.CompletedProcess([],0,data,b'')):
                self.assertEqual(package_sdk.imports('symbol-tool',Path('library'),target),expected)

    def test_vendor_allocator_missing_or_failed_imports_rejected(self):
        expected=json.loads((package_sdk.ROOT/'tools/python-package/profile.json').read_text(encoding='utf-8'))['hashImports']
        valid='\n'.join(' U '+n for n in expected).encode()
        cases=[(valid+b'\n U python_hashlib_Hacl_Hash_SHA2_malloc_256',0),(valid+b'\n U Hacl_unprefixed',0),
               (b'',0),(valid,1),(b'x'*1048577,0)]
        for data,code in cases:
            with self.subTest(size=len(data),code=code),patch.object(package_sdk.subprocess,'run',return_value=subprocess.CompletedProcess([],code,data,b'')),self.assertRaises(ValueError):
                package_sdk.imports('symbol-tool',Path('library'),'linux-x64')
