

def cli_main():
    global FrameReader, Interpreter, Path, contract, delta, digest, error, expected, expected_owner, f, hashlib, i, inp, inspect, json, label, model, np, oracle, os, out, owner, p, preprocess_depth, re, reader, result, root, s, scores, serial, start, sys, sysconfig, time, zlib
    from pathlib import Path
    import os,sys,time,json,hashlib,re,zlib
    os.environ['TF_CPP_MIN_LOG_LEVEL']='2'
    root=Path.cwd();sys.path=[entry for entry in sys.path if Path(entry or '.').resolve()!=Path(__file__).resolve().parent];sys.path.insert(0,str(root/'training/scripts'))
    import inspect,sysconfig
    assert Path(inspect.__file__).resolve()==(Path(sysconfig.get_path('stdlib'))/'inspect.py').resolve()
    import numpy as np
    import serial
    from protocol import FrameReader, build_test_record
    import io
    from dataset import preprocess_depth
    from tensorflow.lite.python.interpreter import Interpreter
    model=root.parent/'project/training/models/rps_int8.tflite'
    digest=hashlib.sha256(model.read_bytes()).hexdigest();assert digest=='59f723828dffae236dd9fa37e2d0de9d7d1a3a31bc07fb4847b6a27dc6637d39'
    contract=re.search(r'N6_MODEL_CONTRACT_SHA256 "([0-9a-f]+)"',(root/'AppliNonSecure/Core/Inc/n6_model_contract.h').read_text())[1]
    oracle=Interpreter(model_path=str(model));oracle.allocate_tensors();inp=oracle.get_input_details()[0];out=oracle.get_output_details()[0]
    ack=b'Dataset stream enabled: N6DF v4, depth + exact tensor + model contract; CRC32 protected.\r\nn6> '
    fixture=FrameReader(io.BytesIO(ack+build_test_record(np.full((42,54),350,dtype=np.uint16),protocol_version=4)))
    fixture.read_frame();assert fixture.crc_errors==0 and fixture.framing_errors==1
    if '--preflight-only' in sys.argv:
     print('HOST PREFLIGHT PASS standard-library inspect, TensorFlow oracle, exact demo model hash and contract; no hardware opened',flush=True)
     sys.exit(0)
    assert '--owner-thread' in sys.argv and '--label' in sys.argv
    expected_owner=sys.argv[sys.argv.index('--owner-thread')+1];label=sys.argv[sys.argv.index('--label')+1];assert re.fullmatch('[a-z0-9-]+',label)
    owner=json.loads((root.parent/'project/.local-dependencies/diagnostics/n6-hardware-owner.json').read_text());assert owner['thread']==expected_owner
    import importlib.util
    spec=importlib.util.spec_from_file_location('hil_lease',root/'hil_tests/n6_hardware_lease.py');lease=importlib.util.module_from_spec(spec);spec.loader.exec_module(lease)
    identity=lease.windows_process_identity(owner['pid']);assert identity['state']=='alive' and identity['created_utc']==owner['process_created_utc']
    result={'scope':'XIP signed resource-profile same-frame USB computation regression, not all-class field accuracy or training-stage acceptance','model_sha256':digest,'contract_sha256':contract,'timestamps':[],'decision_consistent':0,'frames':0,'exact_tensors':0,'npu_frames':0,'max_score_delta':0,'class_matches':0,'tensor_crcs':[],'runs':[],'frame_ids':[],'cloud_sensor_exports':'No Cloud stream requested; verify postflight sent0','passed':False}
    expected_version=int(sys.argv[sys.argv.index('--version')+1]);result['firmware_version']=expected_version
    p=root/f'.local-dependencies/xip/hil-XIP-v{expected_version}-{label}.json';assert not p.exists()
    start=time.monotonic();s=serial.Serial('COM8',115200,timeout=.1,write_timeout=2);s.dtr=True
    try:
     s.reset_input_buffer();s.write(b'version\r');s.flush();reply=bytearray();deadline=time.monotonic()+5
     while time.monotonic()<deadline:
      reply.extend(s.read(8192))
      if reply.endswith(b'n6> '):break
     assert f'Firmware version: {expected_version}\r\n'.encode() in reply,'Unexpected live firmware'
     s.reset_input_buffer();s.write(b'DATASET STREAM ON\r');s.flush();reader=FrameReader(s)
     for i in range(100):
      assert time.monotonic()-start<180
      f=reader.read_frame(timeout=3)
      assert f.contract_sha256==contract and f.class_count==4
      assert f.model_frame_id==f.frame_id and f.model_input is not None
      expected=preprocess_depth(f.depth_mm)[...,0]
      assert np.array_equal(expected,f.model_input),'CPU preprocessing mismatch'
      result['exact_tensors']+=1;result['frames']+=1;result['frame_ids'].append(f.frame_id);result['timestamps'].append(f.timestamp_ms)
      result['tensor_crcs'].append(zlib.crc32(f.model_input.tobytes()))
      oracle.set_tensor(inp['index'],f.model_input[np.newaxis,...,np.newaxis]);oracle.invoke();scores=oracle.get_tensor(out['index'])[0]
      if f.npu_valid and f.npu_scores is not None:
       delta=int(np.max(np.abs(np.asarray(scores,dtype=np.int16)-np.asarray(f.npu_scores,dtype=np.int16))))
       result['npu_frames']+=1;result['max_score_delta']=max(result['max_score_delta'],delta)
       host_class=int(np.argmax(scores));result['class_matches']+=int(host_class==f.npu_class_id);result['runs'].append(f.npu_runs)
       result['decision_consistent']+=int(host_class==f.npu_class_id or int(scores[host_class])-int(scores[f.npu_class_id])<=2*delta)
      if (i+1)%10==0:print('XIP HIL',i+1,'NPU',result['npu_frames'],'maxdelta',result['max_score_delta'],flush=True)
     result['crc_errors']=reader.crc_errors;result['framing_errors']=reader.framing_errors
     assert result['exact_tensors']==100 and result['npu_frames']>=80 and result['max_score_delta']<=16
     assert result['crc_errors']==0
     result['last_parser_diagnostic']=reader.last_error
     config=json.loads((root/'training/config/training.json').read_text(encoding='utf-8'));gates=config['hil']
     result['sensor_fps']=99*1000/((result['timestamps'][-1]-result['timestamps'][0])&0xffffffff)
     assert result['sensor_fps']>=float(config['capture']['save_fps'])
     assert result['decision_consistent']/result['npu_frames']>=float(gates['minimum_decision_consistency'])
     assert result['npu_frames']/100>=float(gates['minimum_npu_coverage']) and result['max_score_delta']<=int(gates['maximum_raw_score_delta'])
     assert all(right>left for left,right in zip(result['runs'],result['runs'][1:]))
     assert len(set(result['runs']))>=80
     result['passed']=True
    except Exception as error:
     result['error']=repr(error);raise
    finally:
     try:s.write(b'DATASET STREAM OFF\r');s.flush();time.sleep(.3)
     finally:s.close()
     result['elapsed_s']=time.monotonic()-start;result['unique_tensors']=len(set(result['tensor_crcs']))
     p.write_text(json.dumps(result,indent=2)+'\n')
    print('PASS XIP same-frame regression',result['frames'],result['exact_tensors'],result['npu_frames'],result['max_score_delta'],result['elapsed_s'],flush=True)


if __name__ == "__main__":
    cli_main()
