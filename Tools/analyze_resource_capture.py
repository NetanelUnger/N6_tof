"""Decode bounded resource UART records and ELF object names; host-only.

Observed pool/queue peaks and instantaneous PSP sample maxima are lower bounds,
not proven worst-case, fragmentation or all-stack high-water measurements.
"""

def main():
    import argparse,json,re,subprocess
    from pathlib import Path
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--log',type=Path,required=True)
    p.add_argument('--elf',type=Path,required=True);p.add_argument('--output',type=Path);a=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    plugins=Path('C:/ST/STM32CubeIDE_2.2.0/STM32CubeIDE/plugins')
    nm=next(plugins.glob('com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.*/tools/bin/arm-none-eabi-nm.exe'))
    symbols={}
    for line in subprocess.check_output([str(nm),'--defined-only',str(a.elf.resolve())],text=True).splitlines():
        m=re.match(r'^([0-9a-fA-F]+)\s+[bBdD]\s+(\S+)$',line)
        if m:symbols.setdefault(int(m[1],16),[]).append(m[2])
    usage={};failures={};invalid=[]
    for line in a.log.read_text(errors='replace').splitlines():
        m=re.fullmatch(r'\[RESOURCE\] ((?:[0-9A-F]{8} ?)+)\s*',line)
        if not m:continue
        fields=[int(x,16) for x in m[1].split()]
        if len(fields)==8 and fields[0]==255 and 256<=fields[1]<=258:
            _,kind,n,capacity,peak,minimum,address,flags=fields
            record=dict(kind=['queue','pool','stack'][kind-256],object=hex(address),symbols=symbols.get(address,[]),observations=n,capacity=capacity,observed_peak=peak,observed_minimum_free=minimum,flags=flags)
            record['observed_free_over_used_percent']=100*minimum/peak if peak else None
            if kind==258:
                required=((((peak+336)*110+99)//100)+63)&~63
                record.update(sample_plus_provisional_context_margin_required=required,sampled_margin_target_met=capacity>=required,warning='PSP sample maximum only, not full watermark/WC')
            elif kind==257:
                record['observed_10percent_capacity_target_met']=minimum*10>=peak
                record['warning']='C heap frontier, not malloc free/largest block' if flags&8 else 'Wrapped observations only; fragmentation/largest request not proven'
            usage[(kind,address)]=record
        elif len(fields)==9 and fields[0]<8 and fields[1]<9 and fields[8]&~3==0:
            module,kind,count,status,site,arg,obj,tick,flags=fields
            failures[(module,kind)]=dict(module=module,kind=kind,count=count,status=hex(status),line=site,argument=arg,object=hex(obj),tick=tick,flags=flags)
        else:invalid.append(line)
    result=dict(kind='OBSERVED_ONLY_NOT_VERIFIED_WORST_CASE',log=str(a.log),elf=str(a.elf),usage=list(usage.values()),failure_rows=list(failures.values()),invalid_resource_lines=invalid,
                limits=['Finite expected receive timeouts retained silently as POLL','Queue free-lists may validly be full; no generic10percent queue-admission claim','Addresses reused across instances may retain conservative historical peaks','Pool free percentage is not proof of largest allocatable block','No proof that every thread or interrupt nesting peak was sampled'])
    if a.output:
        if subprocess.check_output(['git','branch','--show-current'],cwd=root,text=True).strip()!='feature/n6-xip-ota-usb':raise RuntimeError('Wrong branch')
        target=a.output.resolve()
        if not target.is_relative_to(root):raise RuntimeError('Output outside feature')
        target.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(usage_rows=len(usage),pools=[r for r in usage.values() if r['kind']=='pool'],stack_samples=len([r for r in usage.values() if r['kind']=='stack']),failure_rows=result['failure_rows'],invalid_lines=len(invalid)),indent=2))

if __name__=='__main__':main()
