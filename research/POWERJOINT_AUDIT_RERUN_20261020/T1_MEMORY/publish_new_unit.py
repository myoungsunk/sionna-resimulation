"""Publish actual stored-trace parity receipts; no RF/model computation."""
from pathlib import Path
import csv,json,hashlib
HERE=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 rows=[];receipts=[]
 for route in ['C01','C02','C03','O01','O02','O03']:
  root=HERE/'execution_new_unit_39361490496'/route
  meta=json.loads((root/'ACTIONS_ARTIFACT.json').read_text());manifest=json.loads((root/'checks/NEW_RHO0_CHECKS.MANIFEST.json').read_text())
  assert manifest['technical']=='TECHNICAL_PASS' and manifest['source_run_id']==39359952488 and int(manifest['validation_run_id'])==39361490496
  assert json.loads((root/'checks/NEW_RHO0_CHECKS.ERRORS.json').read_text())==[]
  assert sha(root/'checks/NEW_RHO0_CHECKS.csv')==manifest['csv_sha256']
  with (root/'checks/NEW_RHO0_CHECKS.csv').open(newline='') as f:checks=list(csv.DictReader(f))
  for row in checks:
   assert row['technical']=='TECHNICAL_PASS' and float(row['state_max_abs'])<=1e-10 and float(row['cov_max_abs'])<=1e-10 and int(row['gate_mismatches'])==0
   rows.append(dict(route=route,**row))
  receipts.append(dict(route=route,artifact_id=meta['id'],artifact_sha256=meta['digest'],source_commit=meta['workflow_run']['head_sha'],receipt_manifest=str((root/'checks/NEW_RHO0_CHECKS.MANIFEST.json').relative_to(HERE)).replace('\\','/'),manifest_sha256=sha(root/'checks/NEW_RHO0_CHECKS.MANIFEST.json'),source_t2_artifact=manifest.get('source_artifact_receipt')))
 assert len(rows)==36 and len({r['trace'] for r in rows})==36
 out=HERE/'UNIT_TESTS_NEW.csv'
 with out.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 check=dict(technical='TECHNICAL_PASS',actions_run_id=39361490496,n=36,state_max_abs=max(float(r['state_max_abs']) for r in rows),cov_max_abs=max(float(r['cov_max_abs']) for r in rows),gate_mismatches=sum(int(r['gate_mismatches']) for r in rows),csv_sha256=sha(out),receipts=receipts,archive_verification='Full seven small archives downloaded and SHA256 checked by collector; raw NPZ not downloaded')
 p=HERE/'MANIFEST.json';m=json.loads(p.read_text(encoding='utf-8'));m['new_packet_rho0_state_cov_gate_check']=check;m['outputs']['UNIT_TESTS_NEW.csv']=sha(out);p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 report=HERE/'RESULTS_KO.md';s=report.read_text(encoding='utf-8');old='T2 요약에는 신규 RF의 MEMORY_RHO0 상태·공분산·gate parity가 별도 저장되지 않아 이 재귀 검사 부분은 요약 회수만으로 재확인하지 못했다.'
 new=f"신규 저장 trace 36개도 run39361490496에서 모든 시점의 물리 4차원 POWER1/MEMORY_RHO0 parity를 직접 검증했다. 최대 상태 차={check['state_max_abs']:.3e}, 공분산 차={check['cov_max_abs']:.3e}, gate 불일치=0. UNIT_TESTS_NEW.csv와 여섯 artifact receipt에 보존했다. 모델·RF를 재실행하지 않았다."
 assert old in s;report.write_text(s.replace(old,new),encoding='utf-8');print(json.dumps({k:v for k,v in check.items() if k!='receipts'}))
if __name__=='__main__':main()
