from pathlib import Path
import difflib, hashlib, json
HERE=Path(__file__).parent
ROOT=Path(r'C:\Users\netan\Dropbox\DevelopPersonal\N6\n6-xip-ota-usb')
OUT=HERE/'evidence/st67-cp11-at-timeout-candidate'
OUT.mkdir(exist_ok=False)
p='ThirdParty/ST67W6X_Network_Driver/Driver/W61_at/modem_cmd_handler.c'
before=(ROOT/p).read_text()
old='''    /* A scoped timeout has no terminal boundary; a late OK must not satisfy
     * a new operation. Only module reinitialization clears this real fence. */
    if ((ret == -ETIMEDOUT) && (data->budget_owner == xTaskGetCurrentTaskHandle()))
    {
      if (((flags & MODEM_NO_UNSET_CMDS) == 0U) &&'''
new='''    /* Any written command missing its terminal has an ambiguous boundary,
     * including unscoped query/connect callers. A late OK must not satisfy a
     * new command. Only the existing bounded scoped-DNS drain is an exception. */
    if (ret == -ETIMEDOUT)
    {
      if ((data->budget_owner == xTaskGetCurrentTaskHandle()) &&
          ((flags & MODEM_NO_UNSET_CMDS) == 0U) &&'''
assert before.count(old)==1
after=before.replace(old,new)
dest=OUT/'candidate'/p;dest.parent.mkdir(parents=True);dest.write_text(after,newline='\n')
(OUT/'PROPOSED-NOT-APPLIED-at-timeout-fence.patch').write_text(''.join(difflib.unified_diff(before.splitlines(keepends=True),after.splitlines(keepends=True),fromfile='a/'+p,tofile='b/'+p)),newline='\n')
(OUT/'candidate-manifest.json').write_text(json.dumps({'path':p,'original_sha256':hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),'candidate_sha256':hashlib.sha256(dest.read_bytes()).hexdigest()},indent=2)+'\n')
print('Prepared isolated one-file timeout candidate; production unchanged.')
