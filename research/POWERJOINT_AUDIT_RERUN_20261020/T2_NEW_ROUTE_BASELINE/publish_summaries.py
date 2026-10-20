"""Publish preserved T2 summaries and merge T1; no RF or NPZ reads."""
from pathlib import Path
import csv,json,hashlib,math,shutil
HERE=Path(__file__).resolve().parent; T1=HERE.parent/'T1_MEMORY'; REPO=HERE.parents[2]
ROUTES={'O01':12237161269,'C03':12237146888,'O03':12236673976,'C02':12236504528,'C01':12236404720,'O02':12236009723}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
 with p.open(newline='',encoding='utf-8-sig') as f:return list(csv.DictReader(f))
def write(p,rows):
 fields=list(dict.fromkeys(k for r in rows for k in r))
 with p.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fields);w.writeheader();w.writerows(rows)
def save(p,obj):p.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def main():
 merged={n:[] for n in ['BASELINE','CHECKS','ALL_METRICS','MOTION_NOISE_REPEAT_RANGE','T1_NEW_CANONICAL_RESULTS']}; receipts=[]; units=[]
 for route,aid in ROUTES.items():
  root=HERE/'execution_39359952488'/route;meta=json.loads((root/'ACTIONS_ARTIFACT.json').read_text());runmeta=json.loads((root/'t2_new/MANIFEST.json').read_text())
  assert meta['id']==aid and int(runmeta['actions_run_id'])==39359952488 and runmeta['technical']=='TECHNICAL_PASS'
  assert not list(root.rglob('*.npz')) and not list(root.rglob('*.npy'))
  for member in meta['recovery']['member_sha256']:assert sha(root/member['member'])==member['sha256']
  for name in merged:merged[name].extend(read(root/'t2_new'/f'{name}.csv'))
  for u in read(root/'unit/UNIT_TESTS.csv'):
   assert u['pass_']=='True';units.append({'route':route,**u})
  receipts.append(dict(route=route,artifact_id=aid,artifact_digest=meta.get('digest'),source_commit=meta.get('workflow_run',{}).get('head_sha'),execution_manifest=str((root/'t2_new/MANIFEST.json').relative_to(HERE)).replace('\\','/'),execution_manifest_sha256=sha(root/'t2_new/MANIFEST.json'),**{k:runmeta[k] for k in ['sensor_settings_sha256','engine_sha256','sensor','inputs']}))
 for r in merged['MOTION_NOISE_REPEAT_RANGE']:
  r['motion_noise_seed_count']=5 if r['arm'] in ['DR4','JOINT4','POWER1'] else 1
 for n,rs in merged.items():write(HERE/f'{n}.csv',rs)
 write(HERE/'UNIT_TESTS_BY_ROUTE.csv',units)
 assert len(merged['BASELINE'])==108 and len(merged['CHECKS'])==180 and len(merged['T1_NEW_CANONICAL_RESULTS'])==324
 assert all(float(r['independent_scorer_max'])<=1e-9 and r['no_nonradio_updates']=='True' for r in merged['CHECKS'])
 sensor={r['sensor_settings_sha256'] for r in receipts};engine={r['engine_sha256'] for r in receipts};assert len(sensor)==len(engine)==1
 # Earlier figures are source comparisons, not parity targets: Chain F full precision; crosscase published 3 decimals.
 old=read(REPO/'research/CHAIN_VALIDATED_RESULTS_20261019/external_evidence/EXTERNAL_EVALUATION.csv')
 fmap={(r['case'],r['method'],float(r['bias_dps'])):r for r in old if r['scope']=='evaluation'}
 cross={'C01_A_M45_FULL':3.966,'C01_B_M45_FULL':5.028,'C02_A_M45_FULL':2.236,'C02_B_M45_FULL':1.221,'C03_A_M45_FULL':.610,'C03_B_M45_FULL':.801,'O01_O0_M45_FULL':.456,'O02_O0_M45_FULL':2.220,'O03_O0_M45_FULL':6.868};bias={'B0':0.,'L0':.01,'L1':.05,'L2':.2}
 comparisons=[]
 for r in merged['BASELINE']:
  f=fmap.get((r['case'],r['arm'],bias[r['bias']]));c=cross.get(r['case']) if r['arm']=='POWER1' and r['bias']=='B0' else None
  comparisons.append({**r,'chain_f_heading_rmse_deg':f['heading_rmse_deg'] if f else '', 'canonical_minus_chain_f_deg':float(r['heading_rmse_deg'])-float(f['heading_rmse_deg']) if f else '', 'crosscase_heading_rmse_deg_reported_3dp':c if c is not None else '', 'canonical_minus_crosscase_deg':float(r['heading_rmse_deg'])-c if c is not None else '', 'comparison_limit':'different motion/sensor/training conventions; not parity; crosscase only B0 POWER published'})
 write(HERE/'PREVIOUS_COMPARISON.csv',comparisons)
 baseline=[r for r in merged['BASELINE'] if r['arm']=='POWER1' and r['bias']=='B0']
 checksmax=max(float(r['independent_scorer_max']) for r in merged['CHECKS'])
 text='# T2 신규 주로 기준선 정본\n\nTECHNICAL_PASS. Actions run39359952488의 6개 성공 artifact에서 요약만 회수했다. BASELINE.csv는 9조건 × 4 bias × 3 arm =108행이다. seed0–4 motion noise 반복 180개 실행의 독립 scorer 최대 차는 '+f'{checksmax:.3e}'+', 비RF update는 0이다. 11개 공통 지표를 모두 보존했다.\n\n정본 센서 설정 hash: `'+next(iter(sensor))+'`. 실제 엔진 파일 SHA256: `'+next(iter(engine))+'`. 전체 .25s motion을 원래 생성기로 재구성했으며 모든 공개 RADIO_POSE CSV와 생성 RF CSV의 byte identity를 인증했다. Sensor-v2 원본 잡음·초기오차 스트림을 사용하고 최대 2µm CSV 반올림 lateral 잔차만 허용했다. RF는 원래 radio pose_id에서만 갱신한다. O03 los_exists=false는 그대로 보존하며 LoS를 생성하지 않는다.\n\n신규 POWER와 MEMORY는 기존 R2/R4/R5 전체로 학습했다. 이전 Chain F의 R2-heldout 학습 및 crosscase 센서와 다른 정의이므로 이전 숫자 parity를 주장하지 않는다. PREVIOUS_COMPARISON.csv에 108행별 이전 수치와 차이를 기록했으며 미공개 이전 값은 공란이다. crosscase 원본 구현은 미확보로 숫자 원인 완전 분해는 NOT_ESTABLISHED다.\n\n|조건|B0 POWER1 Heading RMSE (°)|\n|---|---:|\n'+''.join('|'+r['case']+'|'+f"{float(r['heading_rmse_deg']):.6f}"+'|\n' for r in baseline)+'\nMOTION_NOISE_REPEAT_RANGE.csv에서 DR4/JOINT4/POWER1만 seed0–4 범위이며, 나머지 arm은 seed0 단일 값(motion_noise_seed_count=1)이다. 반복 범위는 같은 RF의 motion noise 및 원래 초기오차 스트림 반복이다. 독립 RF/장면 표본이 아니다.\n\n## 주장하지 않는 것\n\n독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증을 주장하지 않는다. C01–C03과 기존 주로는 같은 복도, O01–O03은 같은 오피스 장면이다. 조건 수를 독립 표본 수로 쓰거나 p-value를 계산하지 않는다. 이전 실패 기록은 삭제하지 않았다.\n'
 (HERE/'RESULTS_KO.md').write_text(text,encoding='utf-8')
 manifest=dict(technical='TECHNICAL_PASS',scientific='NOT_ESTABLISHED',scope='canonical baseline fixed, not an efficacy hypothesis',actions_run_id=39359952488,sensor_settings_sha256=next(iter(sensor)),engine_sha256=next(iter(engine)),routes=receipts,row_counts={k:len(v) for k,v in merged.items()},independent_scorer_max=checksmax,raw_npz_downloaded=False,artifact_hash_limit='GitHub immutable artifact digest; retrieved members SHA256 and ZIP CRC verified; whole ZIP not locally downloaded')
 manifest['outputs']={p.name:sha(p) for p in HERE.glob('*.csv')};save(HERE/'MANIFEST.json',manifest)
 # Keep prior assessment verbatim as a historical correction, then merge all canonical rows.
 prior=T1/'RESULTS_KO.md';saved=T1/'RESULTS_OLD_SUPERSEDED_KO.md'
 if not saved.exists():shutil.copyfile(prior,saved)
 oldrows=read(T1/'CANONICAL_RESULTS_OLD.csv');allrows=[]
 for r in oldrows:allrows.append({**r,'dataset':'old','seed':0,'scope':'radio'})
 for r in merged['T1_NEW_CANONICAL_RESULTS']:allrows.append({**r,'dataset':'new'})
 assert len(allrows)==576 and len({(r['case'],r['bias'],r['arm']) for r in allrows})==576
 write(T1/'CANONICAL_RESULTS.csv',allrows)
 groups={}
 for r in allrows:groups.setdefault((r['case'],r['bias']),{})[r['arm']]=r
 verdict=[]
 for (case,b),arms in groups.items():
  p,m=arms['POWER1'],arms['MEMORY'];pr,mr=float(p['heading_rmse_deg']),float(m['heading_rmse_deg'])
  verdict.append(dict(case=case,bias=b,POWER1_heading_rmse_deg=pr,MEMORY_heading_rmse_deg=mr,heading_ratio=mr/pr,worse_over_10pct=mr>1.1*pr,heading95_improved=float(m['heading95'])>float(p['heading95']),POWER1_heading95=p['heading95'],MEMORY_heading95=m['heading95']))
 write(T1/'MEMORY_CRITERION.csv',verdict)
 worse=sum(r['worse_over_10pct'] for r in verdict);coverage=sum(r['heading95_improved'] for r in verdict);support=worse/64<=.1 and coverage/64>.5
 assert len(verdict)==64
 decision=dict(scientific='SUPPORTED_BUT_LIMITED' if support else 'NOT_ESTABLISHED',adoption_criterion='PASS' if support else 'FAIL',n_cells=64,worse_over_10pct=worse,worse_fraction=worse/64,coverage_improved=coverage,coverage_fraction=coverage/64,criterion_source='PROTOCOL_LOCK.json decision.otherwise=NOT_ESTABLISHED',correction='Supersedes old-only FALSIFIED_FOR_TESTED wording; no post-result decision threshold change',missing_original_implementations=['impl2','impl3'])
 save(T1/'DECISION.json',decision)
 tm=json.loads((T1/'MANIFEST.json').read_text());tm.setdefault('prior_old_manifest_scientific','FALSIFIED_FOR_TESTED');tm.update(scientific=decision['scientific'],scope='old7 plus new9 x4bias x9arms=576 rows',new_run_id=39359952488,new_route_receipts=receipts,decision=decision);tm['new_packet_rho0_state_cov_gate_check']='NOT_REVERIFIED_FROM_RECOVERED_SUMMARIES; actual-engine unit rho0 passed on all six jobs, full RF packet state/cov/gate parity not separately logged by T2';tm['outputs']={n:sha(T1/n) for n in ['CANONICAL_RESULTS.csv','MEMORY_CRITERION.csv','DECISION.json']};save(T1/'MANIFEST.json',tm)
 prior.write_text('# T1 시간기억 정본 재실행 완료\n\nTECHNICAL_PASS. 기존 7조건 × 4 bias × 9 arm=252행과 신규 9조건 × 4 bias × 9 arm=324행을 합쳐 CANONICAL_RESULTS.csv 576행을 보존했다. 구 주로는 route-heldout, 신규 주로는 기존 R2/R4/R5 전체 학습과 T2 정본 seed0 센서를 사용했다.\n\n사전 등록 판정 '+decision['scientific']+'; 채택 기준 '+decision['adoption_criterion']+f'. MEMORY의 Heading RMSE가 POWER1보다 10% 초과 악화된 셀은 {worse}/64 ({worse/64:.3%}), heading95 개선은 {coverage}/64 ({coverage/64:.3%})다. 전체 셀별 결과는 MEMORY_CRITERION.csv에 남겼다. R5 A M0 B0는 4.556146 → 8.764142°로 악화가 남는다.\n\n기존 수학 시험 500회 NEES=1.0886208364, coverage=.934; RF rho0 상태 최대 차3.997e−14, 공분산7.772e−16, gate 불일치0. 과거 POWER1 B0 RMSE 최대 차1.262e−13°, 독립 scorer2.274e−13. 신규 6개 작업도 수학 시험과 독립 scorer를 통과했다(T2 CHECKS/UNIT_TESTS_BY_ROUTE). T2 요약에는 신규 RF의 MEMORY_RHO0 상태·공분산·gate parity가 별도 저장되지 않아 이 재귀 검사 부분은 요약 회수만으로 재확인하지 못했다. 신규 기존 정본과의 역사적 gate parity는 존재하지 않으며 T2 자체를 첫 정본으로 고정한다.\n\n기준 구현은 원본3fc70f2280471954f1a0673009812ad75437d9ea이며 실제 실행 엔진 파일 hash/코드 revision은 MANIFEST와 각 artifact receipt에 보존했다. 구현2·3은 원본 미확보 BLOCKED_INPUT, 문서 재구성은 미시험이다. 이전 보고서의 FALSIFIED_FOR_TESTED 표현은 lock의 otherwise=NOT_ESTABLISHED와 달라 정정했다. 원문은 RESULTS_OLD_SUPERSEDED_KO.md에 그대로 남겼다.\n\n기존 run39358085399/artifact12236825429, 신규 run39359952488/6개 artifact. trace NPZ는 Actions에만 보존한다.\n\n## 주장하지 않는 것\n\n범용 기억 모델 승인, 독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증을 주장하지 않는다. 구현2·3 숫자·코드를 인증하지 않는다.\n',encoding='utf-8')
 print(json.dumps(dict(T2=manifest['row_counts'],decision=decision,sensor_hash=next(iter(sensor)),source_commits=sorted({r['source_commit'] for r in receipts})),ensure_ascii=False))
if __name__=='__main__':main()
