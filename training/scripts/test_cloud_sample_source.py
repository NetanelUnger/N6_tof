import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from cloud_sample_source import CloudSampleSource, SourceComplete, CloudApiError
from sample_sources import SourceError
from sample_store import SampleStore, DuplicateSample
from protocol import decode_record


class DurableDownload(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        training=Path(__file__).resolve().parents[1]
        self.cfg=json.loads((training/'config/preprocessing.json').read_text(encoding='utf-8'))
        self.project=str(uuid.uuid4());self.session=uuid.uuid4().hex
        self.workspace={'format':'n6-workspace-v1','workspaceId':'fixture-workspace',
                        'workspaceToken':'synthetic-fixture-not-a-production-credential',
                        'devices':[{'id':'fixture-device'}]}
        self.workspace_path=self.root/'fixture.n6workspace.json'
        self.workspace_path.write_text(json.dumps(self.workspace),encoding='utf-8')
        self.wire=(training/'testdata/two-class-production-c.n6df').read_bytes()
        frame=decode_record(self.wire[:132],self.wire[132:])
        self.row={'projectId':self.project,'workspaceId':'fixture-workspace','sessionId':self.session,
                  'deviceId':'fixture-device','canonicalDeviceId':'n6:40:82:7b:03:b8:fa',
                  'cursor':1,'dataBase64':base64.b64encode(self.wire).decode(),'bytes':len(self.wire),
                  'sha256':hashlib.sha256(self.wire).hexdigest(),'frameId':frame.frame_id,
                  'timestampMs':frame.timestamp_ms,'contractSha256':frame.contract_sha256,
                  'bootId':'ab'*16,'receivedUtc':'2026-10-21T00:00:00Z'}
        self.manifest={'project_id':self.project,'classes':[{'name':'rock'}]}

    def tearDown(self):self.temp.cleanup()

    def source(self):
        source=CloudSampleSource(endpoint='https://fixture.invalid',workspace_path=self.workspace_path,
            project_id=self.project,state_root=self.root/'state',capture_session=self.session,
            expected_device='n6:40:82:7b:03:b8:fa')
        def request(path,**kwargs):
            if path.endswith('capabilities'):return {'captureVersion':1,'record':'N6DF4','persistent':True}
            if path.endswith('/auth'):return {'workspaceId':'fixture-workspace'}
            if path.endswith('browser-state'):return {'browserAttached':False,'browserRequired':False}
            if '/samples?' in path:return {'samples':[dict(self.row)] if 'after=0&' in path else [],'active':False}
            return {'session':{'projectId':self.project,'deviceId':'fixture-device','canonicalDeviceId':'n6:40:82:7b:03:b8:fa'}}
        source._request=request;source.open();return source

    def test_crash_after_local_commit_resumes_without_duplicate_or_token_copy(self):
        store=SampleStore(self.root,self.manifest,self.cfg,'download')
        try:
            source=self.source();sample=source.read();store.commit(sample)
            self.assertEqual(source.cursor,0);self.assertFalse(source.cursor_path.exists())
            source.stop()
            resumed=self.source();sample=resumed.read()
            with self.assertRaises(DuplicateSample):store.commit(sample)
            resumed.acknowledge(sample)
            self.assertEqual(resumed.cursor,1)
            self.assertEqual(len(store.records()),1)
            final=self.source()
            with self.assertRaises(SourceComplete):final.read()
            final.stop();resumed.stop()
            self.assertNotIn(self.workspace['workspaceToken'],json.dumps(store.records())+json.dumps(resumed.status())+resumed.cursor_path.read_text())
        finally:store.close()

    def test_corrupt_or_cross_project_download_never_advances_cursor(self):
        for change in ({'projectId':str(uuid.uuid4())},{'dataBase64':base64.b64encode(b'corrupt').decode()}):
            original=dict(self.row);self.row.update(change)
            source=self.source()
            with self.assertRaises(SourceError):source.read()
            self.assertEqual(source.cursor,0);self.assertFalse(source.cursor_path.exists())
            source.stop();self.row=original

    def test_production_plain_http_is_rejected_before_authorization(self):
        source=CloudSampleSource(endpoint='http://example.com',workspace_path=self.workspace_path,
            project_id=self.project,state_root=self.root/'state',expected_device='n6:40:82:7b:03:b8:fa')
        with self.assertRaisesRegex(SourceError,'HTTPS'):source.open()

    def test_uncertain_creation_reuses_the_prepared_request(self):
        source=self.source();source.capture_session=None
        original=source._request
        def uncertain(path,**kwargs):
            if kwargs.get('method')=='POST':raise TimeoutError('fixture lost response')
            return original(path,**kwargs)
        source._request=uncertain
        with self.assertRaises(TimeoutError):source.open()
        pending_path=self.root/'state/cloud_download/creation_pending.json'
        pending=json.loads(pending_path.read_text());self.assertEqual(pending['status'],'prepared')
        def recovered(path,**kwargs):
            if kwargs.get('method')=='POST':return {'id':kwargs['body']['idempotencyKey']}
            return original(path,**kwargs)
        source._request=recovered;source.open()
        self.assertEqual(source.capture_session,pending['idempotency_key'])
        self.assertEqual(json.loads(pending_path.read_text())['status'],'acknowledged')
        source.stop()

    def test_definite_rejection_does_not_strand_an_uncertain_request(self):
        source=self.source();source.capture_session=None
        original=source._request
        def rejected(path,**kwargs):
            if kwargs.get('method')=='POST':raise CloudApiError(400)
            return original(path,**kwargs)
        source._request=rejected
        with self.assertRaises(CloudApiError):source.open()
        pending_path=self.root/'state/cloud_download/creation_pending.json'
        self.assertEqual(json.loads(pending_path.read_text())['status'],'rejected')
        source.stop()


if __name__=='__main__':unittest.main()
