"""Copy recovered bytes, calculate final tables, preserve prior root summary bytes."""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess,sys
ROOT=Path(__file__).resolve().parents[4];HERE=ROOT/'research/POWERJOINT_AUDIT_FOLLOWUP_20261020/S3_Q1_POLICY'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def main():
 p=argparse.ArgumentParser();p.add_argument('--recovered',type=Path,required=True);p.add_argument('--final-run',type=int,required=True);a=p.parse_args();receipt=json.loads((a.recovered/'RECOVERY_RECEIPT.json').read_text());assert receipt['complete'];records=receipt['records'];selected=a.recovered/'selected_final';selected.mkdir(exist_ok=True);retired_errors=[]
 final_run=json.loads((a.recovered/f'RUN_{a.final_run}.json').read_text());assert final_run['conclusion']=='success','FINAL_RETRY_NOT_SUCCESS'
 for rec in records:
  source=a.recovered/f"run-{rec['actions_run_id']}"/rec['name'];target=HERE/'execution'/rec['name'];shutil.copytree(source,target,dirs_exist_ok=True)
  if rec['actions_run_id'] in [39378144903,a.final_run]:shutil.copytree(source,selected/rec['name'],dirs_exist_ok=True)
  else:
   for path in source.rglob('ERRORS.json'):
    for error in json.loads(path.read_text()):retired_errors.append(dict(source_run=rec['actions_run_id'],source_artifact=rec['artifact_id'],resolved_by_run=a.final_run,resolved=True,**error))
 for name in ['RECOVERY_RECEIPT.json','PUBLIC_BUNDLE_RECEIPT.json']:shutil.copy2(a.recovered/name,HERE/name)
 if (a.recovered/'failure_logs').exists():shutil.copytree(a.recovered/'failure_logs',HERE/'failure_logs',dirs_exist_ok=True)
 for pattern in ['RUN_*.json','JOBS_*.json']:
  for path in a.recovered.glob(pattern):shutil.copy2(path,HERE/'execution'/path.name)
 subprocess.run([sys.executable,'-X','utf8',str(HERE/'aggregate.py'),'--inputs',str(selected),'--out',str(HERE)],check=True)
 errors=json.loads((HERE/'ERRORS.json').read_text());errors.extend(retired_errors)
 if (HERE/'preparation_failures/ERRORS.json').exists():
  for error in json.loads((HERE/'preparation_failures/ERRORS.json').read_text()):errors.append(dict(resolved=True,resolved_by_run=receipt['preservation_actions_run_id'] if 'preservation' in error['stage'] else a.final_run,**error))
 dump(HERE/'ERRORS.json',errors)
 for name in ['MODELS.json','MARGINS.json']:
  source=list((HERE/'execution').rglob(name));assert len(source)==1;shutil.copy2(source[0],HERE/name)
 # Model index references keep the original OOF-model JSON byte-identical too.
 for source in (HERE/'execution').rglob('MODELS_OOF_*.json'):shutil.copy2(source,HERE/source.name)
 decision=json.loads((HERE/'DECISION.json').read_text());lock=json.loads((HERE/'PROTOCOL_LOCK.json').read_text())
 manifest=dict(task='S3_Q1_POLICY',technical=decision['technical'],scientific=decision['scientific'],go_no_go=decision['go_no_go'],scope='S3 only; stop after verification and preservation',protocol_commit='17274785e30a033dd242088e57bc9ff197b3fca1',label_code_commit='1e092428b178d2f5ab2ac1c022f6956d01373363',initial_train_evaluation_code_commit='b3e60de790764d834da07260a0d4bd8318f939c4',train_evaluation_code_commit=final_run['head_sha'],final_evaluation_run=a.final_run,preserved_S2_commit='8821d2e4d80ed749b5c4c5e3901e42957d29b2eb',engine_sha256=lock['engine_sha256'],sensor_lock_sha256=lock['sensor_lock_sha256'],protocol_sha256=sha(HERE/'PROTOCOL_LOCK.json'),original_artifacts=records,public_summary_bundle=json.loads((HERE/'PUBLIC_BUNDLE_RECEIPT.json').read_text()),code_sha256={str(p.relative_to(HERE)):sha(p) for p in HERE.rglob('*.py') if '__pycache__' not in p.parts})
 dump(HERE/'MANIFEST.json',manifest)
 report=HERE/'RESULTS_KO.md';proof=manifest['public_summary_bundle']
 report.write_bytes(report.read_bytes()+f"\n## 실행과 보존 증거\n\n사전 등록 commit: 17274785e30a033dd242088e57bc9ff197b3fca1. label 코드 commit: 1e092428b178d2f5ab2ac1c022f6956d01373363. 최종 학습·평가 run: {a.final_run}, head: {final_run['head_sha']}. 원본 archive {len(records)}개의 전체 SHA256·CRC·멤버 SHA와 release 재다운로드 SHA를 MANIFEST.json에 기록했다. 요약 release asset: {proof['bundle_release_url']}, SHA256: {proof['bundle_sha256']}.\n\n최초 학습 대기 run 39378550447의 연결 오류와 최초 보존 run 39380336271의 경로 오류를 보존했다. 고정 label·학습·평가 계약을 바꾸지 않고 각각 run 39380603592와 39380765996으로 재시도했다. 이전 실패 자료와 재시도 관계는 ERRORS.json 및 preparation_failures/에 남긴다. 결과 파일의 최종 git commit과 전체 hash index는 MANIFEST.json 및 OUTPUT_INDEX.json을 따른다.\n".encode('utf-8'))
 summary=HERE.parent/'00_SUMMARY_KO.md';old=summary.read_bytes();marker='## S3 Q1 v3'.encode('utf-8')
 if marker not in old:
  addition=f"\n\n## S3 Q1 v3\n\n| 과제 | TECHNICAL | 과학 판정 | 핵심 수치 | 증거 |\n|---|---|---|---|---|\n| S3 Q1 v3 | {decision['technical']} | {decision['scientific']} / {decision['go_no_go']} | Full {decision['full_pass']}/64, Native LoS {decision['los_pass']}/8 | S3_Q1_POLICY/MANIFEST.json 및 RESULTS_KO.md |\n\nS0/S1/S2 및 v2 NO-GO를 보존한다. HGB 단계 조건부 route OOF이며 전체 pipeline OOF·coverage 보장은 없다. S3 이후 다음 연구 단계는 시작하지 않는다.\n"
  summary.write_bytes(old+addition.encode('utf-8'))
 print('S3_ASSEMBLED',len(records),flush=True)
if __name__=='__main__':main()
