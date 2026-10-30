from pathlib import Path
import hashlib, json, shutil, difflib
ROOT=Path(r'C:\Users\netan\Dropbox\DevelopPersonal\N6\n6-xip-ota-usb')
OUT=Path(__file__).parent/'evidence/st67-cp10-transport-candidate'
old=json.loads((OUT/'candidate-manifest.json').read_text())
assert all(hashlib.sha256((ROOT/x['path']).read_bytes()).hexdigest()==x['original_sha256'] for x in old)
assert all(hashlib.sha256((OUT/'candidate'/x['path']).read_bytes()).hexdigest()==x['candidate_sha256'] for x in old)
shutil.copy2(OUT/'candidate-manifest.json',OUT/'candidate-v1-manifest.json')
shutil.copy2(OUT/'PROPOSED-NOT-APPLIED-spi-fence.patch',OUT/'candidate-v1-NOT-APPLIED.patch')
path=OUT/'candidate/ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/w61_at_common.c'
s=path.read_text();anchor='  available = mdm->spi_rx_pending_len - mdm->spi_rx_pending_offset;'
assert s.count(anchor)==1
s=s.replace(anchor,'''  /* A bus wait may have overlapped the fault. Recheck after packet ownership
   * transfer, before publishing any bytes or releasing the retained packet. */
  if (spi_transaction_faulted() != 0)
  {
    mdm->handler_data.tx_desynchronized = true;
    vTaskDelay(1U);
    return -EIO;
  }
'''+anchor)
path.write_text(s,newline='\n')
patch=''
for x in old:
 a=(ROOT/x['path']).read_text();b=(OUT/'candidate'/x['path']).read_text()
 patch+=''.join(difflib.unified_diff(a.splitlines(keepends=True),b.splitlines(keepends=True),fromfile='a/'+x['path'],tofile='b/'+x['path']))
 x['candidate_sha256']=hashlib.sha256((OUT/'candidate'/x['path']).read_bytes()).hexdigest()
(OUT/'candidate-manifest.json').write_text(json.dumps(old,indent=2)+'\n')
(OUT/'PROPOSED-NOT-APPLIED-spi-fence.patch').write_text(patch,newline='\n')
print('Candidate v2 rechecks fault after queued receive; v1 patch, hashes and failed test retained. Production unchanged.')
