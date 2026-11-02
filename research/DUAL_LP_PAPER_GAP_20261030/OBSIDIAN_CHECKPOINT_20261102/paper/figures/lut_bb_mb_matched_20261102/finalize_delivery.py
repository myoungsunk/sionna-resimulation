"""Delivery envelope only; audited scientific files remain unchanged."""
from pathlib import Path
import json,hashlib,datetime
OUT=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
    audit_path=OUT/'audit/INDEPENDENT_AUDIT.json'
    audit=json.loads(audit_path.read_text(encoding='utf-8'));assert audit['verdict']=='ACCEPT'
    assert sha(OUT/'OUTPUT_MANIFEST.json')==audit['audited_output_manifest_sha256']
    assert all(sha(OUT/p)==h for p,h in audit['audited_output_files'].items())
    contract=json.loads((OUT/'CONTRACT_BB_MB_DISTANCE_LUT.json').read_text(encoding='utf-8'))
    assert all(sha(p)==h for p,h in contract['input_hashes'].items())
    managed=json.loads((OUT/'MANAGED_FINISH.json').read_text(encoding='utf-8-sig'))['processes'][0]
    assert managed['exit_code']==0 and managed['termination']=='natural' and managed['ref_count']==0
    assert managed['actual_process']['state']=='absent' and managed['actual_supervisor']['state']=='absent' and managed['job']['state']=='absent'
    status=dict(question_id=contract['contract_id'],execution='COMPLETED',primary_distance_replays=24,source_validation_replays=24,technical_self_checks='PASS',independent_audit='ACCEPT',scientific_result='MIXED',model_or_manuscript_adoption=False,contract_sha256=sha(OUT/'CONTRACT_BB_MB_DISTANCE_LUT.json'),audit_sha256=sha(audit_path),audited_files_unchanged=True,input_files_unchanged=True,managed_process_finished=True,run_id=managed['creator'],resource_id=managed['id'],note='FINAL_SELF_QA is the immutable pre-audit self-check snapshot; independent audit completion is recorded here and in audit/INDEPENDENT_AUDIT.json. Post-audit delivery envelope and copied process logs do not modify the audited manifest or scientific tables.',finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (OUT/'FINAL_DELIVERY_STATUS.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(status,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
