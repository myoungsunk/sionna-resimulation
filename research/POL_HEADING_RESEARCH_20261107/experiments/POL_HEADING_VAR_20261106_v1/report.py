import run_heading as m
import numpy as np,json,csv
def main():
 rows=json.loads((m.BASE/'PROGRESS.json').read_text());assert len(rows)==40 and len({(r['channel'],r['level'],r['method']) for r in rows})==40
 for r in rows:
  d=np.load(m.BASE/f"outputs/{r['channel']}_{r['level']}_{r['method']}.npz");raw=m.e.data(r['channel']);sel=d['t_s']>=30;truth=raw['truth_for_offline_scoring_only'];err=d['estimate'][sel,:3]-truth[sel];ang=np.arctan2(np.sin(err[:,2]),np.cos(err[:,2]));hr=float(np.sqrt(np.mean(np.rad2deg(ang)**2)));xy=float(np.sqrt(np.mean(np.sum(err[:,:2]**2,axis=1))))
  assert abs(hr-r['heading_rmse_deg'])<1e-10 and abs(xy-r['xy_rmse_m'])<1e-12 and sel.sum()==829
  assert np.isfinite(d['estimate']).all() and np.linalg.eigvalsh(d['covariance']).min()>0
  if 'heading_density' in d:
   den=d['heading_density'][sel].astype(float);den/=den.sum(axis=1)[:,None];theta=d['theta_rad'];idx=np.round((m.e.wrap(truth[sel,2])+np.pi)/(2*np.pi)*len(theta)).astype(int)%len(theta)
   order=np.sort(den,axis=1)[:,::-1];cs=np.cumsum(order,axis=1);j=(cs<.95).sum(axis=1);threshold=order[np.arange(len(j)),j];cover=den[np.arange(len(j)),idx]>=threshold
   r['circular_hpd95_coverage']=float(cover.mean());r['density_mass_max_error']=float(abs(d['heading_density'].sum(axis=1)-1).max())
   r['variance_scale_max_mean']=float((d['scale_prob']@(m.SCALES if 'Variable' in r['method'] else [1.])).max())
  else:r['circular_hpd95_coverage']=None
 hashes=json.loads((m.BASE/'INPUT_HASHES.json').read_text());assert all(m.sha(p)==h for p,h in hashes.items());grid=json.loads((m.BASE/'GRID_CHECK.json').read_text());assert grid['status']=='PASS'
 fields=sorted(set().union(*(r.keys() for r in rows)))
 with (m.BASE/'VERIFIED_COMPARISON.csv').open('w',newline='',encoding='utf-8-sig') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
 ratios=[]
 for ch in ['los','full']:
  for lv in ['B0','L0','L1','L2']:
   a=next(r for r in rows if r['channel']==ch and r['level']==lv and r['method']=='S4_original')
   for mode in ['all','matched']:
    b=next(r for r in rows if r['channel']==ch and r['level']==lv and r['method']=='HeadingVariable_'+mode)
    ratios.append(dict(channel=ch,level=lv,mode=mode,heading_ratio=b['heading_rmse_deg']/a['heading_rmse_deg'],xy_ratio=b['xy_rmse_m']/a['xy_rmse_m']))
 passed=all(x['heading_ratio']<=1.1 and x['xy_ratio']<=1.1 for x in ratios if x['channel']=='full' and x['mode']=='matched')
 m.dump('VALIDATION.json',dict(status='PASS_SELF_CHECK',rows=40,all_metrics_recomputed=True,inputs_unchanged=True,grid_check=grid,ratios=ratios,matched_full_accuracy_target_met=passed,adoption=False,independent_audit=False))
 def table(selected):
  s='|환경|bias|방법|헤딩 RMSE °|XY RMSE m|헤딩 RMS σ °|XY RMS σ m|헤딩 95% 포함률 %|원형 HPD 95% 포함률 %|평균 분산배율|\n|---|---|---|---:|---:|---:|---:|---:|---:|---:|\n'
  for r in selected:
   vals=[r['channel'],r['level'],r['method']]+[f'{r[k]:.3f}' for k in ['heading_rmse_deg','xy_rmse_m','heading_sigma_rms_deg','xy_sigma_rms_m']]+[f"{100*r['heading_coverage95']:.1f}",'-' if r['circular_hpd95_coverage'] is None else f"{100*r['circular_hpd95_coverage']:.1f}",f"{r.get('mean_variance_scale',1):.3f}"]
   s+='|'+'|'.join(vals)+'|\n'
  return s
 report='''# 편파 헤딩 + 가변 불확실성: 기존 데이터 비교\n\n질문 ID POL-HEADING-VAR-001. 구현·실행·자기검사 완료, 독립 감사·과학적 채택 미수행.\n\n## 구현\n\n- 원본 S4의 운동 입력 생성·상태 초기값·공분산·frozen LUT 재사용. 거리 관측 미사용. R2 Anchor B mount0 seed0, 979시점 인과 처리, t>=30의 829시점 평가.\n- 추정기는 EKF/FGO가 아닌 **원형 헤딩 격자 + 가우시안 혼합 + 분산모드 IMM**이다. 기존 s의 정보는 frozen forward model을 통해 heading likelihood로 변환한다. 새로운 독립 헤딩 센서를 가정하거나 가까운 역함수 해 하나만 고르지 않는다.\n- 360도 0.25도 간격의 헤딩 후보. 각 heading에 조건부인 위치·bias 분포를 사용하고 관측 likelihood에서 위치 불확실성을 선형 근사로 적분. 같은 prior를 두 번 독립 정보로 곱하지 않는다.\n- 분산 후보: Rs*[1,2,4,8,16,32]. 후보별 확률을 Gaussian likelihood의 정규화 항까지 포함해 갱신. IMM 지속시간 5초, prior [0.70,0.15,0.075,0.04,0.025,0.01]. 결과 전 고정한 공학적 선택이며 참값 학습/평가 후 튜닝 없음.\n- 각도 분포의 복수 봉우리를 유지하고 모드 간·분산 간 평균 차이도 공분산에 반영. 미세 봉우리 상대 prominence 1e-4 이하는 moment merge, IMM에서 45도 이내 basin은 혼합 근사. 확률질량을 특정 참값 가지로 선택하지 않음.\n- 모든 조건에서 초기 heading 표준편차 5도를 알고 시작한다. 180도 전역 모호성이 실제 자료에서 해결되었다는 주장이 아니다. 대칭 synthetic case에서 두 후보 50:50 유지 검사로 기능만 확인.\n- 이 모델은 가변 관측분산이며 시간상관이나 지속적 평균편향을 직접 보정하는 모델이 아니다.\n\n## 기존 S4와 동일 관측 수용 시점\n\nmatched는 원래 causal S4 selector를 공유한 조건부 비교이다. 독립적인 새 게이트가 아니다. S4의 위치/heading 추정치를 새 필터에 입력하지 않으며 수용 여부만 공유한다.\n\n'''+table([r for r in rows if r['method'] in ['S4_original','HeadingFixed_matched','HeadingVariable_matched']])
 report+='\n## 게이트 없이 모든 관측 사용\n\n고정 불확실성 대조군을 함께 제시해 가변 불확실성의 효과를 분리한다.\n\n'+table([r for r in rows if r['method'] in ['S4_original','HeadingFixed_all','HeadingVariable_all']])
 report+='''\n## 검증\n\n- 200개 입력에서 vector LUT 값은 원본과 정확히 동일, Jacobian 최대 차이 3.56e-15.\n- 선형 관측의 Gaussian 평균·공분산 해와 격자 적분 결과 최대 차이 1.67e-16.\n- 180도 대칭 모호성의 두 후보 질량 0.5 유지, 모드 간 공분산 확인. 잔차 0에서 log variance 정규화가 작은 분산을 선호하는지 검사.\n- 8개 S4 조건의 상태·공분산·수용 mask parity, 저장 상태로 40개 지표 행의 RMSE 재계산, 입력 해시 불변·유한성·공분산 양의 정부호 확인.\n- Full B0 matched 가변 모델을 0.125도 격자로 다시 계산한 numerical refinement 통과. 다른 조건의 전수 grid convergence 검증은 아님.\n- 원형 HPD 포함률은 전체 다중모드 격자의 95% 질량집합으로 계산(참 헤딩에 가장 가까운 격자점). Gaussian 95% 포함률과 구분.\n- 상대 분산 후보, 지속시간, 혼합 근사 및 LUT 물리 정확성에 대한 독립 검증 없음. 한 경로·seed에서 과신 해결/일반화를 주장하지 않는다.\n\n## 판정\n\n공통 gate Full 전 bias에서 두 RMSE 모두 S4 대비 10% 이내라는 탐색적 정확도 조건: '''+str(passed)+'. 불확실성 확대와 정확도·일관성 개선을 분리해서 판단한다.\n\n파일: CONTRACT.json / TESTS.json / PARITY.json / GRID_CHECK.json / VALIDATION.json / VERIFIED_COMPARISON.csv / outputs/*.npz. 원본 자료는 보존했다.\n'
 (m.BASE/'REPORT_KO.md').write_text(report,encoding='utf-8');print(json.dumps({'target_met':passed,'ratios':ratios}))
if __name__=='__main__':main()
