"""Host-only reproduction of current server lease behavior; never contacts server."""

def main():
    import argparse,hashlib,json,os,subprocess
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    if not args.execute:print('PASS host preflight; no files, subprocess or network');return
    root=Path(__file__).resolve().parents[1]
    assert subprocess.check_output(['git','branch','--show-current'],cwd=root,text=True).strip() in ('main', 'feature/n6-xip-ota-usb')
    server=root.parent.parent/'Web_N6_ST67W611M1_VL53L9CX/server/N6.CloudRelay'
    source=(server/'RelayRegistry.cs').read_text(encoding='utf8')
    actual='using System.Threading.Channels;\nnamespace N6.CloudRelay;\n'+source[source.index('public enum OutputAcceptance'):]
    folder=root/'.local-dependencies/xip/server-lease-current-20261023';folder.mkdir(exist_ok=False)
    (folder/'Session.cs').write_text(actual,encoding='utf8')
    (folder/'Contracts.cs').write_bytes((server/'RelayContracts.cs').read_bytes())
    (folder/'Probe.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup></Project>')
    (folder/'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
    (folder/'Program.cs').write_text(PROGRAM,encoding='utf8')
    environment=os.environ.copy();environment.update(DOTNET_CLI_HOME=str(folder/'.dotnet-home'),DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1',DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE='1',DOTNET_GENERATE_ASPNET_CERTIFICATE='false',DOTNET_ADD_GLOBAL_TOOLS_TO_PATH='false')
    for command in [['dotnet','restore','Probe.csproj','--configfile','NuGet.Config'],['dotnet','run','--no-restore','--project','Probe.csproj']]:
        subprocess.run(command,cwd=folder,env=environment,check=True,timeout=60)
    result=json.loads((folder/'result.json').read_text(encoding='utf8'))
    result['actual_registry_sha256']=hashlib.sha256((server/'RelayRegistry.cs').read_bytes()).hexdigest()
    result['actual_contracts_sha256']=hashlib.sha256((server/'RelayContracts.cs').read_bytes()).hexdigest()
    result['server_modified']=False;result['network_access']=False
    (folder/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS actual server class lease probe',json.dumps(result))

PROGRAM=r'''
using N6.CloudRelay;
using System.Diagnostics;
using System.Reflection;
using System.Text.Json;
static void Check(bool value,string message){if(!value)throw new Exception(message);}
var session=new DeviceSession("host-only-probe");
DeviceCommand Command(int sequence)=>new("same-command","binary",sequence,null,"AA==",483328,"00000000",false,DateTimeOffset.UtcNow);
Check(session.TryQueue(Command(473)),"queue original");
var first=await session.ReadCommandAsync(CancellationToken.None);
Check(first.Sequence==473,"original delivered");
var field=typeof(DeviceSession).GetField("_leaseExpiresAt",BindingFlags.Instance|BindingFlags.NonPublic)!;
var seconds=((DateTimeOffset)field.GetValue(session)!-DateTimeOffset.UtcNow).TotalSeconds;
Check(seconds>28.5&&seconds<=30,"actual source sets30second lease");
Check(session.TryQueue(Command(474)),"queue retry");
bool blocked=false;var watch=Stopwatch.StartNew();
using(var cancel=new CancellationTokenSource(1000)){
    try{await session.ReadCommandAsync(cancel.Token);}
    catch(OperationCanceledException){blocked=true;}
}
watch.Stop();Check(blocked,"queued retry cannot bypass in-flight lease");
// Expire only the isolated test object's clock field; do not wait or claim a real30s run.
field.SetValue(session,DateTimeOffset.UtcNow.AddSeconds(-1));
var replay=await session.ReadCommandAsync(CancellationToken.None);
Check(replay.Sequence==473,"lease expiry replays original, not queued retry");
Check(session.Acknowledge("same-command",473),"exact original acknowledged");
var retry=await session.ReadCommandAsync(CancellationToken.None);
Check(retry.Sequence==474,"queued retry then delivered");
Check(!session.Acknowledge("same-command",473),"stale ACK cannot retire retry");
var result=new{passed=true,configured_lease_seconds=Math.Round(seconds,3),blocked_probe_ms=watch.Elapsed.TotalMilliseconds,
    expiry_forced_only_in_test_object=true,replayed_original_sequence=replay.Sequence,retry_sequence_after_ACK=retry.Sequence,
    stale_ACK_rejected=true,live_server_requests=0};
File.WriteAllText("result.json",JsonSerializer.Serialize(result,new JsonSerializerOptions{WriteIndented=true}));
Console.WriteLine("PASS30s lease, queued-retry head blocking, original replay, exact ACK correlation");
'''

if __name__=='__main__':main()
