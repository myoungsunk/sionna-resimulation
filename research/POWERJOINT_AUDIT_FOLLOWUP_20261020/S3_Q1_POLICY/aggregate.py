"""Recalculate fixed denominators and report all valid violations without retuning."""
from pathlib import Path
import argparse,hashlib,json
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent
def dump(p,x):p.write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
def maximum(g,key):return float(g[key].max()) if key in g and g[key].notna().any() else None
def total(g,key):return int(g[key].sum()) if key in g else 0
def main():
 p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,required=True);p.add_argument('--out',type=Path,default=HERE);a=p.parse_args();a.out.mkdir(exist_ok=True)
 paths=list(a.inputs.rglob('POLICY_RESULTS.csv'));frames=[pd.read_csv(p) for p in paths];df=pd.concat(frames,ignore_index=True);assert len(df)==288 and not df.duplicated(['case','channel','bias','seed','arm','scope']).any(),'EVALUATION_DENOMINATOR'
 expected=pd.read_csv(HERE/'EVALUATION_MATRIX.csv');keys=['case','channel','bias','seed','arm','scope'];assert set(map(tuple,df[keys].values))==set(map(tuple,expected[keys].values)),'LOCKED_EVALUATION_KEYS'
 technical=(df.status=='TECHNICAL_PASS').all();comparison=[]
 for key,g in df.groupby(['case','channel','bias','seed']):
  case,channel,bias,seed=key;g=g.set_index('arm');base='POWER1' if channel=='full' else 'R0'
  for arm in ['POLICY_V3','POLICY_NO_MARGIN']:
   valid=all(g.loc[x,'status']=='TECHNICAL_PASS' for x in [arm,base]);b=float(g.loc[base,'heading_rmse_deg']) if valid else None;v=float(g.loc[arm,'heading_rmse_deg']) if valid else None
   comparison.append(dict(case=case,channel=channel,bias=bias,seed=int(seed),arm=arm,reference=base,status='VALID' if valid else 'TECHNICAL_INCOMPLETE',reference_rmse_deg=b,policy_rmse_deg=v,absolute_difference_deg=v-b if valid else None,ratio=v/b if valid and b!=0 else None,ratio_status='DEFINED' if valid and b!=0 else ('ZERO_DENOMINATOR' if valid else 'INCOMPLETE'),pass_10pct=bool(valid and v<=1.1*b)))
 comp=pd.DataFrame(comparison);v3=comp[comp.arm=='POLICY_V3'];full=v3[v3.channel=='full'];los=v3[v3.channel=='los'];assert len(full)==64 and len(los)==8
 errors=[]
 for path in a.inputs.rglob('ERRORS.json'):
  for e in json.loads(path.read_text()):errors.append(dict(source=str(path),**e))
 checks=pd.concat([pd.read_csv(p).assign(source_file=str(p.relative_to(a.inputs))) for p in a.inputs.rglob('CHECKS.csv')],ignore_index=True,sort=False);maxscore=float(df.scorer_max_abs_difference.max()) if 'scorer_max_abs_difference' in df else None
 hist=checks[checks.check=='HISTORICAL_POWER'];callback=checks[checks.check=='ALWAYS_POWER_CALLBACK'];keychecks=checks[checks.check=='KEY_B0']
 validation=dict(historical_cells=len(hist),historical_heading_max_deg=maximum(hist,'heading_difference_deg'),historical_gate_mismatches=total(hist,'gate_mismatches'),always_power_cells=len(callback),always_power_state_max=maximum(callback,'state_max'),always_power_cov_max=maximum(callback,'cov_max'),always_power_gate_mismatches=total(callback,'gate_mismatches'),nonradio_updates=total(callback,'nonradio_updates'),key_b0_cells=len(keychecks),key_b0_heading_max_deg=maximum(keychecks,'heading_difference_deg'))
 supported=bool(technical and not errors and full.pass_10pct.all() and los.pass_10pct.all())
 decision=dict(technical='TECHNICAL_PASS' if technical and not errors else 'ERROR_OR_INCOMPLETE',scientific='SUPPORTED_BUT_LIMITED' if supported else 'NOT_ESTABLISHED',go_no_go='GO_LIMITED' if supported else 'NO_GO',n_results=len(df),full_pass=int(full.pass_10pct.sum()),full_denominator=64,los_pass=int(los.pass_10pct.sum()),los_denominator=8,independent_11_max_abs_difference=maxscore,violations=v3[(v3.status=='VALID')&(~v3.pass_10pct)].to_dict('records'),technical_failures=v3[v3.status!='VALID'].to_dict('records'),no_margin=dict(full_pass=int(comp[(comp.arm=='POLICY_NO_MARGIN')&(comp.channel=='full')].pass_10pct.sum()),los_pass=int(comp[(comp.arm=='POLICY_NO_MARGIN')&(comp.channel=='los')].pass_10pct.sum())))
 decision['validation']=validation
 df.to_csv(a.out/'POLICY_RESULTS.csv',index=False);comp.to_csv(a.out/'POLICY_COMPARISON.csv',index=False);checks.to_csv(a.out/'CHECKS.csv',index=False)
 action_text=[]
 for name in ['ACTION_RATES','LABELS_SUMMARY']:
  parts=[pd.read_csv(p) for p in a.inputs.rglob(name+'.csv')]
  if parts:
   combined=pd.concat(parts,ignore_index=True,sort=False);combined.to_csv(a.out/(name+'.csv'),index=False)
   if name=='ACTION_RATES':
    for (channel,arm),g in combined[combined.scope=='t30_radio'].groupby(['channel','arm']):
     n=int(g.n_selected.sum());accepted=int(g.n_gate_accepted.sum());counts=g.groupby('action').n_selected.sum()
     action_text.append('| '+channel+' | '+arm+' | '+str(n)+' | '+' / '.join(f'{x} {int(counts.get(x,0))/n:.4%}' for x in ['POWER','R0','INFLATE4','SKIP'])+' | '+f'{accepted/n:.4%}'+' |')
 dump(a.out/'DECISION.json',decision);dump(a.out/'ERRORS.json',errors)
 marginpath=next(a.inputs.rglob('MARGINS.json'));margins=json.loads(marginpath.read_text());mtext='\n'.join(f"| {outer} | {action} | {r['delta']} | {r['n_selected']} | {r['status']} |" for outer,acts in margins['margins'].items() for action,r in acts.items())
 vio='\n'.join(f"| {r['case']} | {r['channel']} | {r['bias']} | {r['reference_rmse_deg']:.9f} | {r['policy_rmse_deg']:.9f} | "+(f"{r['ratio']:.6f}" if r['ratio'] is not None else 'ZERO_DENOMINATOR')+' |' for r in decision['violations'])
 report=f'''# S3 Q1 v3 결과

TECHNICAL: {decision['technical']}. 과학 판정: {decision['scientific']} / {decision['go_no_go']}.

주 판정: Full {decision['full_pass']}/64, Native LoS {decision['los_pass']}/8. 주 평가는 seed 0, 전체 motion clock t≥30 s다. NO_MARGIN은 같은 모델에서 margin만 0으로 적용한 대조이며 Full {decision['no_margin']['full_pass']}/64, LoS {decision['no_margin']['los_pass']}/8이다. v3 판정을 NO_MARGIN으로 대체하지 않는다.

독립 scalar/Cholesky scorer의 공통 11지표 최대 차이는 {maxscore}이다. historical POWER 재현과 항상 POWER callback, all-frame SPD/finite, nonradio update, 저장·재로딩 검사는 CHECKS.csv와 각 실행 manifest에 보존한다. 행동 선택 비율과 gate 수락은 ACTION_RATES.csv의 별도 열이다. POWER 선택을 갱신 수락으로 세지 않는다.

역사적 POWER {validation['historical_cells']}셀의 Heading 최대 차이는 {validation['historical_heading_max_deg']}°, gate 불일치는 {validation['historical_gate_mismatches']}이다. 항상 POWER callback {validation['always_power_cells']}셀의 상태/공분산 최대 차이는 {validation['always_power_state_max']} / {validation['always_power_cov_max']}, gate 불일치는 {validation['always_power_gate_mismatches']}, 비RF 갱신은 {validation['nonradio_updates']}이다. 기존 KEY_B0 {validation['key_b0_cells']}셀 최대 차이는 {validation['key_b0_heading_max_deg']}°다.

## 모든 v3 위반 셀

| case | channel | bias | 기준 RMSE° | v3 RMSE° | 비율 |
|---|---|---|---:|---:|---:|
{vio}

## 선택 조건부 margin

| outer | action | delta (deg²) | OOF 선택 행 | 상태 |
|---|---|---:|---:|---|
{mtext}

## 행동 선택과 gate 수락 (t≥30 s RF)

| 입력 | arm | RF 결정 수 | 행동 선택 비율 | 전체 gate 수락 비율 |
|---|---|---:|---|---:|
{chr(10).join(action_text)}

RF 결정 수는 동일 RF의 조건·bias 반복을 포함한 처리 횟수이며 독립 표본 수가 아니다. 자세한 셀별 수치는 ACTION_RATES.csv다. 선택과 수락을 구분한다.

## 해석 범위

학습은 전수 RF×4 bias×5 seed이며 label loss는 현재 시점 제외 (t,t+10s]의 단발 개입 후 POWER 복귀다. 반면 평가 정책은 매 패킷 다시 행동을 선택한다. 이 단발 label과 지속 재귀 정책의 상태·목적함수 차이를 해소했다고 주장하지 않는다.

R2-heldout은 학습에 M45 mount가 없는 OUT_OF_TRAINING_RANGE_MOUNT 평가를 포함한다. q 기반 모델과 gate는 기존 기준을 유지했으며 S2 GEOM은 채택하지 않았다.

OOF는 고정 v2 prior-label에서 HGB 단계 route-heldout이다. ROUTE_DEPENDENCIES.csv에 상위 P1의 검증 route 의존성을 기록했다. 전체 pipeline OOF나 독립 보정·coverage 보장은 없다. 중첩 창과 동일 RF의 bias/seed 및 fold 중복은 독립 정보가 아니다. ALL_OLD 기준 고유 eligible RF 5,851개, greedy 비겹침 10초 창 120개는 조건별 합계이며 독립 장면 수가 아니다.

기존 복도와 신규 C01–C03은 같은 복도 장면이며 O01–O03은 하나의 오피스 장면이다. 조건 수·seed 수를 독립 표본으로 쓰거나 p-value를 보고하지 않는다. 모든 실패와 불리한 효용을 보존하며, S0/S1/S2와 v2 NO-GO를 변경하지 않는다. S3 후 새 정책 변형이나 다음 단계를 시작하지 않는다.

## 주장하지 않는 것

독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증, margin의 coverage 보장, q의 인과적 독립 정보는 주장하지 않는다.
'''
 (a.out/'RESULTS_KO.md').write_text(report,encoding='utf-8')
 print(json.dumps(decision,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
