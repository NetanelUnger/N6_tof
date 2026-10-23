// Existing SignalR/CLI/XMODEM path, using the user's existing workspace only.
// No pairing, allowlist expansion, sensor stream, server edits or deployment.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';

const root=path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const website=path.join(path.dirname(path.dirname(root)),'Web_N6_ST67W611M1_VL53L9CX');
const workspacePath=path.join(path.dirname(root),'project/.local-dependencies/workspaces/n6-ws-13e32f198c2e42938860512d2f0ce47d-restored.n6workspace.json');
const endpoint='https://natilab-n6-h6bjh2ffbadtfyaw.israelcentral-01.azurewebsites.net';
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
function assert(condition,message){if(!condition)throw new Error(message);}

export async function main(args=process.argv.slice(2)){
  const arg=name=>{const i=args.indexOf(name);return i<0?null:args[i+1];};
  const source=Number(arg('--from')??13),target=Number(arg('--to')??14);
  const workspace=JSON.parse(fs.readFileSync(workspacePath,'utf8').replace(/^\uFEFF/,''));
  const ids=workspace.devices.map(device=>device.id);
  assert(ids.length===1&&ids[0]==='N6-MAINT-B8FB','Only the existing single paired device is authorized');
  assert(typeof workspace.workspaceToken==='string'&&workspace.workspaceToken.length>10,'Existing workspace token unavailable');
  const file=arg('--package');let firmware=null,build=null;
  if(file){
    const filename=path.resolve(root,file);
    assert(!path.relative(root,filename).startsWith('..'),'Package must be inside feature worktree');
    firmware=fs.readFileSync(filename);build=JSON.parse(fs.readFileSync(path.join(path.dirname(filename),'build.json'),'utf8'));
    assert(hash(firmware)===build.hashes[path.basename(filename)].sha256.toLowerCase(),'Package differs from immutable signed build');
    assert(firmware.toString('ascii',0,4)==='N6UP'&&firmware.readUInt32LE(16)+256===firmware.length,'Invalid package framing');
    assert(firmware.readUInt32LE(20)===target&&target>source,'Version order rejected');
    assert(firmware.readUInt32LE(24)===(build.slot==='A'?1:2),'Physical slot flag mismatch');
    assert(hash(firmware.subarray(256))===firmware.subarray(28,60).toString('hex'),'Image digest mismatch');
  }
  if(args.includes('--preflight-only')||!args.includes('--execute')){
    console.log('HOST PREFLIGHT PASS existing workspace/device only; no network, no commands, no credentials printed');
    return {deviceId:ids[0],allowedDeviceCount:ids.length,packageBytes:firmware?.length??0};
  }
  const git=['-c',`safe.directory=${root}`,'-C',root];
  assert(execFileSync('git',[...git,'branch','--show-current'],{encoding:'utf8'}).trim()==='feature/n6-xip-ota-usb','Wrong branch');
  const owner=JSON.parse(fs.readFileSync(path.join(path.dirname(root),'project/.local-dependencies/diagnostics/n6-hardware-owner.json'),'utf8'));
  assert(arg('--owner-thread')&&owner.thread===arg('--owner-thread'),'Shared device ownership missing');
  const python=path.join(path.dirname(root),'project/hil_tests/.venv/Scripts/python.exe');
  const py='import importlib.util,json,sys;s=importlib.util.spec_from_file_location("lease",sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);print(json.dumps(m.windows_process_identity(int(sys.argv[2]))))';
  const identity=JSON.parse(execFileSync(python,['-I','-B','-c',py,path.join(root,'hil_tests/n6_hardware_lease.py'),String(owner.pid)],{encoding:'utf8'}));
  assert(identity.state==='alive'&&identity.created_utc===owner.process_created_utc,'Live owner creation identity mismatch');
  const usbProofPath=path.resolve(root,arg('--usb-proof')??'.local-dependencies/xip/resume-20261022/before-cloud-b13-status.json');
  assert(!path.relative(root,usbProofPath).startsWith('..'),'USB proof must stay inside feature worktree');
  const usbProof=JSON.parse(fs.readFileSync(usbProofPath,'utf8'));
  assert(Date.now()-fs.statSync(usbProofPath).mtimeMs<300000,'Fresh inactive-workspace USB proof required');
  assert(usbProof.version.includes(`Firmware version: ${source}\r\n`),'USB source version differs');
  assert(usbProof['cloud status'].includes('last 409')&&usbProof['cloud status'].includes('ToF: sent 0'),
    'Do not replace an active browser owner or active sensor stream');
  const label=arg('--label');assert(label&&/^[a-z0-9-]+$/.test(label),'Fresh output label required');
  const output=path.join(root,`.local-dependencies/xip/cloud-${label}`);fs.mkdirSync(output);
  const redact=value=>String(value).replaceAll(workspace.workspaceToken,'[redacted]').replaceAll(encodeURIComponent(workspace.workspaceToken),'[redacted]');
  const require=createRequire(path.join(website,'package.json'));
  const signalR=require('@microsoft/signalr');
  const {XmodemControls,OutputSequences,sendXmodem}=await import(pathToFileURL(path.join(website,'src/cloud/xmodemSender.ts')).href);
  const result={mode:firmware?'OTA_UPDATE':'CLOUD_CLI_PROBE',deviceId:ids[0],sourceVersion:source,targetVersion:target,
    packageBytes:firmware?.length??0,packageSha256:firmware?hash(firmware):null,sensorStreamRequested:false,newCredentials:false,
    allowedDeviceIdsUnchanged:ids,passed:false,events:[],commands:[]};
  const persist=()=>fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(result,null,2)+'\n');
  const trace=(message,details={})=>fs.appendFileSync(path.join(output,'xmodem-trace.jsonl'),JSON.stringify({
    atUtc:new Date().toISOString(),monotonicMs:performance.now(),message:redact(message),...details})+'\n');
  const connection=new signalR.HubConnectionBuilder().withUrl(endpoint+'/hubs/relay').configureLogging(signalR.LogLevel.None).build();
  connection.serverTimeoutInMilliseconds=90000;
  const controls=new XmodemControls(),sequences=new OutputSequences(),messages=new Map();let route=null;
  connection.on('TerminalOutput',message=>{
    if(message.deviceId!==ids[0]||!sequences.accept(message.deviceId,message.commandId,message.sequence))return;
    const entry=messages.get(message.commandId)??{text:'',completed:false};
    if(message.kind==='binary'&&message.dataBase64){
      const bytes=Buffer.from(message.dataBase64,'base64');
      if(route&&(route.commandId===null||route.commandId===message.commandId)){
        route.commandId??=message.commandId;
        // Queue only protocol controls; human terminal strings must not fill
        // the bounded control FIFO after the final ACK.
        for(const byte of bytes)if([0x43,0x06,0x15,0x18].includes(byte))controls.push({byte,inputSequence:message.inputSequence});
        result.events.push({kind:'binary-control',sequence:message.sequence,inputSequence:message.inputSequence,length:bytes.length,
          atUtc:new Date().toISOString(),monotonicMs:performance.now()});
        trace('CONTROL_ARRIVAL',{sequence:message.sequence,inputSequence:message.inputSequence,bytes:[...bytes]});
      }
    }else entry.text+=redact(message.text??'');
    entry.completed||=Boolean(message.completed);messages.set(message.commandId,entry);
  });
  connection.onclose(error=>controls.close(new Error(redact(error?.message??'Connection closed'))));
  async function command(line){
    const request=await connection.invoke('SendCommand',ids[0],line);
    const record={line,id:request.id};result.commands.push(record);
    const deadline=Date.now()+45000;
    while(Date.now()<deadline){
      const message=messages.get(request.id);
      if(message?.completed){record.text=message.text;record.completed=true;persist();return message.text;}
      await delay(50);
    }
    record.completed=false;persist();throw new Error('CLI response timeout: '+line);
  }
  const hardStop=setTimeout(()=>{result.deadlineExpired=true;controls.close(new Error('Bounded20minute deadline'));connection.stop().catch(()=>{});},1200000);
  let lastLoop=performance.now();result.maxHostLoopLagMs=0;
  const loopMonitor=setInterval(()=>{const now=performance.now(),lag=now-lastLoop-100;lastLoop=now;
    result.maxHostLoopLagMs=Math.max(result.maxHostLoopLagMs,lag);
    if(lag>250)trace('HOST_LOOP_LAG',{lagMs:lag});},100);
  try{
    persist();await connection.start();
    const opened=await connection.invoke('OpenWorkspace',workspace.workspaceToken,ids);
    result.workspaceId=opened.workspaceId;result.workspaceOpened=true;
    console.log('EXISTING WORKSPACE CONNECTED; allowed devices retained:',ids.length);
    const version=await command('version');
    assert(new RegExp(`Firmware version: ${source}(?:\\r?\\n|$)`).test(version),'Unexpected source version; no update sent');
    assert((await command('debug ping 1414')).includes('PONG 1414 '),'Cloud PONG missing');
    assert((await command('tof status')).includes('requested NONE, active NONE'),'Sensor route is active; no update sent');
    assert((await command('cloud status')).includes('ToF: sent 0'),'Unexpected Cloud sensor exports; stop');
    assert((await command('dataset stream status')).includes('Dataset stream: off'),'Dataset must be off');
    result.probePassed=true;console.log('PASS real Cloud CLI version/ping/status, imageNONE/ToFsent0/datasetOFF');persist();
    if(!firmware){result.passed=true;return result;}
    route={commandId:null};controls.reset();
    const request=await connection.invoke('SendCommand',ids[0],'update');
    route.commandId??=request.id;assert(route.commandId===request.id,'Unexpected binary route; no package sent');
    result.updateCommandId=request.id;let previous=-1;
    await sendXmodem({firmware:new Uint8Array(firmware),controls,
      send:async(packet,sequence,offset,completed,crc)=>{
        result.lastSubmitted={sequence,offset,completed};persist();
        const started=performance.now();trace('SEND_RPC_START',{sequence,offset,completed});
        await connection.invoke('SendCliBinary',ids[0],request.id,sequence,offset,Buffer.from(packet).toString('base64'),crc,completed);
        trace('SEND_RPC_DONE',{sequence,offset,durationMs:performance.now()-started});
      },
      progress:percent=>{result.percent=percent;if(percent!==previous){console.log('OTA',percent+'%');previous=percent;}persist();},
      trace});
    result.eotAcknowledged=true;persist();console.log('PASS actual OTA EOT acknowledged',firmware.length,'bytes');
    await delay(15000);
    try{
      result.versionAfter=await command('version');
      result.targetRunning=new RegExp(`Firmware version: ${target}(?:\\r?\\n|$)`).test(result.versionAfter);
      result.cloudAfter=await command('cloud status');
      assert(result.cloudAfter.includes('ToF: sent 0'),'Cloud sensor count changed');
    }catch(error){result.postUpdateError=redact(error.message);}
    result.passed=Boolean(result.eotAcknowledged&&result.targetRunning);
    if(!result.passed)result.blocker='Candidate EOT acknowledged; target boot not established. Inspect USB/UART before retry/reset.';
    return result;
  }catch(error){result.error=redact(error?.message??error);throw new Error(result.error);}
  finally{
    clearTimeout(hardStop);clearInterval(loopMonitor);await connection.stop();result.connectionClosed=true;persist();
    console.log('CLOUD RESULT',JSON.stringify({mode:result.mode,probePassed:result.probePassed,eotAcknowledged:result.eotAcknowledged,
      targetRunning:result.targetRunning,passed:result.passed,error:result.error??null,connectionClosed:true}));
  }
}

if(process.argv[1]&&pathToFileURL(path.resolve(process.argv[1])).href===import.meta.url){
  main().catch(error=>{console.error('Stopped:',error.message);process.exitCode=1;});
}
