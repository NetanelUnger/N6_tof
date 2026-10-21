"""Package only the unchanged binary explicitly accepted by Stage11 HIL."""
from pathlib import Path
import uuid
from common import (PROJECT_ROOT,GENERATED_ROOT,MODELS_ROOT,REPORTS_ROOT,PROJECT_ID,
                    npu_deployment_fingerprint,stage_state,sha256_file,load_json,atomic_json,run,mark_stage)

def package_verified(version):
    current=npu_deployment_fingerprint();hil=stage_state('11_hil');ram=stage_state('10_ram')
    if (hil.get('status')!='complete' or hil.get('input_fingerprint')!=current or
        ram.get('status')!='complete' or ram.get('input_fingerprint')!=current):
        raise RuntimeError('BLOCKED: Stage10 and Stage11 must pass for the exact current model/project.')
    report_path=REPORTS_ROOT/'hil_validation.json';report=load_json(report_path)
    candidate=ram.get('details',{}).get('candidate')
    if (not candidate or report.get('result')!='pass' or report.get('frames')!=100 or
        report.get('elapsed_seconds',181)>180 or report.get('ram_candidate')!=candidate or
        report.get('model_sha256')!=sha256_file(MODELS_ROOT/'rps_int8.tflite')):
        raise RuntimeError('BLOCKED: exact100-frame HIL candidate/model binding is missing.')
    for item in candidate['artifacts'].values():
        if sha256_file(Path(item['path']))!=item['sha256']:
            raise RuntimeError('BLOCKED: a HIL-tested RAM artifact changed; no package created.')
    if version!=candidate['firmware_version']:
        raise RuntimeError('BLOCKED: package version differs from the exact HIL-tested RAM firmware.')
    folder=GENERATED_ROOT/'release'/('v'+str(version)+'-'+uuid.uuid4().hex)
    binary=candidate['artifacts']['candidate.bin']
    run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(PROJECT_ROOT/'Tools/Package-VerifiedRamCandidate.ps1'),
         '-Binary',binary['path'],'-OutputDirectory',str(folder),'-FirmwareVersion',str(version),'-ExpectedSha256',binary['sha256']],cwd=PROJECT_ROOT)
    package=folder/f'N6-Firmware-v{version}.n6fw'
    manifest={'schema':1,'project_id':PROJECT_ID,'firmware_version':version,'model_sha256':report['model_sha256'],
              'contract_sha256':sha256_file(MODELS_ROOT/'model_contract.json'),
              'hil_report_sha256':sha256_file(report_path),'candidate':candidate,
              'package':str(package),'package_sha256':sha256_file(package),'persistent_installation':False}
    atomic_json(folder/'release_manifest.json',manifest)
    mark_stage('12_package',status='complete',inputs=current,outputs=[str(package),str(folder/'release_manifest.json')],details=manifest)
    return manifest
