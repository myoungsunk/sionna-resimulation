"""Byte-preserving local result staging, full-roster aggregation and reporting."""
from pathlib import Path
import argparse,hashlib,json,re,shutil,subprocess,sys
import pandas as pd
HERE=Path(__file__).resolve().parent
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def dump(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def copy(src,dst):
 dst.parent.mkdir(parents=True,exist_ok=True)
 if dst.exists():assert src.read_bytes()==dst.read_bytes(),('REFUSE_REPLACE_DIFFERENT_RESULT',dst)
 else:shutil.copyfile(src,dst)
def main():
 p=argparse.ArgumentParser();p.add_argument('--recovery',type=Path,required=True);a=p.parse_args()
 recovery=json.loads((a.recovery/'RECOVERY_RECEIPT.json').read_text());assert recovery['complete']
 lock=json.loads((HERE/'PROTOCOL_LOCK.json').read_text());old=json.loads((HERE/'PROTOCOL_LOCK_V1.json').read_text())
 strip=lambda d:{k:v for k,v in d.items() if k not in ['version','amendment','implementation_sources_sha256']}
 assert strip(lock)==strip(old),'SCIENTIFIC_PROTOCOL_CHANGED'
 selected=[];prior=[]
 for record in recovery['records']:
  route=re.search(r'-s1-([A-Z0-9]+)-',record['name']).group(1)
  canonical=(record['actions_run_id']==(39370942876 if route in ('R2','R5') else 39370673576))
  root=a.recovery/f"run-{record['actions_run_id']}"/record['name'];src=root/'s1'/route
  assert src.is_dir(),('MISSING_ROUTE_RESULT',route)
  dest=HERE/('execution' if canonical else 'FAILED_EXECUTION_R01')/route
  for path in src.rglob('*'):
   if not path.is_file():continue
   if path.suffix.lower() not in ['.json','.csv','.md']:continue
   if path.stat().st_size>20_000_000:raise ValueError('CSV_GT_20MB:'+str(path))
   copy(path,dest/path.relative_to(src))
  for rel in ['s1_inputs/PAIRING_RECEIPT.json','s1_inputs/BUNDLE.json','source_route/ARCHIVE_CONTENTS_AND_SHA.json',
              f'canonical_t2/{route}/S1_RESTORE_RECEIPT.json','RESTORE_RECEIPT.json','old_bundle/BUNDLE.json']:
   path=root/rel
   if path.is_file():copy(path,dest/'input_receipts'/rel)
  copy(root/'OUTPUT_ARCHIVE_RECEIPT.json',dest/'OUTPUT_ARCHIVE_RECEIPT.json')
  rec={k:record[k] for k in ['artifact_id','actions_run_id','source_commit','archive_sha256','archive_bytes','expires_at','full_archive_download_verified','all_member_CRC_verified','release_asset_id','release_asset_url','release_readback_sha256','release_readback_bytes']}
  rec.update(route=route,canonical=canonical)
  (selected if canonical else prior).append(rec)
 assert len(selected)==8 and {r['route'] for r in selected}==set(lock['routes'])
 for r in selected:
  manifest=json.loads((HERE/'execution'/r['route']/'MANIFEST.json').read_text())
  assert manifest['technical']=='TECHNICAL_PASS_CORE',('CANONICAL_EXECUTION_ERROR',r['route'])
 subprocess.run([sys.executable,str(HERE/'aggregate.py'),'--runs',str(HERE/'execution'),'--out',str(HERE)],check=True)
 d=json.loads((HERE/'DECISION.json').read_text());assert d['technical']=='TECHNICAL_PASS_CORE'
 table=pd.read_csv(HERE/'INTERVENTIONS.csv');assert len(table)==79*2*5
 assert not table.duplicated(['event','bias','arm']).any()
 assert len(pd.read_csv(HERE/'EVENT_TABLE.csv'))==79 and len(pd.read_csv(HERE/'EVENT_TABLE_L2.csv'))==79
 checks=pd.read_csv(HERE/'BASELINE_CHECKS.csv');assert len(checks)==30
 assert checks.gate_mismatches.eq(0).all() and checks.adapter_identity_gate_mismatches.eq(0).all()
 assert checks.stored_heading_difference_deg.max()<=1e-6
 assert table.scorer_max_abs_difference.max()<=1e-9
 assert checks.adapter_identity_state_max.max()<=1e-10 and checks.adapter_identity_cov_max.max()<=1e-10
 error_sources=[]
 for rec in prior:
  er=json.loads((HERE/'FAILED_EXECUTION_R01'/rec['route']/'ERRORS.json').read_text())
  error_sources.extend(dict(source_run=rec['actions_run_id'],route=rec['route'],**x) for x in er['execution_errors'])
 er=json.loads((HERE/'ERRORS.json').read_text());er['preserved_first_run_execution_errors']=error_sources
 er['retry_reason']='Exact float64 CSV parsing only; identical scientific roster, thresholds and RF/sensor/POWER inputs'
 dump(HERE/'ERRORS.json',er)
 final=dict(task='S1_N1_EVENTS',technical=d['technical'],scientific=d['scientific'],event_count=79,
     canonical_artifacts=selected,preserved_failed_artifacts=prior,protocol_lock_commit='306270154b528ba2ae3fd24b5786ff1735ed4c2b',
     first_lock_commit='cccac1fee2892576f3a3b41ae4a6ecb54dd318d0',protocol_lock_sha256=sha(HERE/'PROTOCOL_LOCK.json'),
     event_list_sha256=sha(HERE/'EVENT_LIST.csv'),engine_commit=lock['engine_commit'],engine_sha256=lock['engine_sha256'],
     sensor_lock_sha256=lock['new_sensor_lock_sha256'],scientific_protocol_identical_across_parser_amendment=True,
     QA=dict(baseline_cases_bias=30,gate_mismatches=int(checks.gate_mismatches.sum()),
             max_heading_reproduction_difference_deg=float(checks.stored_heading_difference_deg.max()),
             max_common11_independent_scorer_difference=float(table.scorer_max_abs_difference.max()),
             max_adapter_state_difference=float(checks.adapter_identity_state_max.max()),
             max_adapter_covariance_difference=float(checks.adapter_identity_cov_max.max()),
             intervention_rows=len(table),original_failed_execution_errors=len(error_sources)),
     D7_not_evaluable_count=d['D7_unavailable_count'],original77_status='BLOCKED_SOURCE_UNAVAILABLE',
     trace_policy='NPZ in original Actions archives and durable audit-traces-20261020-r01 release mirrors, full SHA/CRC and complete release readback verified; expiry above applies to Actions only. No trace overwritten or deleted.',
     preservation_actions_run_id=recovery.get('preservation_actions_run_id'),
     output_recovery_transport='LOCAL_RECOVERY_TRANSPORT.json',
     S2_S3_executed=False,new_RF_simulation=False)
 dump(HERE/'MANIFEST.json',final)
 lines=['# S1 N1 이벤트 검증 결과','',f"**{d['technical']} / {d['scientific']}**. B0가 주 판정이며 L2는 보조다. 모든 이벤트 개입은 `ORACLE_DIAGNOSTIC`이다.",'',
   '개정 격자로 후보110개를 열거해79개(기존35/신규44)를 고정했다. 종료 후30초가 부족한31개는 원래 후보와 제외 사유를 보존했다. 신규 물리61개는 RF 행 범위·개수·시각61/61 일치했다. 원래30+47개 source의 상태는 BLOCKED_SOURCE_UNAVAILABLE이며 이79개가 원래77개라고 주장하지 않는다.','',
   '| 범위 | 유해 D2 회수≥50% | 유익 D2 악화≤skip의50% | 중립 | 과학 판정 |','|---|---:|---:|---:|---|']
 for scene,g in d['groups'].items():lines.append(f"| {scene} | {g['harmful_numerator']}/{g['harmful_denominator']} | {g['beneficial_numerator']}/{g['beneficial_denominator']} | {g['neutral_count']} | {g['scientific']} |")
 lines+=['','각 비율은 조건 수를 독립 표본 수로 해석하지 않는다. corridor는 R2/R4/R5/C01–C03의 같은 장면이며 office는 O02/O03의 한 장면이다. O01은 포함 가능한30초 horizon 이벤트가0개다. p-value는 계산·보고하지 않는다.','',
   '## 검증과 오류 보존','',
   f"정본30개 case×bias에서 과거 POWER1 gate 불일치0, Heading 차이 최대{final['QA']['max_heading_reproduction_difference_deg']:.17g}°. 현 실행 모든 유효 개입의11개 지표를 독립 scalar/Cholesky scorer로 재계산한 최대차는{final['QA']['max_common11_independent_scorer_difference']:.17g}이다. no-change joint adapter의 state/cov 최대차는{final['QA']['max_adapter_state_difference']:.17g}/{final['QA']['max_adapter_covariance_difference']:.17g}이다. pinned engine과 T4 helper는 원본 bytes를 유지했다.",'',
   f"첫 run39370673576의 R2/R5에서 CSV 기본 float parser 때문에 원본 시각과 약1e-14s 차이가 발생했다. 오류{len(error_sources)}건과 모든 첫 출력은 FAILED_EXECUTION_R01/에 보존했다. V2 lock3062701은 round_trip parser만 적용하며 입력/이벤트 행/과학 임계값을 바꾸지 않았다. 재실행39370942876의 R2/R5와 첫 실행의 나머지6개 성공 결과를 정본으로 묶었다.",'',
   '## D7 적용 범위','',
   f"D7 평가 불가{d['D7_unavailable_count']}개 event×bias 행을 삭제하지 않았다. 기존 주로 실제los_exists 미인증은 NOT_EVALUABLE_LOS_STATUS_UNCERTIFIED, 실제 차단이 포함된 신규 이벤트는 NOT_EVALUABLE_LOS_BLOCKED로 남겼다. 신규 평가 가능한 행만 same-pose 실제 Native LoS s와mu_s=0을 적용하고 rawFull range·mu_r·C와 원래 joint gate를 유지했다.",'',
   '| 범위 | D7 평가 가능한 유해 이벤트 | D7·D2 모두 회수≥50% | D7<20%, D2≥50% 패턴 |','|---|---:|---:|---:|']
 for scene,g in d['groups'].items():lines.append(f"| {scene} | {g['D7_evaluable_harmful']} | {g['observation_replacement_recovered']} | {g['D7_low_D2_high_pattern']} |")
 lines+=['','마지막 열은 이 D7/D2 비교에서만 나타난 제한된 패턴이며 필터 구조 변경의 인과적 필요성이나 모든 관측 교정의 불가능성을 뜻하지 않는다.','',
   '## Full-only 특징','',f"기존 T7A SPEC12 중 개정 포함 명단과 RF 행·시각이 정확히 맞는 이벤트는{d['feature_exact_matched']}/12이다. ONLINE_FEATURE_MAPPING.csv에서 누락/불일치를 표시했다. 온라인 특징 정의를 확대하지 않았다. r_D2와의 Spearman은 그중 B0 유해 이벤트에 한정되며 특징별 분모를 ONLINE_FEATURE_SPEARMAN.csv에 기록했다.",'',
   '## 산출물·정본','',
   'EVENT_TABLE.csv와 EVENT_TABLE_L2.csv는 각각79개 고정 행이다. INTERVENTIONS.csv는790개 event×bias×arm의 POST30 지표·평가 불가 상태를 포함한다. 실행별 PACKET_LOG, FIRST_HARMFUL_UPDATE, DIVERGENCE, GROWTH와 원본 manifest는 execution/에 보존한다. MANIFEST.json에 run·artifact·archive SHA256·expiry와 엔진/센서 hash를 기록했다. 대용량NPZ는 원래 Actions artifact와 audit-traces-20261020-r01 release mirror에 보존했다. 각 원본 전체 SHA/CRC와 release 전체 readback을 확인했다. Windows 직접 전송 취소와 부분 파일 보존은 LOCAL_RECOVERY_TRANSPORT.json에 기록했다.','',
   f"엔진 `{lock['engine_commit']}`, SHA256 `{lock['engine_sha256']}`. 센서 lock SHA256 `{lock['new_sensor_lock_sha256']}`. B_OLD=−0.5315983906250129m이며 SRC_TAP은 사용하지 않았다.",'',
   '## 주장하지 않는 것','',
   '독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증, 온라인 정책의 성능, D7 패턴의 인과적 필요성, 원래77개 명단 복원을 주장하지 않는다. S0의 OPEN/NOT_ESTABLISHED 잔차 판정은 유지한다. S2/S3, 새 gate·기억 모델, RF 시뮬레이션, T6 tap EKF 및 D4 대체는 실행하지 않았다. S1 결과에서 멈춘다.']
 (HERE/'RESULTS_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 summary=HERE.parent/'00_SUMMARY_KO.md';marker='## S1 최종 개정 격자 실행 결과'
 assert marker not in summary.read_text(encoding='utf-8')
 g=d['groups']['overall']
 with summary.open('a',encoding='utf-8') as f:f.write(f"\n\n{marker}\n\n| 과제 | TECHNICAL | 과학 판정 | 핵심 수치 | commit / run / artifact |\n|---|---|---|---|---|\n| S1 N1/D7 | {d['technical']} | {d['scientific']} | 79개; B0 유해 D2회수≥50% {g['harmful_numerator']}/{g['harmful_denominator']}; 유익 안전성 {g['beneficial_numerator']}/{g['beneficial_denominator']} | lock cccac1f/v2 3062701; runs39370673576,39370942876; 각artifact는 S1 MANIFEST |\n\n앞선 S1 입력 차단은 원래77개 source에 대해 유지하되, 사용자 승인 개정 격자79개 실행은 완료했다. 원래30+47 복원을 뜻하지 않는다. 첫 CSV parser 오류와 재실행을 모두 보존했으며 과학 기준은 동일하다. D7 미평가{d['D7_unavailable_count']}개 event×bias 행과 특징 대응 분모는 S1 보고서에 명시했다. S0 수치·판정은 위에 그대로 유지한다. S2/S3로 진행하지 않았다.\n")
 # Final index excludes itself to avoid a circular hash claim.
 outputs={str(p.relative_to(HERE)):dict(sha256=sha(p),bytes=p.stat().st_size) for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='OUTPUT_INDEX.json'}
 dump(HERE/'OUTPUT_INDEX.json',{'outputs':outputs,'root_summary_sha256':sha(summary)})
 print('S1_FINAL_REPORT_READY',d['scientific'],'files',len(outputs),flush=True)
if __name__=='__main__':main()
