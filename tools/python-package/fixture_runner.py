"""Run actual native C API cases in an owned developer-SDK process."""
import argparse
import json
import os
from pathlib import Path
import unittest

class RecordingResult(unittest.TextTestResult):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.cases={}
    def addSuccess(self,test):
        super().addSuccess(test)
        self.cases[test.id().split('.')[-1]]={"status":"passed"}
    def addSkip(self,test,reason):
        super().addSkip(test,reason)
        self.cases[test.id().split('.')[-1]]={"status":"skipped","reason":reason}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    os.environ['SYNCWATCH_PACKAGE_TEST_MODULE']=str(args.module.resolve(strict=True))
    suite=unittest.defaultTestLoader.discover(str(Path(__file__).parent/'tests'))
    result=unittest.TextTestRunner(verbosity=2,resultclass=RecordingResult).run(suite)
    report={'passed':result.wasSuccessful(),'cases':result.cases,'testsRun':result.testsRun,
            'failures':len(result.failures),'errors':len(result.errors),'skips':len(result.skipped)}
    args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if report['passed'] else 1)

if __name__=='__main__':main()
