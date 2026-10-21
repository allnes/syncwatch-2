"""Owned ports for the unchanged CPython Unicode generator, in an isolated child."""

import argparse
import importlib.util
import io
from pathlib import Path
import sys
import zipfile

from unicode_oracle import UCD, interchange

INPUTS = ("UnicodeData.txt", "NameAliases.txt", "NamedSequences.txt", "CompositionExclusions.txt",
          "EastAsianWidth.txt", "DerivedCoreProperties.txt", "LineBreak.txt", "DerivedNormalizationProps.txt",
          "Unihan.zip", "SpecialCasing.txt", "CaseFolding.txt")


class Ports:
    def __init__(self, unicode, destination):
        self.unicode, self.destination, self.reads = unicode, destination, []

    def read(self, template, version):
        name = template.replace("%s", "")
        if version != "15.0.0" or name not in INPUTS or name in self.reads:
            raise ValueError("Unreviewed Unicode generator input or version")
        self.reads.append(name)
        if name == "Unihan.zip":
            # Explicit derived interchange; original range-compressed sources stay in sources.zip.
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
                entry = zipfile.ZipInfo("Unihan_NumericValues.txt", date_time=(1980, 1, 1, 0, 0, 0))
                entry.create_system = 3
                entry.external_attr = 0o100644 << 16
                archive.writestr(entry, interchange(self.unicode))
            return io.BytesIO(output.getvalue())
        return io.StringIO(self.unicode[UCD + name].decode("utf-8"))

    def write(self, name, mode):
        if name != "Objects/unicodetype_db.h" or mode != "w" or self.destination.exists():
            raise ValueError("Unreviewed Unicode generator output")
        return self.destination.open("x", encoding="ascii", newline="\n")


def generate(cpython, unicode, output):
    path = cpython / "Tools/unicode/makeunicodedata.py"
    spec = importlib.util.spec_from_file_location("pinned_unicode_generator", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    ports = Ports(unicode, output)
    module.SCRIPT = "Tools/unicode/makeunicodedata.py"
    module.open_data, module.open = ports.read, ports.write
    if module.UNIDATA_VERSION != "15.0.0" or module.VERSION != "3.3":
        raise ValueError("Original Unicode generator has an unexpected version")
    def offline(event, _args):
        if event.startswith(("socket.", "subprocess.", "urllib.")) or event in {"os.system", "os.posix_spawn", "os.fork", "os.exec"}:
            raise ValueError("Unicode generation cannot use network or subprocess operations")
    sys.addaudithook(offline)
    module.makeunicodetype(module.UnicodeData("15.0.0"), 0)
    if ports.reads != list(INPUTS):
        raise ValueError("Unicode generation did not consume its exact reviewed input graph")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cpython", type=Path)
    parser.add_argument("unicode", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    # This executable is invoked with -I; only our own adjacent modules are added by the launcher.
    files = {p.relative_to(args.unicode).as_posix(): p.read_bytes() for p in args.unicode.rglob("*") if p.is_file()}
    generate(args.cpython, files, args.output)
