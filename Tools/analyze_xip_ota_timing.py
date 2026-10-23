"""Host-only OTA trace analysis. Never imports hardware/network clients."""
def main():
    import argparse,bisect,json,re,statistics
    from datetime import datetime
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--label',required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];base=root/'.local-dependencies/xip'
    assert re.fullmatch('[a-z0-9-]+',args.label)
    sender=base/('cloud-'+args.label);capture=base/('ota-uart-'+args.label)
    def rows(path):
        result=[]
        for line in path.read_text(encoding='utf8').splitlines():
            try:result.append(json.loads(line))
            except json.JSONDecodeError:pass # a live writer may have an incomplete final line
        return result
    trace=rows(sender/'xmodem-trace.jsonl');tx={};rpc={};control={};durations=[]
    for row in trace:
        seq=row.get('sequence')
        if row['message']=='TX':tx[seq]=row
        elif row['message']=='SEND_RPC_DONE':rpc[seq]=row['durationMs']
        elif row['message']=='CONTROL_ARRIVAL' and 6 in row['bytes']:control[row['inputSequence']]=row
        elif row['message']=='RX' and row.get('control')==6 and 'monotonicMs' in row:
            durations.append({'sequence':seq,'block':row['block'],'attempt':row['attempt'],
                'ms':row['monotonicMs']-tx[seq]['monotonicMs']})
    def summary(values):
        if not values:return None
        ordered=sorted(values)
        return {'count':len(values),'p50_ms':statistics.median(ordered),'p95_ms':ordered[int((len(ordered)-1)*.95)],
                'max_ms':max(ordered)}
    raw=(capture/'uart.log').read_bytes();lines=[];offset=0
    for line in raw.splitlines(keepends=True):lines.append((offset+len(line)-1,line));offset+=len(line)
    arrivals_path=capture/'uart-arrivals.jsonl';arrivals=rows(arrivals_path) if arrivals_path.exists() else []
    ends=[x['offset']+x['length']-1 for x in arrivals]
    def host_utc(pos):
        i=bisect.bisect_left(ends,pos)
        return arrivals[i]['atUtc'] if i<len(arrivals) else None
    def ms_since(a,b):return (datetime.fromisoformat(b.replace('Z','+00:00'))-datetime.fromisoformat(a.replace('Z','+00:00'))).total_seconds()*1000
    received={};delivered={};faults=[];output_input={}
    for pos,line in lines:
        match=re.search(rb'binary received: seq=(\d+)',line)
        if match:received[int(match[1])]={'hostUtc':host_utc(pos),'line':line.decode('utf8','replace').strip()}
        match=re.search(rb'HTTP complete: kind=4 .*input-seq=(\d+) output-seq=(\d+)',line)
        if match:output_input[int(match[2])]=int(match[1])
        match=re.search(rb'control delivered: output-seq=(\d+) byte=0x06',line)
        if match and int(match[1]) in output_input:delivered[output_input[int(match[1])]]=host_utc(pos)
        if b'SPI-FAULT' in line:faults.append({'hostUtc':host_utc(pos),'line':line.decode('utf8','replace').strip()})
    stages=[]
    for seq,row in tx.items():
        rx=received.get(seq,{}).get('hostUtc');ack=delivered.get(seq);c=control.get(seq,{})
        if rx and ack and 'atUtc' in row and c.get('atUtc'):
            stages.append({'sequence':seq,'block':row['block'],'attempt':row['attempt'],
                'TX_to_device_RX_observed_ms':ms_since(row['atUtc'],rx),
                'device_RX_to_ACK_observed_ms':ms_since(rx,ack),
                'ACK_observed_to_client_ms':ms_since(ack,c['atUtc'])})
    result={'label':args.label,'completed_ACKs':len(durations),'timeouts':[x for x in trace if x['message'].startswith('TIMEOUT')],
        'TX_ACK':summary([x['ms']for x in durations]),'RPC':summary(list(rpc.values())),
        'slowest_ACKs':sorted(durations,key=lambda x:x['ms'],reverse=True)[:10],
        'SPI_faults':faults,'host_loop_lags':[x for x in trace if x['message']=='HOST_LOOP_LAG'],
        'stage_summary':{key:summary([x[key]for x in stages])for key in ['TX_to_device_RX_observed_ms','device_RX_to_ACK_observed_ms','ACK_observed_to_client_ms']},
        'slow_stages':sorted(stages,key=lambda x:x['TX_to_device_RX_observed_ms'],reverse=True)[:10],
        'limits':'UART timestamps are host read-arrival proxies, include UART queuing/read latency; device TIM6 is not wall time while NS IRQs are masked; negative cross-proxy intervals can occur'}
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
