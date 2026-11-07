import run_heading as m
import numpy as np,json,csv
rows=json.loads((m.BASE/'PROGRESS.json').read_text(encoding='utf-8'));assert len(rows)==33 and len({(r['channel'],r['level'],r['method']) for r in rows})==33
old=m.BASE.parent/'POL_HEADING_VAR_20261106_v2';comp=[];convergence=[]
for r in rows:
 d=np.load(m.BASE/f"outputs/{r['channel']}_{r['level']}_{r['method']}.npz");truth=m.e.data(r['channel'])['truth_for_offline_scoring_only'];sel=d['t_s']>=30
 assert sel.sum()==829 and np.isfinite(d['estimate']).all() and np.isfinite(d['covariance']).all() and np.linalg.eigvalsh(d['covariance']).min()>0
 actual=m.e.metrics(d['estimate'],d['covariance'],truth,d['t_s'])
 for k,v in actual.items():assert abs(v-r[k])<1e-10
 if 'heading_density' in d:assert np.max(abs(d['heading_density'].sum(axis=1)-1))<1e-6
for ch in ['full','los']:
 for lv in ['B0','L0','L1','L2']:
  new=next(r for r in rows if (r['channel'],r['level'],r['method'])==(ch,lv,'v3'))
  for arm in ['refined','shifted']+(['fine'] if ch=='full' and lv=='B0' else []):
   base=new if arm!='fine' else next(r for r in rows if (r['channel'],r['level'],r['method'])==(ch,lv,'refined'))
   r=next(r for r in rows if (r['channel'],r['level'],r['method'])==(ch,lv,arm))
   delta={k:abs(r[k]-base[k]) for k in ['heading_rmse_deg','xy_rmse_m']};delta.update({k:abs(r[k]/base[k]-1) for k in ['heading_sigma_rms_deg','xy_sigma_rms_m']})
   passed=delta['heading_rmse_deg']<=.02 and delta['xy_rmse_m']<=.005 and max(delta['heading_sigma_rms_deg'],delta['xy_sigma_rms_m'])<=.02
   convergence.append(dict(channel=ch,level=lv,test=arm,passed=passed,**delta))
  for label in ['S4','v2','v3']:
   path=old/f'outputs/{ch}_{lv}_HeadingVariable_matched.npz' if label=='v2' else m.BASE/f'outputs/{ch}_{lv}_{label}.npz'
   d=np.load(path);truth=m.e.data(ch)['truth_for_offline_scoring_only'];metrics=m.e.metrics(d['estimate'],d['covariance'],truth,d['t_s']);sel=d['t_s']>=30
   comp.append(dict(channel=ch,level=lv,model=label,**metrics,bias_sigma_rms_deg_s=float(np.rad2deg(np.sqrt(d['covariance'][sel,3,3].mean())))))
for name in ['INPUT_HASHES.json','EXTRA_HASHES.json']:
 assert all(m.sha(p)==h for p,h in json.loads((m.BASE/name).read_text(encoding='utf-8')).items())
with (m.BASE/'COMPARISON.csv').open('w',newline='',encoding='utf-8-sig') as f:
 w=csv.DictWriter(f,fieldnames=comp[0].keys());w.writeheader();w.writerows(comp)
passed=all(r['passed'] for r in convergence)
m.dump('CONVERGENCE.json',dict(status='PASS' if passed else 'FAIL',checks=convergence))
m.dump('VALIDATION.json',dict(status='PASS_SELF_CHECK' if passed else 'CONVERGENCE_FAIL',all_33_outputs_recomputed=True,inputs_unchanged=True,independent_audit=False,adoption=False))
text='# 모드 검출·분포 근사 격자 민감성 수정 결과\n\nPOL-HEADING-VAR-003. IMPLEMENTER 자기검사, 독립 감사 아님. 원본 v2 및 S4 보존.\n\n## 변경과 통제\n\n검출에만 원형 Gaussian 평활화 sigma 1도, 상대 prominence 1%, 봉우리 위치 이차 보간을 적용했다. 최근접 봉우리의 딱딱한 분할 대신 각도 거리 기반 softmax(온도 1도)로 전체 확률질량을 연속 분할한다. 실제 관측 likelihood와 posterior density는 평활화하지 않는다. 이 값은 실행 전 고정했으며 수렴 허용치를 변경하지 않았다. 1도 이하 세부 모드의 독립 표현은 보장하지 않는다.\n\n기존 R2 Loop / Anchor B / mount0 / seed0, LOS·Full × gyro bias [0,0.01,0.05,0.2] deg/s. 979시점 처리, t>=30의 829시점 평가. S4 causal mask 공유 matched 비교. 거리 관측 없음. 분산 후보·IMM 지속시간·LUT·초기조건 동일. 수정 전은 직전 v2.\n\n## 동일 정의 비교\n\n|환경|bias|모델|헤딩 RMSE °|XY RMSE m|헤딩 RMS σ °|XY RMS σ m|헤딩95% 포함률 %|pose95% 포함률 %|\n|---|---|---|---:|---:|---:|---:|---:|---:|\n'
for r in comp:
 text+='|'+'|'.join([r['channel'],r['level'],r['model']]+[f"{r[k]:.6f}" for k in ['heading_rmse_deg','xy_rmse_m','heading_sigma_rms_deg','xy_sigma_rms_m']]+[f"{100*r[k]:.2f}" for k in ['heading_coverage95','pose_coverage95']])+'|\n'
text+='\n헤딩 RMS σ=sqrt(mean(Pψψ)), XY RMS σ=sqrt(mean(Pxx+Pyy)). pose 영역은 x,y,ψ 3자유도 NEES 기준이며 XY 단독 영역이 아니다. 시간상관을 가진 한 경로의 경험적 포함률이다. 바이어스 RMS σ와 NEES는 COMPARISON.csv에 포함했다.\n\n## 수렴 검증\n\n판정: '+str(passed)+'. 전체8조건에서 0.25→0.125도와 0.25도 격자 시작점 0.125도 이동을 검사했다. Full B0는 0.125→0.0625도도 검사했다. 허용 차이: 헤딩 RMSE 0.02도, XY RMSE 0.005m, 두 RMS σ 상대변화 2%.\n\n|환경|bias|검사|헤딩 차이 °|XY 차이 m|헤딩 σ 변화 %|XY σ 변화 %|통과|\n|---|---|---|---:|---:|---:|---:|---|\n'
for r in convergence:
 text+='|'+'|'.join([r['channel'],r['level'],r['test'],f"{r['heading_rmse_deg']:.6f}",f"{r['xy_rmse_m']:.6f}",f"{100*r['heading_sigma_rms_deg']:.4f}",f"{100*r['xy_sigma_rms_m']:.4f}",str(r['passed'])])+'|\n'
text+='\n검증: S4 8조건 상태·공분산·수용 mask parity, 33출력 재집계·유한성·공분산 양의 정부호·확률질량, 원본 해시 불변. 선형 Gaussian 해석해 및 넓은 주기별 조건부 해석해, 근접 모드 보존, ±180도 경계를 넘는 두 모드의 격자/위상 불변성 검사 통과.\n\n잔여 한계: 조건부 위치 선형화, Gaussian 분포 근사, 정해진 모드 검출 해상도, 가변 s-domain 분산, 시간상관·지속 편향 미모델링은 남는다. 수치 수렴과 과신 해결·물리 모델 타당성·일반화는 별도 판정이다.\n'
(m.BASE/'REPORT_KO.md').write_text(text,encoding='utf-8');print(json.dumps(dict(convergence_pass=passed,checks=convergence,comparison=comp)))
