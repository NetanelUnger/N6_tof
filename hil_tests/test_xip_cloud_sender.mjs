import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import path from 'node:path';
const [senderFile, packageFile] = process.argv.slice(2);
if (!senderFile || !packageFile) throw new Error('Provide existing xmodemSender.ts and real .n6fw paths');
const {validateN6Package, sendXmodem, XmodemControls} = await import(pathToFileURL(path.resolve(senderFile)));
const firmware=new Uint8Array(readFileSync(packageFile));
validateN6Package(firmware);
assert.ok(new DataView(firmware.buffer).getUint32(24,true)>0,'Requires actual signed XIP package');
const controls=new XmodemControls();controls.push({byte:0x43,inputSequence:0});
const chunks=[];let rejected=false, retry=null, expectedBlock=1, ended=false;
const progress=[];
await sendXmodem({firmware,controls,trace:()=>{},progress:x=>progress.push(x),
  send:async(packet,sequence,offset,completed)=>{
    if(completed){assert.equal(packet[0],4);assert.equal(offset,firmware.length);ended=true;controls.push({byte:6,inputSequence:sequence});return;}
    assert.equal(packet.length,1029);assert.equal(packet[0],2);
    assert.equal(packet[1],expectedBlock&255);assert.equal(packet[2],255-packet[1]);
    let crc=0;for(const b of packet.subarray(3,1027)){crc^=b<<8;for(let i=0;i<8;i++)crc=((crc<<1)^((crc&0x8000)?0x1021:0))&65535;}
    assert.equal((packet[1027]<<8)|packet[1028],crc);
    if(!rejected){rejected=true;retry=packet.slice();controls.push({byte:0x15,inputSequence:sequence});return;}
    if(retry){assert.deepEqual(packet,retry);retry=null;}
    assert.equal(offset,chunks.length*1024);chunks.push(packet.slice(3,1027));expectedBlock++;
    controls.push({byte:6,inputSequence:sequence});
  }});
assert.ok(ended);assert.equal(progress.at(-1),100);assert.ok(chunks.length>256);
const received=new Uint8Array(chunks.length*1024);chunks.forEach((p,i)=>received.set(p,i*1024));
assert.deepEqual(received.slice(0,firmware.length),firmware);
assert.ok(received.slice(firmware.length).every(b=>b===0x1a));
console.log(`PASS existing Cloud sender: actual signed XIP package ${firmware.length} bytes, ${chunks.length} CRC blocks, sequence wrap, NAK retry, padding and EOT; transport simulated, no server/device/network traffic`);
