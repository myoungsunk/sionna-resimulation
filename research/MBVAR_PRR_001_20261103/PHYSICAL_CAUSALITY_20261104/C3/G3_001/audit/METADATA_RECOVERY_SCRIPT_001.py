from pathlib import Path
import hashlib,json,datetime,os
phase=Path('D:/codex/MBVAR_PRR_001_20261103/research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/C3/G3_001')
root=phase/'BATCH_001';audit=phase/'audit'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,o):assert not p.exists();p.write_bytes((json.dumps(o,indent=2)+'\n').encode())
assert not (root/'ARTIFACT_HASHES.json').exists()
disposition=audit/'C3_G3_EXECUTION_DEFECT_DISPOSITION_RESULT.json';assert json.loads(disposition.read_bytes())['decision']=='REDIRECT'
originals={p.relative_to(root).as_posix():sha(p) for p in sorted(root.rglob('ARTIFACT_HASHES.json'))}
assert len(originals)==20
index={p.relative_to(root).as_posix():sha(p) for p in sorted(root.rglob('*')) if p.is_file() and p.name!='ARTIFACT_HASHES.json'}
assert len(index)==5383
out=audit/'RECOVERED_ROOT_ARTIFACT_HASHES_001.json';put(out,index)
put(audit/'G3_METADATA_RECOVERY_001.json',dict(schema='C3_G3_ADMINISTRATIVE_METADATA_RECOVERY_V1',status='RECOVERED_INDEX_ONLY_PENDING_INDEPENDENT_RETAINED_DATA_AUDIT',original_execution='FORCED_AFTER_ALL20_DATA_SAVED_NO_NATURAL_EXIT_PASS',disposition_sha256=sha(disposition),recovered_index_path=out.name,recovered_index_sha256=sha(out),indexed_files=len(index),original_condition_indexes=originals,forced_manager_receipt_sha256=sha(phase/'logs/G3_BATCH_001_MANAGED.json'),original_manifest_sha256=sha(root/'MANIFEST.json'),original_index_sha256=sha(root/'INDEX.csv'),incident_sha256=sha(phase/'G3_EXECUTION_INCIDENT_001_KO.md'),original_root_index_absent=True,original_capture_modified=False,rt_calls=0,source_model_initializations=0,fft_calls=0,timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),managed_run=os.environ.get('MANAGED_PROCESS_RUN_ID'),managed_resource=os.environ.get('MANAGED_PROCESS_ID')))
print(json.dumps(dict(status='METADATA_INDEX_RECOVERED_ONLY',files=len(index),original_condition_indexes=len(originals),recovered_index_sha256=sha(out))),flush=True)
