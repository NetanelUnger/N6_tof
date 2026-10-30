"""Read only N6 firmware binaries, including old timestamps, never key/settings files."""
import os,re,json,hashlib,time
from pathlib import Path
root=Path(r'C:\Users\netan\Dropbox\DevelopPersonal\N6')
skip={'.git','keys','.data-protection-keys','node_modules','.venv','venv','__pycache__','.sandbox-secrets'}
out=Path(__file__).parent/'evidence/st67-cp3-20261028/all-binary-versions.json'
report={'root':str(root),'scope':'All timestamps; only .bin/.elf/.n6fw; no key/credential contents','files':0,'bytes':0,'versions':{},'matches51':[],'errors':[]}
pattern=re.compile(rb'Firmware version: ([0-9]{1,5})(?:\x00|\r|\n)')
for folder,dirs,files in os.walk(root):
    dirs[:]=[d for d in dirs if d.lower() not in skip]
    for name in files:
        p=Path(folder)/name
        if p.suffix.lower() not in {'.bin','.elf','.n6fw'} or any(x in name.lower() for x in ('private','credential','secret','token','password')):continue
        try:
            found=set();tail=b''
            with p.open('rb') as f:
                while chunk:=f.read(1024*1024):
                    report['bytes']+=len(chunk);found.update(int(m[1]) for m in pattern.finditer(tail+chunk));tail=chunk[-64:]
            report['files']+=1
            for v in sorted(found):report['versions'][str(v)]=report['versions'].get(str(v),0)+1
            if 51 in found:report['matches51'].append({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
        except OSError as e:report['errors'].append({'path':str(p),'error':type(e).__name__})
out.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report),flush=True)
