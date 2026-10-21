"""Reject stale/tampered release inputs before any signing or hardware action."""
from copy import deepcopy
import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import verified_package as release

class VerifiedRelease(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.models=self.root/'models';self.reports=self.root/'reports';self.models.mkdir();self.reports.mkdir()
        (self.models/'rps_int8.tflite').write_bytes(b'fixture reference model')
        (self.models/'model_contract.json').write_text('{}')
        self.candidate={'firmware_version':12,'artifacts':{}}
        for extension in ('bin','elf','map'):
            p=self.root/('candidate.'+extension);p.write_bytes(('verified '+extension).encode())
            self.candidate['artifacts'][p.name]={'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
        self.report={'result':'pass','frames':100,'elapsed_seconds':50,'ram_candidate':deepcopy(self.candidate),
                     'model_sha256':hashlib.sha256((self.models/'rps_int8.tflite').read_bytes()).hexdigest()}
        self.states={'10_ram':{'status':'complete','input_fingerprint':'matching','details':{'candidate':self.candidate}},
                     '11_hil':{'status':'complete','input_fingerprint':'matching'}}
        self.patchers=[patch.object(release,'npu_deployment_fingerprint',return_value='matching'),
                       patch.object(release,'stage_state',side_effect=lambda name:self.states[name]),
                       patch.object(release,'MODELS_ROOT',self.models),patch.object(release,'REPORTS_ROOT',self.reports),
                       patch.object(release,'run')]
        values=[p.start() for p in self.patchers];self.sign=values[-1]
    def tearDown(self):
        for p in reversed(self.patchers):p.stop()
        self.temp.cleanup()
    def denied(self,version=12):
        (self.reports/'hil_validation.json').write_text(json.dumps(self.report))
        with self.assertRaisesRegex(RuntimeError,'BLOCKED:'):release.package_verified(version)
        self.sign.assert_not_called()
    def test_foreign_or_stale_hil_never_signs(self):
        self.states['11_hil']['input_fingerprint']='other-project-or-source';self.denied()
    def test_changed_candidate_bytes_never_sign(self):
        (self.root/'candidate.bin').write_bytes(b'tampered');self.denied()
    def test_different_reference_model_never_signs(self):
        (self.models/'rps_int8.tflite').write_bytes(b'other-model');self.denied()
    def test_version_and_short_coverage_never_sign(self):
        self.denied(13);self.report['frames']=99;self.denied()

if __name__=='__main__':unittest.main()
