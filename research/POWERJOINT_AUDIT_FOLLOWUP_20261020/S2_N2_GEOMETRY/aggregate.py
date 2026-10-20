"""Locked S2 denominators; missing/error rows never discarded from decisions."""
from pathlib import Path
import argparse,hashlib,json
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def main():
 p=argparse.ArgumentParser();p.add_argument('--execution',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 frames=[];aux=[];checks=[];refs=[];errors=[];manifests=[]
 for route in ['R2','R4','R5','C01','C02','C03','O01','O02','O03']:
  folder=a.execution/route
  if not (folder/'MANIFEST.json').exists():errors.append(dict(route=route,error='MISSING_ROUTE_OUTPUT'));continue
  manifests.append(json.loads((folder/'MANIFEST.json').read_text()));errors.extend(json.loads((folder/'ERRORS.json').read_text()))
  for name,target in [('RESULTS',frames),('RF_ONLY_RESULTS',aux),('CHECKS',checks),('LOS_REFERENCE',refs)]:
   path=folder/f'{name}.csv'
   try:target.append(pd.read_csv(path,float_precision='round_trip'))
   except pd.errors.EmptyDataError:pass
 matrix=pd.read_csv(HERE/'CASE_MATRIX.csv');key=['case','channel','bias','seed','arm']
 df=pd.concat(frames,ignore_index=True) if frames else pd.DataFrame(columns=key+['status'])
 assert not df.duplicated(key).any(),'DUPLICATE_RESULT_KEYS'
 df=matrix.merge(df.drop(columns=[c for c in ['route','mount_status','fold','population','primary_scope'] if c in df]),on=key,how='left',validate='one_to_one')
 df['status']=df.status.fillna('MISSING_OUTPUT');assert len(df)==792
 df.to_csv(a.out/'RESULTS.csv',index=False)
 pd.concat(aux,ignore_index=True).to_csv(a.out/'RF_ONLY_RESULTS.csv',index=False)
 check=pd.concat(checks,ignore_index=True);check.to_csv(a.out/'CHECKS.csv',index=False)
 reference=pd.concat(refs,ignore_index=True);reference.to_csv(a.out/'LOS_REFERENCE.csv',index=False)
 cells=[]
 for keys,g in df.groupby(['case','route','population','channel','bias','seed'],sort=True):
  by=g.set_index('arm');rec=dict(zip(['case','route','population','channel','bias','seed'],keys));valid=len(g)==4 and g.status.eq('TECHNICAL_PASS').all()
  rec['valid']=bool(valid)
  if valid:
   q,d,geom,gq=[float(by.loc[k].heading_rmse_deg) for k in ['Q_POWER1','DIST_ONLY','GEOM','GEOM_Q']]
   rec.update(Q_POWER1=q,DIST_ONLY=d,GEOM=geom,GEOM_Q=gq,geom_le_110pct_q=bool(geom<=1.10*q),geom_le_110pct_dist=bool(geom<=1.10*d),geom_q_lt_95pct_geom=bool(gq<.95*geom),GEOM_minus_Q_deg=geom-q,GEOM_minus_DIST_deg=geom-d,GEOM_Q_minus_GEOM_deg=gq-geom)
  cells.append(rec)
 gain=pd.DataFrame(cells);gain.to_csv(a.out/'GAIN_COMPARISON.csv',index=False)
 new=gain[(gain.population=='new')&(gain.seed==0)];old=gain[(gain.population=='legacy')&(gain.channel=='full')&gain.case.str.endswith('_m0')]
 assert len(new)==36 and len(old)==12,'LOCKED_PRIMARY_DENOMINATORS'
 complete=len(manifests)==9 and all(m['technical']=='TECHNICAL_PASS' for m in manifests) and df.status.eq('TECHNICAL_PASS').all() and len(reference)==4 and not errors
 nnew=int(new.get('geom_le_110pct_q',pd.Series(dtype=bool)).fillna(False).sum());nold=int(old.get('geom_le_110pct_dist',pd.Series(dtype=bool)).fillna(False).sum());nq=int(new.get('geom_q_lt_95pct_geom',pd.Series(dtype=bool)).fillna(False).sum())
 violations=[]
 for group,column,denom in [(new,'geom_le_110pct_q','NEW_SEED0_36'),(old,'geom_le_110pct_dist','LEGACY_M0_12')]:
  for r in group.to_dict('records'):
   if not r.get(column,False):violations.append(dict(denominator=denom,**r))
 pd.DataFrame(violations).to_csv(a.out/'VIOLATIONS.csv',index=False)
 safety=[]
 for r in df[df.channel=='los'].to_dict('records'):
  base=reference[(reference.case==r['case'])&(reference.bias==r['bias'])&(reference.seed==r['seed'])]
  rec={k:r[k] for k in key};rec['status']=r['status']
  if len(base)==1 and r['status']=='TECHNICAL_PASS':
   baseline=float(base.iloc[0].heading_rmse_deg);value=float(r['heading_rmse_deg']);diff=value-baseline
   rec.update(arm_heading_rmse_deg=value,R0_heading_rmse_deg=baseline,absolute_change_deg=diff,relative_change=None if abs(baseline)<=1e-12 else diff/baseline,relative_status='ZERO_OR_TINY_DENOMINATOR' if abs(baseline)<=1e-12 else 'DEFINED')
  safety.append(rec)
 los=pd.DataFrame(safety);los.to_csv(a.out/'LOS_SAFETY.csv',index=False)
 repeats=[]
 for keys,g in df[df.population=='new'].groupby(['case','bias','arm'],sort=True):
  valid=g[g.status=='TECHNICAL_PASS'];rec=dict(zip(['case','bias','arm'],keys));rec.update(expected_seeds=5,valid_seeds=len(valid))
  if len(valid):
   worst=valid.loc[valid.heading_rmse_deg.idxmax()];rec.update(heading_min_deg=float(valid.heading_rmse_deg.min()),heading_median_deg=float(valid.heading_rmse_deg.median()),heading_max_deg=float(valid.heading_rmse_deg.max()),worst_seed=int(worst.seed))
  cg=gain[(gain.case==keys[0])&(gain.bias==keys[1])]
  if keys[2]=='GEOM':rec.update(violating_seeds_vs_Q=int((~cg.geom_le_110pct_q.fillna(False).astype(bool)).sum()),violating_seeds_vs_DIST=int((~cg.geom_le_110pct_dist.fillna(False).astype(bool)).sum()))
  if keys[2]=='GEOM_Q':rec.update(improving_seeds_gt5pct=int(cg.geom_q_lt_95pct_geom.fillna(False).sum()))
  repeats.append(rec)
 pd.DataFrame(repeats).to_csv(a.out/'SEED_SUMMARY.csv',index=False)
 groups=[]
 scopes=[('NEW_SEED0_36',new),('OLD_FULL',gain[(gain.population=='legacy')&(gain.channel=='full')]),('OLD_M0',old),('OLD_M45',gain[(gain.population=='legacy')&gain.case.str.endswith('_m45')&(gain.channel=='full')])]
 for seed in range(5):
  for scene,prefix in [('NEW_CORRIDOR','C'),('NEW_OFFICE','O'),('NEW_ALL',None)]:
   g=gain[(gain.population=='new')&(gain.seed==seed)]
   if prefix:g=g[g.case.str.startswith(prefix)]
   scopes.append((f'{scene}_SEED{seed}',g))
 for name,g in scopes:groups.append(dict(scope=name,denominator=len(g),valid=int(g.valid.sum()),geom_q_improved_gt5pct=int(g.geom_q_lt_95pct_geom.fillna(False).sum()),geom_within110pct_Q=int(g.geom_le_110pct_q.fillna(False).sum())))
 pd.DataFrame(groups).to_csv(a.out/'GROUP_COMPARISON.csv',index=False)
 decision=dict(technical='TECHNICAL_PASS' if complete else 'ERROR_OR_INCOMPLETE',scientific='SUPPORTED_BUT_LIMITED' if complete and nnew==36 and nold==12 else 'NOT_ESTABLISHED',trained_rows=792,valid_rows=int(df.status.eq('TECHNICAL_PASS').sum()),los_R0_rows=len(reference),new_seed0=dict(pass_cells=nnew,denominator=36),legacy_M0=dict(pass_cells=nold,denominator=12),geom_q_additional=dict(improved_cells=nq,denominator=36,threshold_cells=19,limited_accuracy_statement_allowed=bool(complete and nq>=19)),violations=violations,independent_11_max_abs=float(df.scorer_max_abs_difference.max()),OOD='R2 A M45 heldout OUT_OF_TRAINING_RANGE_MOUNT',independence='old/C routes same corridor scene; office routes one office scene; seeds are motion-noise repeats; no p-value',stop='S2 finished only; S3 not started')
 dump(a.out/'DECISION.json',decision);dump(a.out/'ERRORS.json',errors)
 dump(a.out/'MANIFEST.json',dict(task='S2_AGGREGATE',technical=decision['technical'],scientific=decision['scientific'],protocol_sha256=sha(HERE/'PROTOCOL_LOCK.json'),model_sha256=sha(HERE/'TRAIN_PARAMS.json'),routes=manifests,outputs={p.name:sha(p) for p in a.out.iterdir() if p.is_file() and p.name not in ['MANIFEST.json','RESULTS_KO.md']}))
 report=f'''# S2 N2 기하 특징 검증

기술적 상태: **{decision['technical']}**. GEOM q 대체 후보: **{decision['scientific']}**.

승인된 확장으로 GEOM/GEOM_Q 평균 회귀는 10/11차원, 잔차 평균·공분산은 같은 학습 3D 거리 삼분위다. 검증된 실행 기준 엔진 @034e57a 본문과 SourceFFD 관측, B_OLD, H·gate·update를 보존했다. 주 평가는 전체 motion clock의 t≥30 s, seed 0이다.

| 사전 고정 기준 | 통과 | 필요한 통과 |
|---|---:|---:|
| 신규 seed 0 GEOM ≤ 1.10 Q | {nnew}/36 | 36/36 |
| 기존 M0 GEOM ≤ 1.10 DIST_ONLY | {nold}/12 | 12/12 |
| 신규 seed 0 GEOM_Q < 0.95 GEOM | {nq}/36 | 19/36 |

위반 셀과 실제 Heading RMSE는 VIOLATIONS.csv, 전체 네 arm 비교는 GAIN_COMPARISON.csv에 보존했다. 계산 실패/누락을 삭제하여 분모를 줄이지 않았다. 공통 11개 지표는 RESULTS.csv의 {int(df.status.eq('TECHNICAL_PASS').sum())}/792행과 별도 Native LoS R0 {len(reference)}/4행에 있다. 독립 scalar/Cholesky scorer 최대 차이는 {decision['independent_11_max_abs']:.17g}다.

Native LoS 각 arm의 R0 대비 절대·상대 변화는 LOS_SAFETY.csv에 별도로 기록했다. 안전성은 GEOM 지지식과 분리한다. 같은 RF의 motion noise 반복은 SEED_SUMMARY.csv에서 셀별 min/median/max·최악 seed·위반 seed 수로 보고한다. seed 평균으로 seed 0 실패를 상쇄하지 않는다. 그룹별 q 추가 개선 분모는 GROUP_COMPARISON.csv에 분리했다.

## 재현과 제한

Q 기준선은 기존 Full의 역사적 POWER1 trace/KEY_B0, Native LoS의 T9 Q trace, 신규 seed 0의 T2 trace와 대조했다. 신규 seed 1–4는 동결 T2 코드/μ/C로 재생성한 reference이며 역사적 gate trace 일치를 주장하지 않는다. 같은 seed/bias/motion의 T2 Heading 지표도 대조했다. DIST_ONLY–T9 차이는 CHECKS.csv의 행별 기록을 참조한다. 입력 SHA, 학습 key/site 분할, 모델 파라미터, 실패는 삭제하지 않았다.

R2 A M45 heldout은 **OUT_OF_TRAINING_RANGE_MOUNT**다. mount 특징을 추가해도 학습에 M45가 없는 한계가 해결되었다고 주장하지 않는다. 미확보 입력/실패는 ERRORS.json 및 technical 상태에 따른다.

## 주장하지 않는 것

독립 장면 일반화, 조건 수·seed 수를 독립 표본 수로 해석한 유의성, q의 물리 기전 또는 인과적 독립 정보 증명, 정규화 Bayesian posterior, 실측 하드웨어 실증을 주장하지 않는다. S0 OPEN/NOT_ESTABLISHED, 원래 77개 BLOCKED_SOURCE_UNAVAILABLE 및 S1 개정 79개/실패 기록을 보존했다. S3는 시작하지 않았다.
'''
 if complete and nq>=19:report+='\n이 신규 평가 범위에서는 기하 특징에 q를 추가한 모델의 Heading 정확도 개선이 과반의 셀에서 관찰됐다.\n'
 (a.out/'RESULTS_KO.md').write_text(report,encoding='utf-8')
 print(json.dumps({k:v for k,v in decision.items() if k!='violations'}),flush=True)
if __name__=='__main__':main()
