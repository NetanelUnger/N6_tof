"""Durable Cloud capture/download using an existing workspace capability file."""
from __future__ import annotations
import base64
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from project_context import atomic, read
from protocol import decode_record, HEADER_SIZE_V4
from sample_sources import Sample, SourceError, SourceStats, utc_now


class SourceComplete(SourceError):
    pass


class CloudApiError(SourceError):
    def __init__(self,status):
        self.status=status
        super().__init__(f'Cloud API HTTP {status}; no re-pairing or credential creation attempted.')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise SourceError('BLOCKED: Cloud endpoint redirected; credentials were not forwarded.')


class CloudSampleSource:
    kind='cloud'
    lossless_replay=True
    def __init__(self,*,endpoint=None,workspace_path=None,project_id=None,state_root=None,
                 capture_session=None,device_id=None,expected_device=None,capture_duration=90,
                 capture_rate=2,capture_count=20,require_no_browser=False,**unused):
        self.endpoint=(endpoint or '').rstrip('/')
        self.workspace_path=Path(workspace_path) if workspace_path else None
        self.project_id=project_id
        self.state_root=Path(state_root) if state_root else None
        self.capture_session=capture_session
        self.device_id=device_id
        self.expected_device=expected_device
        self.capture_duration=capture_duration;self.capture_rate=capture_rate;self.capture_count=capture_count
        self.require_no_browser=require_no_browser
        self.stats=SourceStats();self.connection_id=uuid.uuid4().hex
        self.restore_error=None;self.stop_event=threading.Event();self.committed=threading.Event()
        self.pending=None;self.page=[];self.cursor=0;self.server_active=True;self.server_status={}
        self.opener=urllib.request.build_opener(NoRedirect())

    def _request(self,path,*,method='GET',body=None,public=False,timeout=10):
        headers={} if public else {'Authorization':'Bearer '+self.workspace['workspaceToken']}
        data=None
        if body is not None:
            data=json.dumps(body).encode('utf-8');headers['Content-Type']='application/json'
        request=urllib.request.Request(self.endpoint+path,data=data,headers=headers,method=method)
        try:
            with self.opener.open(request,timeout=timeout) as response:
                raw=response.read(512*1024+1)
                if len(raw)>512*1024:raise SourceError('Cloud response exceeded bounded page size.')
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raise CloudApiError(exc.code) from None
        except urllib.error.URLError as exc:
            if isinstance(exc.reason,TimeoutError):raise TimeoutError('Cloud receive window expired.') from None
            raise SourceError('Cloud endpoint network request failed; cursor was not advanced.') from None

    def _route(self):
        return f'/api/training/projects/{self.project_id}/sessions/{self.capture_session}'

    def open(self):
        parsed=urllib.parse.urlsplit(self.endpoint)
        if (parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or
                parsed.path not in ('','/') or parsed.query or parsed.fragment or
                (parsed.scheme!='https' and parsed.hostname not in ('127.0.0.1','localhost'))):
            raise SourceError('BLOCKED: select a verified HTTPS endpoint; HTTP is permitted only for loopback fixtures.')
        if not self.workspace_path or not self.workspace_path.is_file() or not self.state_root:
            raise SourceError('BLOCKED: select an existing .n6workspace.json authorization file and project.')
        self.workspace=json.loads(self.workspace_path.read_text(encoding='utf-8-sig'))
        if self.workspace.get('format')!='n6-workspace-v1' or not self.workspace.get('workspaceToken'):
            raise SourceError('BLOCKED: invalid existing workspace file.')
        uuid.UUID(self.project_id)
        capabilities=self._request('/api/training/capabilities',public=True)
        if not (capabilities.get('captureVersion')==1 and capabilities.get('record')=='N6DF4' and capabilities.get('persistent')):
            raise SourceError('BLOCKED: deploy a compatible durable receiver before capture.')
        auth=self._request('/api/training/auth')
        if auth.get('workspaceId')!=self.workspace['workspaceId']:
            raise SourceError('BLOCKED: endpoint and existing workspace authorization differ.')
        self.browser=self._request('/api/training/browser-state')
        if self.require_no_browser and self.browser.get('browserAttached'):
            raise SourceError('BLOCKED: an existing browser workspace is attached; close it before the no-browser HIL.')
        allowed={d['id'] for d in self.workspace.get('devices',[])}
        if not self.device_id and len(allowed)==1:self.device_id=next(iter(allowed))
        if self.device_id not in allowed:
            raise SourceError('BLOCKED: select a device listed in the existing workspace file.')
        if not self.expected_device or not re.fullmatch(r'n6:[0-9a-f]{2}(:[0-9a-f]{2}){5}',self.expected_device):
            raise SourceError('BLOCKED: select the verified canonical N6 MAC identity.')
        self.state_folder=self.state_root/'cloud_download';self.state_folder.mkdir(parents=True,exist_ok=True)
        if not self.capture_session:
            pending_path=self.state_folder/'creation_pending.json'
            request={'projectId':self.project_id,'deviceId':self.device_id,'canonicalDeviceId':self.expected_device,
                     'durationSeconds':self.capture_duration,'rateHz':self.capture_rate,
                     'maximumSamples':self.capture_count,'maximumBytes':self.capture_count*8192}
            scope={'endpoint':self.endpoint,'workspace_id':self.workspace['workspaceId'],'request':request}
            previous=read(pending_path) if pending_path.exists() else None
            if previous and previous.get('status')=='prepared':
                if previous['scope']!=scope:raise SourceError('BLOCKED: resolve the prior uncertain Cloud creation before changing its request.')
                identifier=previous['idempotency_key']
            else:identifier=uuid.uuid4().hex
            atomic(pending_path,{'status':'prepared','scope':scope,'idempotency_key':identifier})
            try:
                result=self._request(f'/api/training/projects/{self.project_id}/sessions',method='POST',
                                     body={**request,'idempotencyKey':identifier})
            except CloudApiError as exc:
                if exc.status in (400,401,403,404,409,413,422):
                    atomic(pending_path,{'status':'rejected','scope':scope,'idempotency_key':identifier,'http_status':exc.status})
                raise
            self.capture_session=result['id']
            if self.capture_session!=identifier:raise SourceError('Cloud creation did not resolve the requested idempotent session.')
            atomic(pending_path,{'status':'acknowledged','scope':scope,'idempotency_key':identifier,'session':self.capture_session})
        if not re.fullmatch('[a-f0-9]{32}',self.capture_session):raise SourceError('Invalid Cloud capture session identifier.')
        self.cursor_path=self.state_folder/(self.capture_session+'.json')
        self.scope={'endpoint':self.endpoint,'workspace_id':self.workspace['workspaceId'],'project_id':self.project_id,
                    'session':self.capture_session,'device_id':self.device_id,'canonical_device_id':self.expected_device}
        if self.cursor_path.exists():
            state=read(self.cursor_path)
            if state['scope']!=self.scope:raise SourceError('BLOCKED: cursor belongs to another endpoint/project/device.')
            self.cursor=int(state['committed_cursor'])
        self.server_status=self._request(self._route())
        session=self.server_status['session']
        if session['projectId']!=self.project_id or session['deviceId']!=self.device_id or session['canonicalDeviceId']!=self.expected_device:
            raise SourceError('BLOCKED: server capture association differs from the selected project/device.')
        self.stats.state='streaming'

    def read(self,timeout=3):
        deadline=time.monotonic()+timeout
        if self.pending is not None:
            self.committed.wait(timeout=max(.001,deadline-time.monotonic()))
            if self.pending is not None:raise TimeoutError('Waiting for local durable commit before advancing Cloud cursor.')
        while not self.stop_event.is_set() and time.monotonic()<deadline:
            if not self.page:
                response=self._request(self._route()+f'/samples?after={self.cursor}&limit=8',timeout=max(.1,deadline-time.monotonic()))
                self.server_active=bool(response['active']);self.page=response['samples']
                if len(self.page)>8:raise SourceError('Cloud sample page exceeded bounded capacity.')
                if not self.page:
                    if not self.server_active:
                        self.stats.state='complete';raise SourceComplete('Cloud capture completed; all available records downloaded.')
                    self.stop_event.wait(min(.1,max(0,deadline-time.monotonic())));continue
            row=self.page.pop(0)
            if (row['projectId']!=self.project_id or row['workspaceId']!=self.workspace['workspaceId'] or
                    row['sessionId']!=self.capture_session or row['deviceId']!=self.device_id or
                    row['canonicalDeviceId']!=self.expected_device or row['cursor']!=self.cursor+1):
                raise SourceError('Cloud record association/cursor gap; nothing committed.')
            wire=base64.b64decode(row['dataBase64'],validate=True)
            if len(wire)>8192 or len(wire)!=row['bytes'] or hashlib.sha256(wire).hexdigest()!=row['sha256']:
                raise SourceError('Cloud record integrity differs from durable server metadata.')
            frame=decode_record(wire[:HEADER_SIZE_V4],wire[HEADER_SIZE_V4:])
            if frame.frame_id!=row['frameId'] or frame.timestamp_ms!=row['timestampMs'] or frame.contract_sha256!=row['contractSha256']:
                raise SourceError('Cloud source bytes differ from received identity/contract metadata.')
            sample=Sample(frame,self.expected_device,row['bootId'],self.connection_id,self.kind,utc_now(),time.monotonic_ns(),
                device_info={'cloud_session':self.capture_session,'cloud_cursor':row['cursor'],
                             'server_received_utc':row['receivedUtc'],'server_wire_sha256':row['sha256'],
                             'authorization_source':'existing_workspace_capability'})
            self.pending=sample;self.committed.clear();self.stats.received+=1
            return sample
        self.stats.timeouts+=1
        raise TimeoutError('No durable Cloud record in this receive window.')

    def acknowledge(self,sample):
        if self.pending is not sample:raise SourceError('Cloud acknowledgement does not match the pending source sample.')
        cursor=sample.device_info['cloud_cursor']
        if cursor!=self.cursor+1:raise SourceError('Cloud committed cursor is not contiguous.')
        atomic(self.cursor_path,{'scope':self.scope,'committed_cursor':cursor,'updated_utc':utc_now()})
        self.cursor=cursor;self.pending=None;self.committed.set()

    def stop(self):
        self.stop_event.set();self.committed.set()
        self.stats.state='closed'
        # Closing TRAINING stops downloading, not the bounded server capture.
        # The user can explicitly stop that session, or its deadline/count ends it.

    def status(self):
        return {**asdict(self.stats),'source':self.kind,'endpoint':self.endpoint,'project_id':self.project_id,
                'server_session':self.capture_session,'connection_id':self.connection_id,'committed_cursor':self.cursor,
                'server_status_at_open':self.server_status,'browser':getattr(self,'browser',None),
                'restore_error':self.restore_error,'server_capture_independent_of_downloader':True}
