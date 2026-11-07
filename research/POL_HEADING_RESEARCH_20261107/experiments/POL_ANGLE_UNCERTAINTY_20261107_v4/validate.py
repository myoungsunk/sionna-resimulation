import run_angle as m
import numpy as np,json,csv
rows=json.loads((m.BASE/'PROGRESS.json').read_text(encoding='utf-8'));assert len(rows)==33 and len({(r['channel'],r['level'],r['method']) for r in rows})==33
old=m.BASE.parent/'POL_HEADING_VAR_20261106_v3';comp=[];convergence=[]
for r in rows:
 d=np.load(m.BASE/f"outputs/{r['channel']}_{r['level']}_{r['method']}.npz");truth=m.e.data(r['channel'])['truth_for_offline_scoring_only'];sel=d['t_s']>=30
 assert sel.sum()==829 and np.isfinite(d['estimate']).all() and np.isfinite(d['covariance']).all() and np.linalg.eigvalsh(d['covariance']).min()>0
 actual=m.e.metrics(d['estimate'],d['covariance'],truth,d['t_s'])
 for k,v in actual.items():assert abs(v-r[k])<1e-10
 if 'heading_density' in d:assert np.max(abs(d['heading_density'].sum(axis=1)-1))<1e-6
for ch in ['full','los']:
 for lv in ['B0','L0','L1','L2']:
  new=next(r for r in rows if (r['channel'],r['level'],r['method'])==(ch,lv,'v4'))
  for arm in ['refined','shifted']+(['fine'] if ch=='full' and lv=='B0' else []):
   base=new if arm!='fine' else next(r for r in rows if (r['channel'],r['level'],r['method'])==(ch,lv,'refined'))
   r=next(r for r in rows if (r['channel'],r['level'],r['method'])==(ch,lv,arm))
   delta={k:abs(r[k]-base[k]) for k in ['heading_rmse_deg','xy_rmse_m']};delta.update({k:abs(r[k]/base[k]-1) for k in ['heading_sigma_rms_deg','xy_sigma_rms_m']})
   passed=delta['heading_rmse_deg']<=.02 and delta['xy_rmse_m']<=.005 and max(delta['heading_sigma_rms_deg'],delta['xy_sigma_rms_m'])<=.02
   convergence.append(dict(channel=ch,level=lv,test=arm,passed=passed,**delta))
  for label in ['S4','v3','v4']:
   path=old/f'outputs/{ch}_{lv}_v3.npz' if label=='v3' else m.BASE/f'outputs/{ch}_{lv}_{label}.npz'
   d=np.load(path);truth=m.e.data(ch)['truth_for_offline_scoring_only'];metrics=m.e.metrics(d['estimate'],d['covariance'],truth,d['t_s']);sel=d['t_s']>=30
   comp.append(dict(channel=ch,level=lv,model=label,**metrics,bias_sigma_rms_deg_s=float(np.rad2deg(np.sqrt(d['covariance'][sel,3,3].mean())))))
for name in ['INPUT_HASHES.json','EXTRA_HASHES.json']:
 assert all(m.sha(p)==h for p,h in json.loads((m.BASE/name).read_text(encoding='utf-8')).items())
with (m.BASE/'COMPARISON.csv').open('w',newline='',encoding='utf-8-sig') as f:
 w=csv.DictWriter(f,fieldnames=comp[0].keys());w.writeheader();w.writerows(comp)
passed=all(r['passed'] for r in convergence)
m.dump('CONVERGENCE.json',dict(status='PASS' if passed else 'FAIL',checks=convergence))
m.dump('VALIDATION.json',dict(status='PASS_SELF_CHECK' if passed else 'CONVERGENCE_FAIL',all_33_outputs_recomputed=True,inputs_unchanged=True,independent_audit=False,adoption=False))

text='# 직접 각도 불확실성 모델 v4: 구현·검증·기존 데이터 비교\n\n질문 ID POL-ANGLE-UNCERTAINTY-004. 구현·실행·자기검사이며 독립 감사 아님.\n\n## 모델 의미\n\n편파비 s와 예측 위치에서 LUT의 모든 조각별 선형 역해 zψ,m을 구한다. 하나의 해를 prior나 참값으로 선택하지 않고 동일 가중치의 원형 각도 관측 혼합으로 사용한다. 표준편차 [1,2,5,10,20,45]도 자체가 잠재 변수이며, 후보 확률을 정규화된 wrapped Gaussian 가능도로 갱신한다. R_s 및 그 배율은 새 관측 가능도에 없다. 원래 분산모드 prior와 5초 지속시간은 유지했다. 후보 폭은 결과 전 고정한 공학적 선택으로 독립 보정된 센서 정확도가 아니다.\n\n각도 후보는 추정 위치에 의존한다. 역함수 미분 dg/dxy=-h_xy/h_psi를 사용해 위치 불확실성과 상관을 조건부 계산에 포함한다. 역해 없음·연속된 해·역미분 불안정은 균등 가능도로 처리한다. 위치 의존 역해를 선형화하고 해에 같은 가중치를 주는 각도 pseudo-observation 모델이며, 원래 s 관측 likelihood를 정확히 변수변환한 모델 또는 독립적인 헤딩 센서가 아니다.\n\n각도/분산/주기 후보를 합산하고 모드 간 공분산을 포함한다. v3의 검출용 1도 평활화·1% prominence·1도 soft partition을 유지하므로 세부 근접모드 표현에는 해상도 제한이 있다. 지속적인 각도 편향과 시간상관은 별도 상태로 모델링하지 않았다.\n\n## 같은 데이터 비교\n\nR2 Loop / Anchor B / mount0 / seed0. LOS·Full × gyro bias [0,0.01,0.05,0.2]deg/s. 979시점 처리, t>=30의 829시점 평가. 초기 헤딩 표준편차5도, 거리 관측 없음. S4 causal mask 공유 matched 조건이며 독립적인 새 gate의 성능이 아니다. S4는 재실행 parity 확인, v3는 보존된 원본 상태에서 재집계했다.\n\n|환경|bias|모델|헤딩 RMSE °|XY RMSE m|헤딩 RMS σ °|XY RMS σ m|헤딩95% 포함률 %|pose95% 포함률 %|\n|---|---|---|---:|---:|---:|---:|---:|---:|\n'
for r in comp:
 text+='|'+'|'.join([r['channel'],r['level'],r['model']]+[f"{r[k]:.6f}" for k in ['heading_rmse_deg','xy_rmse_m','heading_sigma_rms_deg','xy_sigma_rms_m']]+[f"{100*r[k]:.2f}" for k in ['heading_coverage95','pose_coverage95']])+'|\n'
text+='\n헤딩 RMS σ=sqrt(mean(Pψψ)), XY RMS σ=sqrt(mean(Pxx+Pyy)). pose는 x,y,ψ 3자유도 영역이며 XY 단독 포함률이 아니다. 관측 각도 sigma와 최종 상태 sigma는 다르다.\n\n## 각도 불확실성의 실제 갱신\n\n|환경|bias|추정 관측각 RMS σ °|복수 posterior 모드 시점 수|원형95% HPD 포함률 %|\n|---|---|---:|---:|---:|\n'
angular=[]
for ch in ['full','los']:
 for lv in ['B0','L0','L1','L2']:
  d=np.load(m.BASE/f'outputs/{ch}_{lv}_v4.npz');sel=d['t_s']>=30;sig=float(np.sqrt(np.mean(d['angular_variance_prob'][sel]@(m.SIGMA_DEG**2))));modes=int((d['heading_modes'][sel]>1).sum());den=d['heading_density'][sel].astype(float);den/=den.sum(axis=1)[:,None];truth=m.e.data(ch)['truth_for_offline_scoring_only'][sel,2];idx=np.round((m.e.wrap(truth)+np.pi)/(2*np.pi)*len(d['theta_rad'])).astype(int)%len(d['theta_rad']);order=np.sort(den,axis=1)[:,::-1];j=(np.cumsum(order,axis=1)<.95).sum(axis=1);hpd=float(np.mean(den[np.arange(len(j)),idx]>=order[np.arange(len(j)),j]));angular.append(dict(channel=ch,level=lv,observation_angle_sigma_rms_deg=sig,multimodal_frames=modes,hpd95_coverage=hpd,mean_sigma_prob=d['angular_variance_prob'][sel].mean(axis=0).tolist()));text+=f'|{ch}|{lv}|{sig:.4f}|{modes}|{100*hpd:.2f}|\n'
m.dump('ANGULAR_UNCERTAINTY.json',angular)
text+='\n## 検証\n\n- 角度線形Gaussian解、R_sを100倍変更しても新観測計算不変、180度対称候補の質量保持、LUT逆解、位置微分の有限差分、解なしの無情報更新: PASS(TESTS.json)。\n- 8条件S4 parity、33出力の保存状態から指標再計算、確率質量・有限性・共分散正定値・入力ハッシュ不変を確認。\n- 格子検証: '+str(passed)+'. 全8条件0.25→0.125度および0.125度始点移動、Full B0は0.125→0.0625度。許容値0.02度/0.005m/両RMS sigma相対2%は変更なし。詳細CONVERGENCE.json。\n'
# Korean report wording.
text=text.replace('## 検証','## 검증').replace('角度線形Gaussian解、R_sを100倍変更しても新観測計算不変、180度対称候補の質量保持、LUT逆解、位置微分の有限差分、解なしの無情報更新','각도 선형 Gaussian 해석해, R_s 100배 변경 시 관측 계산 불변, 180도 후보 질량 보존, LUT 역해·위치 유한차분, 역해 없는 관측의 무정보 갱신').replace('8条件S4 parity、33出力の保存状態から指標再計算、確率質量・有限性・共分散正定値・入力ハッシュ不変を確認','8조건 S4 parity, 33개 저장 결과 재집계, 확률질량·유한성·공분산 양의 정부호·입력 해시 불변 확인').replace('格子検証','격자 검증').replace('全8条件0.25→0.125度および0.125度始点移動、Full B0は0.125→0.0625度。許容値0.02度/0.005m/両RMS sigma相対2%は変更なし。詳細','8조건 0.25→0.125도 및 시작점0.125도 이동, Full B0 추가0.0625도. 허용치0.02도/0.005m/두 RMS sigma 상대2% 유지. 상세 ')
text+='\n한 경로·seed의 결과이며 과신 해결·독립 환경 일반화·과학적 채택은 별도 판정이다. 이전 결과를 덮어쓰지 않았다.\n'
(m.BASE/'REPORT_KO.md').write_text(text,encoding='utf-8');print(json.dumps(dict(convergence_pass=passed,checks=convergence,comparison=comp,angular=angular)))
