"""Real public C ABI, native filesystem, immutable snapshot and lifetime cases."""
import ctypes as c
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[3]
FIELDS = json.loads((ROOT/"tools/python-runtime/profile.json").read_text(encoding="utf-8"))["startupPolicy"]["explicitPathFields"]
_DEFAULT = object()

class File(c.Structure):
    _fields_ = [("path",c.c_wchar_p),("size",c.c_uint64),("sha256",c.c_ubyte*32)]
class Paths(c.Structure):
    _fields_ = [(name,c.c_wchar_p) for name in FIELDS]+[("search_count",c.c_size_t),("search",c.POINTER(c.c_wchar_p))]
class Layout(c.Structure):
    _fields_ = [(name,c.c_wchar_p) for name in ["executable","library"]]+[("search_count",c.c_size_t),("search",c.POINTER(c.c_wchar_p))]

OK, ARGUMENT, MANIFEST, ROOT_ERROR, UNSAFE, UNEXPECTED, MISSING, SIZE, DIGEST, IO_ERROR, LIMIT, NOT_FOUND, CAPACITY = range(13)

class NativePackageChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = c.CDLL(os.environ["SYNCWATCH_PACKAGE_TEST_MODULE"])
        functions = {
            "open":([c.c_wchar_p,c.POINTER(File),c.c_size_t,c.POINTER(c.c_void_p)],c.c_int),
            "close":([c.c_void_p],None),
            "resolve":([c.c_void_p,c.c_wchar_p,c.c_int,c.c_wchar_p,c.c_size_t],c.c_int),
            "create_paths":([c.c_void_p,c.POINTER(Layout),c.POINTER(c.c_void_p)],c.c_int),
            "close_paths":([c.c_void_p],None),
            "paths_view":([c.c_void_p],c.POINTER(Paths)),
            "library":([c.c_void_p],c.c_wchar_p),
            "file_size":([],c.c_size_t), "paths_size":([],c.c_size_t),
        }
        for name,(args,result) in functions.items():
            fn = getattr(cls.api,"sw_test_"+name);fn.argtypes=args;fn.restype=result
        if cls.api.sw_test_file_size()!=c.sizeof(File) or cls.api.sw_test_paths_size()!=c.sizeof(Paths):
            raise RuntimeError("Native structure layout differs from the SDK test binding")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="sw-package-cases-")
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name).resolve()
        self.root = self.parent/"package-\u03bc-\u0442\u0435\u0441\u0442-\U0001f642"
        self.root.mkdir()
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,"w") as z:z.writestr("fixture.py",b"VALUE=1\n")
        self.content={"bin/helper":b"fixture helper; never executed", "bin/runtime.bin":b"fixture library; never loaded",
                      "lib/encodings/__init__.py":b"# fixture only\n", "lib/payload.bin":bytes(range(256))*1024+b"last byte",
                      "lib/empty":b"", "lib/stdlib.zip":stream.getvalue()}
        for name,data in self.content.items():
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        self.files=self.inventory()

    def inventory(self, content=None):
        content=self.content if content is None else content
        names=sorted(content,key=str.lower)
        result=(File*len(names))()
        for entry,name in zip(result,names):
            entry.path=name;entry.size=len(content[name]);entry.sha256[:]=hashlib.sha256(content[name]).digest()
        return result

    def open(self, files=None, root=_DEFAULT, expected=OK, count=None):
        files=self.files if files is None else files
        out=c.c_void_p()
        code=self.api.sw_test_open(str(self.root) if root is _DEFAULT else root,files,len(files) if count is None else count,c.byref(out))
        self.assertEqual(code,expected)
        if code==OK:
            self.assertTrue(out.value);self.addCleanup(self.api.sw_test_close,out)
        else:self.assertIsNone(out.value)
        return out

    def query(self,p,name,kind,expected=OK,capacity=6000):
        out=c.create_unicode_buffer(max(capacity,16));out.value="unchanged"
        self.assertEqual(self.api.sw_test_resolve(p,name,kind,out,capacity),expected)
        if expected!=OK:self.assertEqual(out.value,"unchanged")
        return out.value

    def alias(self, link, target):
        if os.name=="nt":
            result=subprocess.run(["cmd","/c","mklink","/J",str(link),str(target)],capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr.decode(errors="replace"))
            self.addCleanup(lambda:os.rmdir(link) if link.exists() else None)
        else:link.symlink_to(target,target_is_directory=True)

    def test_complete_tree_and_unicode_root(self):
        p=self.open()
        for name in self.content:self.assertEqual(self.query(p,name,1),str(self.root/name))
        for name in ["","bin","lib","lib/encodings"]:self.assertEqual(self.query(p,name,2),str(self.root/name))

    def test_nonreserved_dos_prefix_is_portable(self):
        data=b"portable filename";(self.root/"lib/COM10.bin").write_bytes(data)
        self.open(self.inventory(self.content|{"lib/COM10.bin":data}))

    def test_empty_and_chunk_boundary_digests(self):
        for length in [1,55,56,63,64,65,65535,65536,65537,131073]:
            with self.subTest(length=length):
                data=bytes(i%251 for i in range(length));(self.root/"lib/payload.bin").write_bytes(data)
                files=self.inventory(self.content|{"lib/payload.bin":data});self.open(files)

    def test_accepted_snapshot_owns_caller_inventory(self):
        p=self.open();name=self.files[0].path;self.files[0].path="../untrusted";self.files[0].size=999;self.files[0].sha256[:]=bytes(32)
        self.assertEqual(self.query(p,name,1),str(self.root/name))

    def test_later_mutation_requires_fresh_verification(self):
        p=self.open();path=self.root/"bin/helper";path.write_bytes(b"x"*len(self.content["bin/helper"]))
        self.assertEqual(self.query(p,"bin/helper",1),str(path))
        self.open(expected=DIGEST)

    def test_null_arguments_and_existing_output(self):
        out=c.c_void_p();self.assertEqual(self.api.sw_test_open(str(self.root),None,1,c.byref(out)),ARGUMENT)
        self.assertEqual(self.api.sw_test_open(str(self.root),self.files,0,c.byref(out)),ARGUMENT)
        self.assertEqual(self.api.sw_test_open(str(self.root),self.files,len(self.files),None),ARGUMENT)
        p=self.open();value=p.value;self.assertEqual(self.api.sw_test_open(str(self.root),self.files,len(self.files),c.byref(p)),ARGUMENT);self.assertEqual(p.value,value)
        self.api.sw_test_close(None);self.api.sw_test_close_paths(None)
        self.assertFalse(self.api.sw_test_paths_view(None));self.assertIsNone(self.api.sw_test_library(None))

    def test_traversal_nonportable_and_reserved_names(self):
        for name in [None,"",".","..","/file","../file","lib/../file","lib//file","lib/","C:/file","lib\\file","a:b","a ","a.","\u03bc","CON","nul.txt","COM1.bin","Lpt9"]:
            with self.subTest(name=name):
                files=self.inventory({"one":b""});files[0].path=name;self.open(files,expected=MANIFEST)

    def test_forbidden_configuration_cannot_be_blessed(self):
        for name in ["pyvenv.cfg","lib/PYVENV.cfg","bin/python312._pth","lib/a.pth","lib/sitecustomize.py","lib/usercustomize.cpython-312.pyc"]:
            with self.subTest(name=name):self.open(self.inventory({name:b""}),expected=MANIFEST)

    def test_unsorted_duplicate_case_alias_and_overlap(self):
        for names in [["z","a"],["a","a"],["A","a"],["a","a/b"],["A","a/b"],["A/one","a/two"]]:
            files=self.inventory({"first":b"","second":b""})
            for entry,name in zip(files,names):entry.path=name
            with self.subTest(names=names):self.open(files,expected=MANIFEST)

    def test_inventory_size_and_depth_limits(self):
        self.open(count=8193,expected=LIMIT)
        files=self.inventory({"file":b""});files[0].size=536870913;self.open(files,expected=LIMIT)
        files=self.inventory({"a":b"","b":b"","c":b""})
        for entry in files:entry.size=536870912
        self.open(files,expected=LIMIT)
        for name in ["a"*1024,"a"*256,"/".join(["a"]*33)]:
            files=self.inventory({"file":b""});files[0].path=name
            with self.subTest(name=name):self.open(files,expected=MANIFEST)

    def test_invalid_root_shape(self):
        roots=[None,"","relative",str(self.root)+os.sep,str(self.root)+os.sep+"..",str(self.root)+os.sep+".","x"*4096]
        if os.name=="nt":roots += ["\\\\server\\share","\\\\?\\C:\\path","C:relative"]
        else:roots += ["//tmp/package","/"]
        for root in roots:
            with self.subTest(root=root):self.open(root=root,expected=ROOT_ERROR)

    def test_invalid_unicode_root(self):
        self.open(root=str(self.root)+os.sep+"\ud800",expected=ROOT_ERROR)

    def test_missing_file(self):
        (self.root/"lib/empty").unlink();self.open(expected=MISSING)

    def test_missing_subdirectory(self):
        shutil.rmtree(self.root/"lib/encodings");self.open(expected=MISSING)

    def test_extra_file(self):
        (self.root/"lib/extra.py").write_bytes(b"extra");self.open(expected=UNEXPECTED)

    def test_extra_empty_directory(self):
        (self.root/"empty-extra").mkdir();self.open(expected=UNEXPECTED)

    def test_extra_configuration(self):
        (self.root/"pyvenv.cfg").write_text("home=elsewhere\n",encoding="utf-8");self.open(expected=UNEXPECTED)

    def test_same_length_corruption(self):
        (self.root/"bin/helper").write_bytes(b"x"*len(self.content["bin/helper"]));self.open(expected=DIGEST)

    def test_truncated_or_appended_file(self):
        for data in [b"",self.content["bin/helper"]+b"extra"]:
            with self.subTest(size=len(data)):(self.root/"bin/helper").write_bytes(data);self.open(expected=SIZE)

    def test_directory_in_place_of_file(self):
        (self.root/"bin/helper").unlink();(self.root/"bin/helper").mkdir();self.open(expected=UNEXPECTED)

    def test_hard_link(self):
        os.link(self.root/"bin/helper",self.parent/"external-hardlink");self.open(expected=UNSAFE)

    def test_directory_alias(self):
        moved=self.parent/"moved-lib";shutil.move(str(self.root/"lib"),moved);self.alias(self.root/"lib",moved);self.open(expected=UNSAFE)

    def test_root_alias(self):
        link=self.parent/"root-alias";self.alias(link,self.root);self.open(root=str(link),expected=UNSAFE)

    def test_ancestor_alias(self):
        link=self.parent/"ancestor-alias";self.alias(link,self.parent);self.open(root=str(link/self.root.name),expected=UNSAFE)

    @unittest.skipIf(os.name=="nt","POSIX FIFO; Windows uses reparse and stream cases")
    def test_fifo_without_blocking(self):
        (self.root/"lib/empty").unlink();os.mkfifo(self.root/"lib/empty");self.open(expected=UNSAFE)

    @unittest.skipUnless(os.name=="nt","Windows named streams; POSIX has no NTFS stream namespace")
    def test_alternate_data_stream(self):
        Path(str(self.root/"lib/empty")+":unreviewed").write_bytes(b"unreviewed");self.open(expected=UNSAFE)

    def test_case_alias(self):
        (self.root/"lib/payload.bin").rename(self.root/"lib/PAYLOAD.bin");self.open(expected=UNEXPECTED)

    def test_unlisted_unicode_file(self):
        (self.root/"\u03bc").write_bytes(b"unknown");self.open(expected=UNEXPECTED)

    def test_query_rejection_keeps_destination(self):
        p=self.open()
        for name,kind in [("bin/helper",2),("lib",1),("missing",1),("../file",1),("",1),("BIN/helper",1),("lib/",2),("lib/"+"a"*1024,1)]:
            with self.subTest(name=name):self.query(p,name,kind,NOT_FOUND)
        self.query(p,"lib",99,ARGUMENT)
        out=c.create_unicode_buffer("unchanged",100)
        self.assertEqual(self.api.sw_test_resolve(p,None,1,out,100),ARGUMENT)
        self.assertEqual(self.api.sw_test_resolve(p,"lib",2,None,100),ARGUMENT)

    def test_query_capacity_is_atomic(self):
        p=self.open()
        for capacity in [0,1,len(str(self.root/"bin/helper"))]:self.query(p,"bin/helper",1,CAPACITY,capacity)

    def layout(self, search=None):
        search=["lib","lib/stdlib.zip"] if search is None else search
        array=(c.c_wchar_p*len(search))(*search)
        return Layout("bin/helper","bin/runtime.bin",len(search),array)

    def test_startup_layout_and_owned_lifetime(self):
        package=self.open();layout=self.layout();out=c.c_void_p()
        self.assertEqual(self.api.sw_test_create_paths(package,c.byref(layout),c.byref(out)),OK);self.addCleanup(self.api.sw_test_close_paths,out)
        snapshot=self.api.sw_test_paths_view(out).contents
        expected={name:str(self.root) for name in FIELDS}
        expected.update({name:str(self.root/"bin/helper") for name in ["program_name","executable","base_executable"]})
        self.assertEqual({name:getattr(snapshot,name) for name in FIELDS},expected)
        self.assertEqual([snapshot.search[i] for i in range(snapshot.search_count)],[str(self.root/"lib"),str(self.root/"lib/stdlib.zip")])
        self.assertEqual(self.api.sw_test_library(out),str(self.root/"bin/runtime.bin"))
        self.api.sw_test_close(package);package.value=None
        layout.executable="untrusted";self.assertEqual(self.api.sw_test_paths_view(out).contents.executable,str(self.root/"bin/helper"))

    def test_layout_rejects_missing_duplicate_or_escaping_roles(self):
        package=self.open()
        layouts=[self.layout(search=[]),self.layout(search=["lib","lib"]),self.layout(search=["lib"]*17),self.layout(search=["bin/runtime.bin"]),self.layout(search=["missing"])]
        for field,value in [("executable","helper"),("library","../runtime"),("executable","bin/missing"),("library","bin/helper")]:
            layout=self.layout();setattr(layout,field,value);layouts.append(layout)
        for layout in layouts:
            out=c.c_void_p()
            with self.subTest(layout=layout):self.assertNotEqual(self.api.sw_test_create_paths(package,c.byref(layout),c.byref(out)),OK);self.assertIsNone(out.value)

    def test_regular_file_cannot_be_root(self):
        self.open(root=str(self.root/"bin/helper"),expected=UNSAFE)

    def test_handles_closed_on_success_and_failure(self):
        def count():
            if os.name=="nt":
                value=c.c_ulong();kernel=c.WinDLL("kernel32",use_last_error=True)
                kernel.GetCurrentProcess.restype=c.c_void_p
                kernel.GetProcessHandleCount.argtypes=[c.c_void_p,c.POINTER(c.c_ulong)]
                self.assertTrue(kernel.GetProcessHandleCount(kernel.GetCurrentProcess(),c.byref(value)));return value.value
            return len(os.listdir("/proc/self/fd" if sys.platform.startswith("linux") else "/dev/fd"))
        before=count()
        for _ in range(40):
            out=c.c_void_p();self.assertEqual(self.api.sw_test_open(str(self.root),self.files,len(self.files),c.byref(out)),OK);self.api.sw_test_close(out)
            self.files[0].sha256[0]^=1;out=c.c_void_p();self.assertEqual(self.api.sw_test_open(str(self.root),self.files,len(self.files),c.byref(out)),DIGEST);self.files[0].sha256[0]^=1
        self.assertEqual(count(),before)

if __name__=="__main__":unittest.main()
