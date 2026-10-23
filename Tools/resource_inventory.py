"""Lexical resource inventory; declarations are not evaluated peak measurements."""
def main():
    import argparse,json,re,subprocess
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    scopes=['AppliNonSecure/Core','AppliNonSecure/AZURE_RTOS/App','AppliNonSecure/USBX/App','AppliNonSecure/Middlewares/ST/vl53l9-transform-c','ThirdParty/ST67W6X_Network_Driver','Common','FSBL/Core','AppliSecure/Core']
    macros=[];arrays=[];calls=[];sources=[]
    api=re.compile(r'\b(tx_(?:queue_\w+|byte_\w+|block_\w+|thread_create|mutex_create|semaphore_create|event_flags_\w+)|(?:N6R_)?[Mm]alloc|(?:N6R_)?[Cc]alloc|(?:N6R_)?[Rr]ealloc|pvPortMalloc|xQueueCreate|xTaskCreate|ux_utility_memory_allocate)\s*\(')
    for scope in scopes:
      for p in sorted((root/scope).rglob('*')):
        if p.suffix not in ['.c','.h','.inc']:continue
        path=p.relative_to(root).as_posix();s=p.read_text(encoding='utf8',errors='replace')
        for number,line in enumerate(s.splitlines(),1):
          match=re.match(r'\s*#define\s+(\w*(?:STACK|POOL|QUEUE|BUFFER|RING)\w*)\s+(.+)',line)
          if match:macros.append({'file':path,'line':number,'name':match[1],'expression':match[2].split('/*')[0].strip()[:150]})
          match=re.match(r'\s*(?:static\s+)?(?:volatile\s+)?(?:UCHAR|ULONG|uint\d+_t|int\d+_t|char|float|double)\s+(\w+)\s*\[([^\]]+)\]',line)
          if match:arrays.append({'file':path,'line':number,'name':match[1],'dimension':match[2]})
          for call in api.finditer(line):calls.append({'file':path,'line':number,'API':call[1]})
        source=re.search(r'#define N6_RESOURCE_SOURCE (\w+)',s)
        if source:sources.append({'file':path,'module':source[1]})
    result={'kind':'LEXICAL_DECLARATIONS_AND_CALLS_NOT_RUNTIME_HIGHWATER','scopes':scopes,'macros':macros,'arrays':arrays,'call_sites':calls,'instrumented_scopes':sources,
      'limits':['Conditional definitions and prototypes included; expressions not evaluated; manually review active build.',
      'Opaque precompiled NPU/USBPD/newlib internal allocators and arbitrary C overwrites are not fully observed.',
      'Shared pool observers see wrapped successful operations; fragmentation and largest future request still need HIL.',
      'Stack telemetry is an instantaneous PSP sample maximum, not full watermark or verified worst-case.',
      'Secure/FSBL resource sites inventoried only, no permission/ABI or fault-path changes.']}
    text=json.dumps(result,indent=2)+'\n'
    if args.output:
      assert subprocess.check_output(['git','branch','--show-current'],cwd=root,text=True).strip()=='feature/n6-xip-ota-usb'
      out=(root/args.output).resolve();assert out.is_relative_to(root);out.write_text(text,encoding='utf8')
    print(json.dumps({'macros':len(macros),'arrays':len(arrays),'call_sites':len(calls),'instrumented_scopes':len(sources)}))
if __name__=='__main__':main()
