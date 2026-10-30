"""Read-only, project-scoped artifact and prior-assistant evidence inventory."""
from pathlib import Path
from datetime import datetime, timezone
import json, os, re, struct, hashlib, subprocess

BASE=Path(r'C:\Users\netan\Dropbox\DevelopPersonal')
OUT=Path(__file__).resolve().parent/'evidence/st67-cp2-20261028'
OUT.mkdir(exist_ok=True)
roots=[BASE/'N6', BASE/'Web_N6_ST67W611M1_VL53L9CX']
skip={'.git','.data-protection-keys','keys','node_modules','.venv','venv','__pycache__','.sandbox-secrets'}
pattern=re.compile(r'(?i)(?:\b[ABV]51\b|version["\s_:=\\rnt-]{1,24}51\b|confirmed["\s_:=\\rnt-]{1,24}51\b|FirmwareVersion\s+51\b|גרסה\s+51\b)')
report={'started_utc':datetime.now(timezone.utc).isoformat(),'roots':[str(p) for p in roots],
        'excluded_directory_names':sorted(skip),'packages':[],'candidate_paths':[],
        'text_hits':[],'session_summaries':[],'errors':[],'counts':{}}
counts={'walk_files':0,'text_files':0,'package_headers':0,'recent_build_artifacts':0}
cutoff=datetime(2026,10,27,0,0,tzinfo=timezone.utc).timestamp()
for root in roots:
    for folder,dirs,files in os.walk(root):
        dirs[:]=[d for d in dirs if d.lower() not in skip]
        for name in files:
            counts['walk_files']+=1;p=Path(folder)/name;ext=p.suffix.lower();low=name.lower()
            if any(s in low for s in ['secret','credential','token','private','password','.env','auth.json']):continue
            try:
                stat=p.stat()
                if ext=='.n6fw':
                    with p.open('rb') as f:head=f.read(256)
                    counts['package_headers']+=1
                    if len(head)==256 and head[:4]==b'N6UP':
                        version=struct.unpack_from('<I',head,20)[0]
                        report['packages'].append({'path':str(p),'version':version,'size':stat.st_size,
                            'sha256':hashlib.sha256(p.read_bytes()).hexdigest() if version>=49 else None})
                if stat.st_mtime>=cutoff and ext in {'.n6fw','.elf','.bin','.hex','.map'}:
                    counts['recent_build_artifacts']+=1
                    report['candidate_paths'].append({'path':str(p),'bytes':stat.st_size,
                        'modified_utc':datetime.fromtimestamp(stat.st_mtime,timezone.utc).isoformat()})
                # Inspect recent project outputs/docs; exclude general source/data and binary payloads.
                if ext not in {'.json','.log','.md','.txt'} or stat.st_size>15_000_000 or stat.st_mtime<cutoff:continue
                if '.local-dependencies' not in p.parts and not any(x in p.parts for x in ['docs','FlashImages','reports','publish']):continue
                counts['text_files']+=1
                content=p.read_text(encoding='utf-8',errors='replace')
                matches=list(pattern.finditer(content))
                if matches:
                    # Report only the matched version phrase, avoiding adjacent credentials/payloads.
                    report['text_hits'].append({'path':str(p),'matches':[m.group(0) for m in matches[:10]],'total':len(matches)})
            except OSError as e:report['errors'].append({'path':str(p),'error':type(e).__name__})
    print(json.dumps({'scanned':str(root),'counts':counts,'hits':len(report['text_hits'])}),flush=True)

# Only assistant messages in recent N6 sessions; no tool arguments, outputs,
# hidden reasoning, settings, authentication files or unrelated conversations.
sessionroot=Path(r'C:\Users\netan\.codex\sessions\2026\10')
for day in ('26','27','28'):
    for p in (sessionroot/day).glob('*.jsonl'):
        with p.open(encoding='utf-8') as f:
            first=json.loads(f.readline());meta=first.get('payload',{})
            if 'DevelopPersonal\\N6' not in meta.get('cwd',''):continue
            item={'path':str(p),'thread_id':meta.get('id'),'cwd':meta.get('cwd'),'assistant_version51_mentions':[]}
            for line in f:
                if '"type":"response_item"' not in line and '"type": "response_item"' not in line:continue
                row=json.loads(line);payload=row.get('payload',{})
                if payload.get('type')!='message' or payload.get('role')!='assistant':continue
                for c in payload.get('content',[]):
                    if c.get('type') not in ('output_text','text'):continue
                    s=c.get('text','');matches=list(pattern.finditer(s))
                    if matches:item['assistant_version51_mentions'].append({'timestamp':row.get('timestamp'),
                        'matches':[m.group(0) for m in matches],
                        'artifact_paths':re.findall(r'[A-Za-z]:[^\n`"<>]*?(?:\.n6fw|build\.json)',s)[:10]})
            report['session_summaries'].append(item)
report['counts']=counts
repo=BASE/'N6/n6-xip-ota-usb'
report['git_worktrees']=subprocess.check_output(['git','-C',str(repo),'worktree','list','--porcelain'],text=True)
report['git_recent_refs']=subprocess.check_output(['git','-C',str(repo),'log','--all','--since=2026-10-26','--format=%H %aI %s'],text=True)
report['finished_utc']=datetime.now(timezone.utc).isoformat()
(OUT/'artifact-search.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'result_path':str(OUT/'artifact-search.json'),'counts':counts,
    'v51_packages':[p for p in report['packages'] if p['version']==51],
    'text_hits':report['text_hits'],'sessions':report['session_summaries'],'errors':report['errors']},ensure_ascii=False),flush=True)
