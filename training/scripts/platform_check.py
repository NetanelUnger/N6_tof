"""Short BAT platform checks with explicit execution scope and durable reports."""
from __future__ import annotations
import argparse,json,os,subprocess,sys,time,uuid
from pathlib import Path
from common import (PROJECT_MANIFEST,PROJECT_ID,TRAINING_ENTRY_ROOT,TRAINING_ROOT,
                    REPORTS_ROOT,RAW_ROOT,NON_INTERACTIVE,stage_state,sha256_file,
                    atomic_json,utc_now,PROJECT_ROOT)
from project_context import ProjectService,read


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transport',choices=('usb','ble','cloud'),default='usb')
    parser.add_argument('--capture',action='store_true',help='Perform a new bounded real capture; never implied by report verification.')
    parser.add_argument('--verify-stored',action='store_true',help='Verify existing lossless records; this is not a new transport HIL.')
    parser.add_argument('--existing-session')
    parser.add_argument('--hil',action='store_true',help='Perform one100-frame HIL on an already loaded exact Stage10 candidate.')
    parser.add_argument('--package-version',type=int)
    parser.add_argument('--ui-workflow',action='store_true')
    parser.add_argument('--skip-host-tests',action='store_true')
    parser.add_argument('--endpoint');parser.add_argument('--workspace-file');parser.add_argument('--cloud-device-id')
    parser.add_argument('--expected-device');parser.add_argument('--device');parser.add_argument('--port')
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    if not NON_INTERACTIVE:
        import tkinter as tk
        from tkinter import ttk
        root=tk.Tk();root.title('N6 platform check');frame=ttk.Frame(root,padding=18);frame.pack()
        service=ProjectService(TRAINING_ENTRY_ROOT);projects=service.list_projects()
        project=tk.StringVar(value=PROJECT_MANIFEST['slug'] if PROJECT_MANIFEST else '')
        transport=tk.StringVar(value=args.transport);chosen=[]
        ttk.Label(frame,text='Project').pack(anchor='w');ttk.Combobox(frame,textvariable=project,values=[p['slug'] for p in projects],state='readonly').pack()
        ttk.Label(frame,text='Transport').pack(anchor='w');ttk.Combobox(frame,textvariable=transport,values=['usb','ble','cloud'],state='readonly').pack()
        ttk.Label(frame,text='Checks saved artifacts and host logic. New capture/HIL require explicit options.',wraplength=350).pack(pady=10)
        def start():
            if project.get():chosen.extend([project.get(),transport.get()]);root.destroy()
        ttk.Button(frame,text='Run check',command=start).pack();root.mainloop()
        if not chosen:return 2
        return subprocess.call([sys.executable,str(Path(__file__).resolve()),*sys.argv[1:],'--project',chosen[0],'--transport',chosen[1],'--non-interactive'])
    folder=REPORTS_ROOT/'platform_check'/uuid.uuid4().hex;folder.mkdir(parents=True)
    report=args.report or folder/'report.json';checks=[];started=time.monotonic()
    def note(name,status,kind,**details):
        item={'check':name,'status':status,'evidence_kind':kind,**details};checks.append(item)
        print(json.dumps(item,ensure_ascii=True),flush=True)
    def command(name,argv,timeout,kind):
        tick=time.monotonic();log=folder/(name+'.log')
        try:
            with log.open('w',encoding='utf-8') as stream:
                result=subprocess.run(argv,cwd=Path(__file__).resolve().parents[1],stdout=stream,stderr=subprocess.STDOUT,timeout=timeout)
            output=log.read_text(encoding='utf-8',errors='replace')
            status='PASS' if result.returncode==0 else 'BLOCKED' if 'BLOCKED:' in output else 'FAIL'
            note(name,status,kind,seconds=round(time.monotonic()-tick,3),exit_code=result.returncode,log=str(log))
            return status=='PASS'
        except subprocess.TimeoutExpired:
            note(name,'FAIL',kind,seconds=round(time.monotonic()-tick,3),reason='Timeout; inspect device/session outcome before any retry.',log=str(log));return False
    bat=lambda name,*extra:['cmd.exe','/d','/c',str(Path(__file__).resolve().parents[1]/name),'--project',PROJECT_MANIFEST['slug'],'--non-interactive',*extra]
    if not PROJECT_MANIFEST:
        note('project','BLOCKED','configuration',reason='Select or import a project through00_PROJECT.bat.')
    else:
        value=ProjectService(TRAINING_ENTRY_ROOT).open(PROJECT_MANIFEST['slug'])
        note('project','PASS','configuration',project_id=PROJECT_ID,classes=len(value['classes']),input_profile=value['input_profile'])
        command('status_bat',bat('99_STATUS_RESUME.bat'),30,'BAT workflow')
        if not args.skip_host_tests:
            command('host_native',['.venv/Scripts/python.exe','-B','-m','unittest','discover','-s','scripts','-p','test_*.py'],60,'host/native fixtures; no HIL')
        else:note('host_native','NOT RUN','host/native fixtures',reason='Explicitly skipped.')
        if args.ui_workflow:
            command('ui_workflow',[sys.executable,'-B','scripts/check_class_workflow.py'],60,'BAT-launched Tk widgets on temporary fixtures; no native pixel assertions')
        else:note('ui_workflow','NOT RUN','UI',reason='Use --ui-workflow for isolated wizard/label/BAT automation.')
        if args.verify_stored:
            try:
                from sample_store import verify_record
                files=sorted((RAW_ROOT/args.existing_session).glob('metadata.jsonl')) if args.existing_session else sorted(RAW_ROOT.glob('*/metadata.jsonl'))
                rows=[json.loads(line) for p in files for line in p.read_text(encoding='utf-8').splitlines() if line.strip()]
                rows=[r for r in rows if r.get('sample_schema')==1 and r.get('source')==args.transport]
                required=25 if args.transport=='ble' else 20
                if len(rows)<required:raise RuntimeError(f'BLOCKED: {len(rows)}/{required} retained {args.transport} records available.')
                for row in rows:verify_record(TRAINING_ROOT,row,PROJECT_MANIFEST)
                note('stored_records','PASS','read-only source record integrity; not a fresh transport HIL',samples=len(rows),transport=args.transport,unique=len({r['sample_id'] for r in rows}))
            except Exception as exc:note('stored_records','BLOCKED' if str(exc).startswith('BLOCKED:') else 'FAIL','stored records',reason=str(exc))
        if args.capture:
            try:
                from guarded_ram import hardware_lease
                extra=['--transport',args.transport,'--unlabeled','--disable-content-filter']
                if args.transport=='cloud':extra.append('--require-no-browser')
                for key in ('endpoint','workspace_file','cloud_device_id','expected_device','device','port'):
                    if getattr(args,key):extra.extend(['--'+key.replace('_','-'),getattr(args,key)])
                limit=60 if args.transport=='usb' else 120;tick=time.monotonic()
                suffix=uuid.uuid4().hex[:12]
                with hardware_lease('platform-capture-'+suffix):
                    for count,part in ((20,'capture'),(5,'reconnect')) if args.transport=='ble' else ((20,'capture'),):
                        remaining=limit-(time.monotonic()-tick)
                        if remaining<=0:note('capture_deadline','FAIL','real transport HIL',reason='Shared capture budget expired.');break
                        if not command(part,bat('01_CAPTURE.bat',*extra,'--session','platform-'+suffix+'-'+part,'--samples',str(count),'--timeout',str(remaining),'--report',str(folder/(part+'.json'))),remaining+5,'real bounded transport HIL'):break
                if args.transport=='cloud' and (folder/'capture.json').exists():
                    from cloud_sample_source import CloudSampleSource,SourceComplete
                    received=read(folder/'capture.json');session=received.get('source',{}).get('server_session')
                    if session:
                        from common import STATE_ROOT
                        source=CloudSampleSource(endpoint=args.endpoint,workspace_path=args.workspace_file,project_id=PROJECT_ID,
                            state_root=STATE_ROOT,capture_session=session,device_id=args.cloud_device_id,expected_device=args.expected_device,require_no_browser=True)
                        try:
                            source.open()
                            if received.get('status')=='PASS':
                                try:source.read(3)
                                except SourceComplete:pass
                                else:raise RuntimeError('Resume returned an uncommitted or duplicate sample.')
                                note('cloud_cursor_resume','PASS','real durable downloader resume',cursor=source.cursor,resumed_records=source.stats.received)
                        except Exception as exc:note('cloud_cursor_resume','FAIL','real downloader',reason=str(exc))
                        finally:
                            try:
                                if source.server_status.get('active'):
                                    source._request(source._route()+'/stop',method='POST',body={})
                            finally:source.stop()
            except Exception as exc:
                note('capture_setup','BLOCKED' if 'BLOCKED:' in str(exc) else 'FAIL','bounded transport check',reason=str(exc))
        else:note('live_capture','NOT RUN','live transport HIL',reason='No new capture requested; existing records are checked separately.')
        if args.hil:command('npu_hil',bat('11_HIL.bat','--frames','100'),185,'real NPU HIL')
        else:note('live_npu_hil','NOT RUN','live NPU HIL',reason='No new hardware inference run requested.')
        if args.package_version is not None:command('package_only',bat('12_FLASH_RELEASE.bat','--package-only','--version',str(args.package_version)),90,'exact HIL-bound package; no persistent installation')
        from common import npu_deployment_fingerprint
        try: current_deployment=npu_deployment_fingerprint()
        except RuntimeError: current_deployment=None
        for name in ('03_validate','04_prepare','05_train','06_quantize','07_generate_n6','08_integrate','10_ram','11_hil','12_package'):
            state=stage_state(name);status=state.get('status')
            if name in ('10_ram','11_hil','12_package') and status=='complete' and state.get('input_fingerprint')!=current_deployment:
                status='stale';state={**state,'reason':'Current integrated source differs from this saved acceptance; reload/revalidate before reuse.'}
            note('saved_'+name,'PASS' if status=='complete' else 'FAIL' if status in ('failed','quality_gate_failed') else 'NOT RUN',
                 'saved project stage; not a new execution',state=status or 'absent',updated_utc=state.get('updated_utc'),
                 input_fingerprint=state.get('input_fingerprint'),reason=state.get('reason'))
    note('persistent_installation','NOT RUN','out of smoke scope',reason='Never performed by90_PLATFORM_CHECK.')
    from common import MODELS_ROOT
    artifacts={p.name:sha256_file(p) for p in (MODELS_ROOT/'rps_int8.tflite',MODELS_ROOT/'model_contract.json') if p.exists()}
    result={'artifacts':artifacts,'schema':1,'project_id':PROJECT_ID,'transport':args.transport,'created_utc':utc_now(),
            'status':'FAIL' if any(c['status']=='FAIL' for c in checks) else 'BLOCKED' if any(c['status']=='BLOCKED' for c in checks) else 'PASS',
            'seconds':round(time.monotonic()-started,3),'checks':checks,'new_cloud_capture_requested':args.capture and args.transport=='cloud'}
    atomic_json(report,result)
    readable=report.with_suffix(".txt");readable.write_text(chr(10).join([f"N6 platform check: {result['status']}",f"Project: {PROJECT_ID}; transport: {args.transport}",*[f"{c['status']:7s} {c['check']}: {c.get('reason',c['evidence_kind'])}" for c in checks]])+chr(10),encoding="utf-8")
    print(json.dumps({'status':result['status'],'report':str(report),'readable':str(readable)},ensure_ascii=True))
    return 0 if result['status']=='PASS' else 2

if __name__=='__main__':raise SystemExit(main())
