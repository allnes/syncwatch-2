"""Compile and execute the shared package verifier on the native host; package no SDK."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from package_sdk import ROOT, build


def probe():
    with tempfile.TemporaryDirectory(prefix='sw-package-native-') as temporary:
        root=Path(temporary).resolve()
        module,identity=build(root)
        report=root/'cases.json'
        command=[sys.executable,str(ROOT/'tools/python-package/fixture_runner.py'),'--module',str(module),'--report',str(report)]
        with tempfile.TemporaryFile() as log:
            result=subprocess.run(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=120)
            log.seek(0);output=log.read(65537)
        if result.returncode or len(output)>65536:
            raise ValueError('Native package API fixtures failed:\n'+output[-32768:].decode('utf-8',errors='replace'))
        data=json.loads(report.read_text(encoding='utf-8'))
        profile=json.loads((ROOT/'tools/python-package/profile.json').read_text(encoding='utf-8'))
        if profile['schemaVersion'] != 1 or profile['runtimeReady'] is not False:
            raise ValueError('Unknown native package verification profile')
        expected_skips={name for name,targets in profile['platformOnly'].items() if identity['compiler']['target'] not in targets}
        if (data['passed'] is not True or set(data['cases'])!=set(profile['cases']) or data['testsRun']!=len(profile['cases'])
            or data['failures'] or data['errors'] or data['skips']!=len(expected_skips)
            or {name for name,case in data['cases'].items() if case['status']=='skipped'}!=expected_skips
            or any(case['status'] not in {'passed','skipped'} for case in data['cases'].values())):
            raise ValueError('Native package case set or platform scope differs')
        return identity|{'nativePackageVerification':data,'inventoryAuthenticityVerified':False,'installationImmutabilityVerified':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path)
    args=parser.parse_args();result=probe();data=json.dumps(result,indent=2,sort_keys=True)+'\n'
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(data,encoding='utf-8')
    print(data,end='')

if __name__=='__main__':main()
