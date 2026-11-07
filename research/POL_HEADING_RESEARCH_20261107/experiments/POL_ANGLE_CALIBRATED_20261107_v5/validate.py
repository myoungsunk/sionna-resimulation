import model as m
import numpy as np,json,csv
rows=json.loads((m.BASE/'PROGRESS.json').read_text(encoding='utf-8'));assert len(rows)==32 and len({(r['channel'],r['level'],r['method']) for r in rows})==32
checks=[];details=[]
for r in rows:
 d=np.load(m.BASE/f"outputs/{r['channel']}_{r['level']}_{r['method']}.npz");truth=m.e.data(r['channel'])['truth_for_offline_scoring_only'];sel=d['t_s']>=40;assert sel.sum()==779 and r['n']==779
 err=d['estimate'][sel,:3]-truth[sel];err[:,2]=m.e.wrap(err[:,2]);hr=float(np.rad2deg(np.sqrt(np.mean(err[:,2]**2))));xy=float(np.sqrt(np.mean(np.sum(err[:,:2]**2,axis=1))));assert abs(hr-r['heading_rmse_deg'])<1e-10 and abs(xy-r['xy_rmse_m'])<1e-10
 actual=m.metrics(d['estimate'],d['covariance'],truth,d['t_s']);assert all(abs(actual[k]-r[k])<1e-10 for k in actual)
 assert np.isfinite(d['estimate']).all() and np.isfinite(d['covariance']).all() and np.linalg.eigvalsh(d['covariance']).min()>0
 if r['method'] in ['v5','precise']:
  assert np.max(abs(d['heading_density'].sum(axis=1)-1))<1e-6
  details.append(dict(channel=r['channel'],level=r['level'],method=r['method'],unconverged=int(d['mode_unconverged'].sum()),lost_mass=float(d['discarded_mass'].sum()),multimodal_evaluation_frames=int((d['modes'][sel]>1).sum())))
for ch in ['los','full']:
 for lv in ['B0','L0','L1','L2']:
  a=next(r for r in rows if (r['channel'],r['level'],r['method'])==(ch,lv,'v5'));b=next(r for r in rows if (r['channel'],r['level'],r['method'])==(ch,lv,'precise'))
  delta={k:abs(a[k]-b[k]) for k in ['heading_rmse_deg','xy_rmse_m']};delta.update({k:abs(a[k]/b[k]-1) for k in ['heading_sigma_rms_deg','xy_sigma_rms_m']});passed=delta['heading_rmse_deg']<=.02 and delta['xy_rmse_m']<=.005 and max(delta['heading_sigma_rms_deg'],delta['xy_sigma_rms_m'])<=.02;checks.append(dict(channel=ch,level=lv,passed=passed,**delta))
assert all(m.sha(p)==h for p,h in json.loads((m.BASE/'INPUT_HASHES.json').read_text(encoding='utf-8')).items())
cal=json.loads((m.BASE/'CALIBRATION.json').read_text(encoding='utf-8'));tests=json.loads((m.BASE/'TESTS.json').read_text(encoding='utf-8'));assert tests['calibration_suffix_poison_invariant'] and cal['diagnostics']['max_training_time']<30
selected=[r for r in rows if r['method']!='precise']
with (m.BASE/'COMPARISON.csv').open('w',newline='',encoding='utf-8-sig') as f:w=csv.DictWriter(f,fieldnames=selected[0].keys());w.writeheader();w.writerows(selected)
passed=all(r['passed'] for r in checks) and not any(r['unconverged'] for r in details)
m.dump('VALIDATION.json',dict(status='PASS_SELF_CHECK' if passed else 'UNRESOLVED_NUMERICS',all_32_rows_recomputed=True,calibration_suffix_poison_invariant=True,inputs_unchanged=True,convergence=checks,mode_checks=details,independent_audit=False,adoption=False,scientific_decision='REJECT_CURRENT_CALIBRATED_MODEL'))
# Offline diagnostic only: never fed back into the frozen calibration or estimator.
diagnostics=[]
for ch in ['los','full']:
 d=m.e.data(ch)
 for label,sel in [('calibration',d['t_s']<30),('evaluation',d['t_s']>=40)]:
  errs=[];indices=[];missing=0
  for k in np.flatnonzero(sel):
   truth=d['truth_for_offline_scoring_only'][k];rts=m.roots(np.r_[truth,0.],d['z_s'][k])
   if not rts:missing+=1;continue
   errs.append(min([float(m.e.wrap(a-truth[2])) for a,H,g in rts],key=abs));indices.append(k)
  err=np.array(errs);idx=np.array(indices);adj=np.diff(idx)==1;rho=float(np.corrcoef(err[:-1][adj],err[1:][adj])[0,1]) if adj.sum()>2 else 0.
  diagnostics.append(dict(channel=ch,split=label,supported=len(err),no_inverse=missing,nearest_branch_rmse_deg=float(np.rad2deg(np.sqrt(np.mean(err*err)))),nearest_branch_mean_deg=float(np.rad2deg(err.mean())),adjacent_error_correlation=rho))
m.dump('OFFLINE_ANGLE_ERROR_DIAGNOSTIC.json',dict(scope='oracle GT position and nearest GT branch, descriptive optimistic diagnostic ONLY; no online branch choice or fitting from evaluation',rows=diagnostics))
text='# 실제 각도 오차 보정 기반 불확실성 모델 v5\n\nPOL-ANGLE-CALIBRATED-005. 설계·구현·자기검사. 독립 감사 아님.\n\n## 분할과 보정\n\n0~30초 미만 보정,30~40초 미만 완충 및 상태 준비,40초 이후 평가(779시점). LOS와 Full 보정 관측을 각각150개씩 한 번만 사용했고 gyro bias별로 복제하지 않았다. 평가 자료는 이전 실험에서 이미 본 것이므로 블라인드 검증이나 독립 환경 검증이 아니다.\n\n보정은 참 위치에서 구한 모든 LUT 각도 역해를 혼합한 가능도를 참 헤딩에서 평가한다. 가까운 정답 가지 하나를 골라 학습하지 않는다. 런타임은 예측 위치에서 모든 후보를 유지한다. 역해 없는34개는 무정보 관측으로 처리되며 분산 학습에 정보를 주지 않는다. 지지 관측266개.\n\n학습 함수는 log sigma=a+b log((|ds/dpsi|+offset)/reference), b∈[-2,0]이며 균등 각도 이상 관측 확률도 같이 보정한다. 3개 초기값 중 보정 가능도가 가장 큰 결과만 선택했다. 평가 성능에 따른 재조정 없음. 학습 결과 b=0으로, 민감도 의존성이 선택되지 않고 sigma=5.440674도(분산 약29.60deg²), 이상 관측 확률0.7183%의 모델이 되었다. 역해가 존재하는 관측에 대한 조건부 이상 관측 확률이며34개 무역해 비율과 다르다. 시간에 따라 달라지는 sigma를 학습했다고 주장하지 않는다.\n\n기존 임의 후보1·2·5·10·20·45도와70% 사전확률/IMM을 제거했다. 보정 분산과 균등 이상 관측을 함께 도입했으므로 순수 분산 변경의 단독 인과효과는 아니다. s 분산을 조정하지 않는다. 각도 후보는 위치에 의존하며 역미분과 상태 공분산을 각도 관측식에 전달한다. 원형 Gaussian 해석적 갱신과 모드 간 공분산을 유지한다.\n\n## 동일 평가 구간 비교\n\nR2 Loop, Anchor B, mount0, seed0. 초기조건·운동모델·원본 S4 인과적 수용 mask 고정. 같은 입력으로 S4 재실행 parity 확인, v3 보존 상태 재집계. 원래 시뮬레이션 제어 입력 생성에는 원본 참 궤적을 사용하나 새 필터의 평가 중 관측에는 참값을 사용하지 않는다. 초기0~40초는 보정된 파라미터로 상태 준비하며 평가 점수에 포함하지 않는다.\n\n|환경|bias|방법|헤딩 RMSE °|XY RMSE m|헤딩 RMS σ °|XY RMS σ m|헤딩95% 포함률 %|pose95% 포함률 %|\n|---|---|---|---:|---:|---:|---:|---:|---:|\n'
for r in selected:
 text+='|'+'|'.join([r['channel'],r['level'],r['method']]+[f"{r[k]:.6f}" for k in ['heading_rmse_deg','xy_rmse_m','heading_sigma_rms_deg','xy_sigma_rms_m']]+[f"{100*r[k]:.2f}" for k in ['heading_coverage95','pose_coverage95']])+'|\n'
text+='\n헤딩 RMS σ=sqrt(mean(Pψψ)); XY RMS σ=sqrt(mean(Pxx+Pyy)). pose는 x,y,ψ의3자유도 영역이다. 관측 sigma5.44도와 최종 상태 sigma는 서로 다른 값이다.\n\n## 검증과 한계\n\n평가 구간의 관측·참값을 임의 값으로 바꿔도 보정 파라미터 불변. 선형 Gaussian 해석해·180도 후보 질량 보존 통과. 32개 저장 결과 재집계·입력 해시·공분산 양의 정부호 확인. 모드 허용오차1e-8/200회→1e-10/400회 검사는 VALIDATION.json 참조. 전체 수치 판정: '+str(passed)+'.\n\n보정 단계는 GT 위치, 실제 추정은 불확실한 위치라는 차이가 남는다. 각도 오차 평균편향·시간상관을 별도 상태로 모델링하지 않았다. 10초 완충은 독립성을 보장하지 않는다. 원형 역해·동일 가지 가중치·위치 선형화·모드 압축도 근사다. 보정 표준편차를 얻었다는 사실만으로 과신 해소나 일반화를 주장하지 않는다.\n\n## 오프라인 각도 오차 진단\n\n다음은 참 위치와 가장 가까운 참값 가지를 사용하는 낙관적 진단이며 실제 필터에 사용하지 않았다. 평가 자료로 재보정하지 않았다.\n\n|환경|구간|지지 관측|역해 없음|최근접 가지 RMSE °|평균 °|인접 오차 상관|\n|---|---|---:|---:|---:|---:|---:|\n'
for r in diagnostics:text+=f"|{r['channel']}|{r['split']}|{r['supported']}|{r['no_inverse']}|{r['nearest_branch_rmse_deg']:.4f}|{r['nearest_branch_mean_deg']:.4f}|{r['adjacent_error_correlation']:.4f}|\n"
text+='\n'+(m.BASE/'ASSESSMENT_KO.md').read_text(encoding='utf-8');(m.BASE/'REPORT_KO.md').write_text(text,encoding='utf-8');print(json.dumps(dict(numerical_pass=passed,comparison=selected,diagnostics=diagnostics)))
