"""Read-only result validation and report generation; no estimator tuning."""
import experiment as e
import numpy as np,json,csv
from pathlib import Path

def table(rows,fields):
 headers=['환경','bias','방법']+[x[1] for x in fields]
 lines=['| '+' | '.join(headers)+' |','|'+'---|'*len(headers)]
 for r in rows:
  vals=[r['channel'],r['level'],r['method']]+[f"{r[k]*scale:.3f}" for k,_,scale in fields]
  lines.append('| '+' | '.join(vals)+' |')
 return '\n'.join(lines)

def main():
 rows=json.loads((e.BASE/'PROGRESS.json').read_text());matched=json.loads((e.BASE/'MATCHED_PROGRESS.json').read_text())
 assert len(rows)==40 and len(matched)==16
 keys=[(r['channel'],r['level'],r['method']) for r in rows+matched];assert len(set(keys))==56
 checks=[]
 for r in rows+matched:
  folder=e.BASE/('matched_gate' if 'matched' in r['method'] else 'outputs')
  d=np.load(folder/f"{r['channel']}_{r['level']}_{r['method']}.npz");truth=e.data(r['channel'])['truth_for_offline_scoring_only'];m=d['t_s']>=30
  err=d['estimate'][m,:3]-truth[m];ang=np.arctan2(np.sin(err[:,2]),np.cos(err[:,2]));heading=np.sqrt(np.mean(np.rad2deg(ang)**2));xy=np.sqrt(np.mean(np.linalg.norm(err[:,:2],axis=1)**2))
  assert abs(heading-r['heading_rmse_deg'])<1e-10 and abs(xy-r['xy_rmse_m'])<1e-12
  assert m.sum()==829 and np.isfinite(d['estimate']).all() and np.isfinite(d['covariance']).all()
  checks.append({'case':keys[len(checks)],'heading_delta':float(heading-r['heading_rmse_deg']),'xy_delta':float(xy-r['xy_rmse_m'])})
 # Verify original scorer parity in addition to state/covariance replay parity.
 old=list(csv.DictReader((e.OLD/'results/score/R2_BIAS_METRICS.csv').open(encoding='utf-8-sig')))
 for r in rows:
  if r['method']!='S4_original':continue
  ref=next(x for x in old if x['method']=='S4' and x['evaluation_mode']=='recursive' and x['rf_channel']==r['channel'] and x['level']==r['level'])
  for new,original in [('heading_rmse_deg','heading_rmse_deg'),('xy_rmse_m','pose_rmse_m'),('heading_sigma_rms_deg','heading_sigma_rms_deg'),('heading_nees','heading_nees_mean'),('pose_nees','pose_nees_mean'),('heading_coverage95','heading95_coverage'),('pose_coverage95','pose95_coverage')]:assert abs(r[new]-float(ref[original]))<1e-8
 # iid control equals basic because fitted total variance equals original RS.
 for ch in ['los','full']:
  for lv in ['B0','L0','L1','L2']:
   a=np.load(e.BASE/f'outputs/{ch}_{lv}_FGO_basic.npz');b=np.load(e.BASE/f'outputs/{ch}_{lv}_FGO_iid.npz');assert np.array_equal(a['estimate'],b['estimate']) and np.array_equal(a['covariance'],b['covariance'])
 hashes=json.loads((e.BASE/'INPUT_HASHES.json').read_text());assert all(e.sha(p)==v for p,v in hashes.items())
 selected=[];ratios=[]
 for ch in ['los','full']:
  for lv in ['B0','L0','L1','L2']:
   s=next(r for r in rows if r['channel']==ch and r['level']==lv and r['method']=='S4_original')
   basic=next(r for r in matched if r['channel']==ch and r['level']==lv and r['method']=='FGO_basic_matched')
   corr=next(r for r in matched if r['channel']==ch and r['level']==lv and r['method']=='FGO_corr_matched')
   selected += [s,basic,corr]
   ratios.append(dict(channel=ch,level=lv,heading_ratio=corr['heading_rmse_deg']/s['heading_rmse_deg'],xy_ratio=corr['xy_rmse_m']/s['xy_rmse_m'],heading_coverage_change=corr['heading_coverage95']-s['heading_coverage95']))
 full=[x for x in ratios if x['channel']=='full'];accuracy=all(r['heading_ratio']<=1.1 and r['xy_ratio']<=1.1 for r in full)
 e.dump('VALIDATION.json',dict(status='PASS_SELF_CHECK',rows=56,metric_recalculation_checks=checks,original_metric_parity=True,original_state_parity=json.loads((e.BASE/'PARITY.json').read_text()),input_source_hashes_unchanged=True,iid_control_identical_to_basic=True,ratios=ratios,full_accuracy_within_10percent=accuracy,independent_audit=False))
 fields=[('heading_rmse_deg','헤딩 RMSE °',1),('xy_rmse_m','XY RMSE m',1),('heading_sigma_rms_deg','헤딩 RMS σ °',1),('xy_sigma_rms_m','XY RMS σ m',1),('heading_coverage95','헤딩 95% 포함률 %',100),('pose_coverage95','pose 95% 포함률 %',100)]
 report='''# 편파 상관오차 FGO — 기존 S4 비교\n\n질문 ID: POL-FGO-CORR-001. 구현·실행·자기검사 완료. 독립 감사·과학적 채택은 미수행.\n\n## 비교 조건\n\n- R2 / Anchor B / mount 0 / seed 0, LOS·Full × B0·L0·L1·L2.\n- 원본 S4 소스의 센서 입력 생성·운동 모델·frozen LUT 재사용. 거리 관측 없음.\n- 979시점 모두 재귀 처리, t>=30초의 829시점 채점. 최신 상태만 비교하며 미래 관측 미사용.\n- Fixed lag: 10 intervals (2초). 시간창 선택에 대한 민감도·실시간 장치 검증 없음.\n- 첫 30초 Full 관측과 참 상태로 오프라인 잡음 식별, 이후 모든 채널·bias에서 파라미터 고정. 같은 궤적의 시간 분할이며 독립 환경 검증 아님.\n- 관측오차 총분산 0.0081 유지, 상관 성분 분산 0.00417836, 독립 성분 분산 0.00392164, 지속시간 1.72164초.\n- 원본의 영(0) bias process noise와 rank-deficient 운동잡음을 그대로 유지. 상태·제어잡음 변수로 결정론적 제약을 제거하는 reduced-coordinate nonlinear factor graph를 SciPy로 구현. GTSAM 사용 아님.\n- 주변화: 오래된 prior·관측·첫 transition만 제거. 전체 window posterior를 새 prior로 재사용하지 않음. 과거 prior는 1차 근사, 출력 공분산은 국소 Gauss–Newton 주변 공분산.\n\n## 공통 게이트 비교\n\nS4가 해당 시점까지의 정보로 결정한 원래 수용 mask를 FGO에도 적용했다. 이것은 **S4 관측 선택기 + FGO**의 조건부 비교이며, 독립적으로 게이팅하는 완성형 FGO가 아니다. 게이트 선택 불확실성은 공분산에 포함되지 않는다.\n\n'''+table(selected,fields)+'\n\n## 일관성 지표\n\n'+table(selected,[('heading_nees','heading NEES (기준 1)',1),('pose_nees','pose NEES (기준 3)',1),('seconds','전체 계산 초',1),('solver_failures','최적화 평가한도 도달 횟수',1)])
 report+='\n\n## 게이트 없는 비교 — 그대로 보존\n\n원래 S4 게이트를 없앤 대조군을 포함한다. 새 FGO의 효과와 게이트 제거 효과를 섞어 해석하지 않는다.\n\n'+table(rows,fields)
 report+='''\n\n## 검사와 해석 제한\n\n- 선형 KF 대조, 색잡음 Schur complement, 고정창 주변화/중복 계산 방지, 관측 누락+색잡음 선형 대조, 유한차분 Jacobian 검사 통과(TESTS.json, MATCHED_TESTS.json).\n- 8개 S4 조건의 상태·공분산·수용 mask 및 기존 CSV 지표 대조 통과(PARITY.json, VALIDATION.json).\n- 56개 결과 행의 RMSE를 저장된 상태로 재계산. 입력·소스 해시 불변 확인.\n- 최적화는 국소 LM, 종료는 scipy ftol/xtol/gtol 기준. 양의 종료코드가 엄격한 gradient stationarity나 전역 최적해를 보증하지 않음. 각 시점 status/nfev/optimality를 solver.json에 보존. 평가한도 도달 결과도 누락하지 않고 포함했으며 실패 0으로 처리하지 않음.\n- 모델은 zero-mean stationary AR(1) 근사. 식별 구간의 잔차 평균 0.01812는 제거하지 않았고 추가 상태·파라미터를 사후 튜닝하지 않음.\n- 헤딩과 c의 식별성, 다중 초기값·창 길이 민감도, 독립 RF 환경 반복 검증은 미완료. 공분산만 커졌다고 해결로 판정하지 않음.\n- Full에서 기존 S4 대비 두 RMSE 모두 10% 이내인 탐색적 정확도 조건: '''+str(accuracy)+'.\n\n실행 증거: CONTRACT.json, MATCHED_CONTRACT.json, INPUT_HASHES.json, RESULT.json, MATCHED_RESULT.json. 원본 입력·기존 S4 결과는 변경하지 않았다.\n'
 (e.BASE/'REPORT_KO.md').write_text(report,encoding='utf-8')
 with (e.BASE/'MAIN_COMPARISON.csv').open('w',encoding='utf-8-sig',newline='') as f:
  fields0=sorted(set().union(*(r.keys() for r in selected)));w=csv.DictWriter(f,fieldnames=fields0);w.writeheader();w.writerows(selected)
 print(json.dumps({'ratios':ratios,'full_accuracy_pass':accuracy,'matched_failures':sum(r['solver_failures'] for r in matched),'ungated_failures':sum(r['solver_failures'] for r in rows)}),flush=True)
if __name__=='__main__':main()
