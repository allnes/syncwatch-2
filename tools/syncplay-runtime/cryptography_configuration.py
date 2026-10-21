"""Select owned Python headers and import libraries in upstream's build script."""

from pathlib import Path
import re


def configure(source):
    path = source / "src/rust/cryptography-cffi/build.rs"
    original = path.read_text(encoding="utf-8")
    text, count = re.subn(r'(?ms)^    let python_includes = .*?^    };',
        '    let python_includes = env::var("SYNCWATCH_PYTHON_INCLUDE")\n'
        '        .expect("owned Python headers are required");', original)
    if count != 1:
        raise ValueError("Original cryptography header configuration differs")
    text, count = re.subn(r'(?ms)^        let libs_dir = run_python_script\(.*?^        \.unwrap\(\);',
        '        let libs_dir = env::var("SYNCWATCH_PYTHON_LIB")\n'
        '            .expect("owned Python import libraries are required");', text)
    if count != 1:
        raise ValueError("Original cryptography Windows library configuration differs")
    path.write_text("// SyncWatch 2026-10-22: use explicit source-built Python SDK paths; no setuptools lookup.\n"
                    + text, encoding="utf-8", newline="\n")
