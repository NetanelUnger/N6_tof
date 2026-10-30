from pathlib import Path
import json,re,hashlib
out=Path(__file__).resolve().parent/'evidence/st67-cp2-20261028'
search=json.loads((out/'artifact-search.json').read_text())
results=[]
for a in search['candidate_paths']:
    p=Path(a['path'])
    if p.suffix.lower() not in {'.bin','.elf','.n6fw'}:continue
    raw=p.read_bytes()
    versions=sorted({int(v) for v in re.findall(rb'Firmware version:\s*(\d+)',raw)})
    results.append({'path':str(p),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
        'compiled_version_strings':versions})
(out/'binary-version-search.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps({'files':len(results),'v51_strings':[r for r in results if 51 in r['compiled_version_strings']],
    'version_strings_found':sorted({v for r in results for v in r['compiled_version_strings']})}))
