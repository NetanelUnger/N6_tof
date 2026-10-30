// Bounded Cloud CLI load using only the already paired workspace and device.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
const root=path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const arg=n=>process.argv[process.argv.indexOf(n)+1];
const folder=path.resolve(arg('--folder'));
if(!folder.startsWith(root+path.sep))throw Error('Report folder outside checkout');
const owner=JSON.parse(fs.readFileSync(path.join(path.dirname(root),'project/.local-dependencies/diagnostics/n6-hardware-owner.json')));
if(owner.thread!==arg('--owner-thread'))throw Error('Hardware ownership mismatch');
const identityCode='import importlib.util,json,sys;s=importlib.util.spec_from_file_location("lease",sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);print(json.dumps(m.windows_process_identity(int(sys.argv[2]))))';
const identity=JSON.parse(execFileSync(path.join(root,'training/.venv/Scripts/python.exe'),['-I','-c',identityCode,path.join(root,'hil_tests/n6_hardware_lease.py'),String(owner.pid)],{encoding:'utf8'}));
if(identity.state!=='alive'||identity.created_utc!==owner.process_created_utc)throw Error('Hardware owner not alive');
const proof=JSON.parse(fs.readFileSync(path.join(folder,'preflight.json')));
if(Date.now()-fs.statSync(path.join(folder,'preflight.json')).mtimeMs>60000||(!proof['cloud status'].includes('last 409')&&!process.argv.includes('--replace-existing-workspace')))throw Error('Fresh inactive workspace proof or explicit replacement authorization required');
const workspace=JSON.parse(fs.readFileSync(path.join(path.dirname(root),'project/.local-dependencies/workspaces/n6-ws-13e32f198c2e42938860512d2f0ce47d-restored.n6workspace.json'),'utf8').replace(/^\uFEFF/,''));
const ids=workspace.devices.map(d=>d.id);
if(ids.length!==1||ids[0]!=='N6-MAINT-B8FB')throw Error('Unexpected paired devices');
const redact=s=>String(s).replaceAll(workspace.workspaceToken,'[redacted]').replaceAll(encodeURIComponent(workspace.workspaceToken),'[redacted]');
const website=path.join(path.dirname(path.dirname(root)),'Web_N6_ST67W611M1_VL53L9CX');
const require=createRequire(path.join(website,'package.json'));const signalR=require('@microsoft/signalr');
const hub=new signalR.HubConnectionBuilder().withUrl('https://natilab-n6-h6bjh2ffbadtfyaw.israelcentral-01.azurewebsites.net/hubs/relay').configureLogging(signalR.LogLevel.None).build();
const delay=ms=>new Promise(r=>setTimeout(r,ms));const pending=new Map();
const report={passed:false,commands:[],startedUtc:new Date().toISOString()};let linkError=null;
const save=()=>fs.writeFileSync(path.join(folder,'cloud-result.json'),JSON.stringify(report,null,2));
hub.onclose(error=>{linkError=redact(error?.message??'Hub closed');});
hub.on('TerminalOutput',m=>{
 if(m.deviceId!==ids[0])return;
 let entry=pending.get(m.commandId)??{text:'',sequence:-1,completed:false};
 if(m.sequence<=entry.sequence)return;
 entry.sequence=m.sequence;entry.text+=redact(m.text??'');entry.completed||=!!m.completed;
 if(entry.text.length>131072){linkError='Cloud reply exceeds128KiB';return;}
 pending.set(m.commandId,entry);
 if(pending.size>64)pending.delete(pending.keys().next().value);
});
async function command(line){
 const start=performance.now();const request=await hub.invoke('SendCommand',ids[0],line);
 const row={line,id:request.id,utc:new Date().toISOString(),completed:false};report.commands.push(row);
 while(performance.now()-start<45000){
  const item=pending.get(request.id);
  if(linkError)throw Error(linkError);
  if(item?.completed){
   row.ms=performance.now()-start;row.text=item.text;row.completed=true;
   // Remote replies end with LF; successful PONG does not carry a prompt.
   if(!item.text.endsWith('\n')||/\[CLI-RESULT\] state=(failed|rejected)/.test(item.text)||/(?:^|\r)FAIL\r?\n$/.test(item.text))throw Error('Missing/suspect CLI terminal: '+line);
   if(line.startsWith('debug ping ')&&!item.text.includes('PONG '+line.slice(11)+' '))throw Error('PONG mismatch');
   fs.appendFileSync(path.join(folder,'cloud-commands.jsonl'),JSON.stringify(row)+'\n');
   console.log('CLOUD',line,Math.round(row.ms)+'ms');return row;
  }
  await delay(25);
 }
 row.ms=performance.now()-start;row.text=pending.get(request.id)?.text??'';throw Error('Cloud command timeout: '+line);
}
const timer=setTimeout(()=>{linkError='Cloud worker reached300s bound';hub.stop().catch(()=>{});},300000);
try{
 await hub.start();await hub.invoke('OpenWorkspace',workspace.workspaceToken,ids);
 const version=await command('version');if(!version.text.includes('Firmware version: 58'))throw Error('Firmware changed');
 await command('debug ping CLOUD-READY');fs.writeFileSync(path.join(folder,'cloud-ready.json'),'{}');
 const readyDeadline=performance.now()+30000;
 while(!fs.existsSync(path.join(folder,'start'))){if(performance.now()>readyDeadline)throw Error('No BLE start');await delay(50);}
 const started=performance.now();let index=0;
 while(performance.now()-started<195000&&!fs.existsSync(path.join(folder,'stop'))){
  const line=index%3===0?'radio status':index%3===1?'help':'debug ping MIX-'+index;
  await command(line);index++;await delay(100);
 }
 report.elapsedMs=performance.now()-started;report.loadCommands=index;
 report.passed=report.elapsedMs>=175000&&index>=3;
}catch(error){report.error=redact(error.message);console.error('CLOUD FAIL',report.error);}
finally{clearTimeout(timer);await hub.stop();report.closed=true;save();}
process.exitCode=report.passed?0:1;
