import run_heading as m
import json,csv,numpy as np
old=m.BASE.parent/'POL_HEADING_VAR_20261106_v1'
rows=json.loads((m.BASE/'PROGRESS.json').read_text());assert len(rows)==40 and len({(r['channel'],r['level'],r['method']) for r in rows})==40
before=list(csv.DictReader((old/'VERIFIED_COMPARISON.csv').open(encoding='utf-8-sig')))
for r in rows:
 d=np.load(m.BASE/f"outputs/{r['channel']}_{r['level']}_{r['method']}.npz");raw=m.e.data(r['channel']);sel=d['t_s']>=30
 metrics=m.e.metrics(d['estimate'],d['covariance'],raw['truth_for_offline_scoring_only'],d['t_s'])
 for k,v in metrics.items():assert abs(v-r[k])<1e-10,(k,v,r[k])
 assert sel.sum()==829 and np.isfinite(d['estimate']).all() and np.linalg.eigvalsh(d['covariance']).min()>0
 if 'heading_density' in d:
  den=d['heading_density'][sel].astype(float);den/=den.sum(axis=1)[:,None];theta=d['theta_rad'];truth=raw['truth_for_offline_scoring_only'][sel,2];idx=np.round((m.e.wrap(truth)+np.pi)/(2*np.pi)*len(theta)).astype(int)%len(theta)
  order=np.sort(den,axis=1)[:,::-1];j=(np.cumsum(order,axis=1)<.95).sum(axis=1);threshold=order[np.arange(len(j)),j]
  r['hpd95']=float(np.mean(den[np.arange(len(j)),idx]>=threshold))
  assert np.max(abs(d['heading_density'].sum(axis=1)-1))<1e-6
compare=[]
for ch in ['los','full']:
 for lv in ['B0','L0','L1','L2']:
  for label,source,method in [('S4',rows,'S4_original'),('v1',before,'HeadingVariable_matched'),('v2',rows,'HeadingVariable_matched')]:
   r=next(x for x in source if x['channel']==ch and x['level']==lv and x['method']==method)
   compare.append(dict(channel=ch,level=lv,version=label,**{k:float(r[k]) for k in ['heading_rmse_deg','xy_rmse_m','heading_sigma_rms_deg','xy_sigma_rms_m','heading_coverage95','pose_coverage95','heading_nees','pose_nees']},hpd95=float(r.get('hpd95',r.get('circular_hpd95_coverage') or 0))))
with (m.BASE/'THREE_WAY.csv').open('w',newline='',encoding='utf-8-sig') as f:
 w=csv.DictWriter(f,fieldnames=compare[0].keys());w.writeheader();w.writerows(compare)
for file in ['INPUT_HASHES.json','COMPARISON_INPUT_HASHES.json']:
 assert all(m.sha(p)==h for p,h in json.loads((m.BASE/file).read_text()).items())
grid=json.loads((m.BASE/'GRID_CHECK.json').read_text())
m.dump('VALIDATION.json',dict(status='PARTIAL_NUMERICAL_CONVERGENCE_FAIL' if grid['status']!='PASS' else 'PASS_SELF_CHECK',conditions=8,rows=40,metrics_recomputed=True,all_inputs_unchanged=True,grid=grid,independent_audit=False,adoption=False))
text='# 모드 보존·주기별 조건부 계산 수정 검증\n\nPOL-HEADING-VAR-002. 구현 및 재실행 완료. 결함 회귀 검사·재집계 검사 통과, 격자 수렴 검사 실패. 독립 감사 및 채택 아님.\n\n기존 v1 및 S4 원본 보존. 기존 R2 Loop / Anchor B / mount0 / seed0, 979 시점 처리, t>=30의 829 시점 평가. 같은 S4 수용 mask를 사용하는 matched 비교이며 독립적인 새 게이트 성능이 아니다.\n\n수정: interact는 거리 45도 기준을 제거하고 직전 posterior의 basin ID별로만 분산 모드를 혼합한다. measurement는 각 winding의 delta+2πj로 조건부 위치·bias와 likelihood를 각각 계산한 후 합산한다. 사전 9σ 밖 winding만 생략한다. 기존 분산 후보, prior, 지속시간, 운동·관측 모델, 격자는 유지했다.\n\n|환경|bias|모델|헤딩 RMSE °|XY RMSE m|헤딩 RMS σ °|XY RMS σ m|헤딩 95% 포함률 %|pose 95% 포함률 %|\n|---|---|---|---:|---:|---:|---:|---:|---:|\n'
for r in compare:
 text+='|'+ '|'.join([r['channel'],r['level'],r['version']]+[f"{r[k]:.6f}" for k in ['heading_rmse_deg','xy_rmse_m','heading_sigma_rms_deg','xy_sigma_rms_m']]+[f"{100*r[k]:.2f}" for k in ['heading_coverage95','pose_coverage95']])+'|\n'
text+='\n불확실성: 헤딩 RMS σ=sqrt(mean(Pψψ)), XY RMS σ=sqrt(mean(Pxx+Pyy)). pose 포함률은 x,y,ψ의 3자유도 NEES 95% 영역이며 XY 단독 포함률이 아니다. 세 방법의 추정 불확실성은 동일 정의.\n\n회귀 검사: 20도 떨어진 좁은 두 모드가 v1에서 하나로 병합되지만 v2에서 둘 유지. 넓은 상관 Gaussian + 선형 x 관측의 해석해에 대한 오차는 REGRESSION.json 참조. 기존 LUT·선형 Gaussian·대칭 모호성 검사 재통과. 8개 S4 상태/공분산/mask parity와 40개 결과 지표 재집계, 입력 해시 불변, 양의 정부호 검사. Full B0 matched의 격자 0.125도 refinement는 GRID_CHECK.json 참조.\n\n남은 한계: 작은 posterior 봉우리 prominence 1e-4 처리, 각 basin의 Gaussian 투영 및 조건부 선형화는 여전히 근사. 분산은 s-domain 후보이며 독립적인 각도 센서 분산이 아니다. 시간상관·지속적 평균편향 모델은 추가하지 않았다. 실제 경로는 알려진 초기 헤딩 5도 prior로 시작하므로 넓은 분포의 winding 수정이 크게 작동하지 않을 수 있다. 한 경로·seed 결과로 과신 해결 또는 일반화를 주장할 수 없다.\n'
(m.BASE/'REPORT_KO.md').write_text(text,encoding='utf-8')
print(json.dumps(compare))
