"""Final evidence checks, event comparison and bounded interpretation."""
from pathlib import Path
import json,hashlib,numpy as np,pandas as pd
OUT=Path(__file__).resolve().parent;OLD=OUT.parent/'lut_observer_swap_20261102'
d=pd.read_csv(OUT/'ALL_SCORES_108.csv');usage=pd.read_csv(OUT/'GATE_VARIANCE_AND_CAP_USAGE.csv');rows=[];state_rows=[]
for _,r in usage.iterrows():
    z=dict(np.load(OUT/f'{r.case}_{r.bias}_{r.stage}_LUT_fixed.npz'));o=dict(np.load(OLD/f'{r.case}_{r.bias}_{r.stage}_LUT.npz'))
    delta=z['X']-o['X'];delta[:,2]=np.angle(np.exp(1j*delta[:,2]))
    state_rows.append(dict(case=r.case,bias=r.bias,stage=r.stage,max_xy_state_difference_cm=float(np.linalg.norm(delta[:,:2],axis=1).max()*100),max_wrapped_heading_state_difference_deg=float(abs(np.degrees(delta[:,2])).max()),max_bias_state_difference_rad_s=float(abs(delta[:,3]).max())))
    if r.case=='R5_aB_m0' and r.stage=='PROPOSED_MB_VAR':
        k=706;e=z['gt'][k,:3]-z['X'][k,:3];e[2]=np.angle(np.exp(1j*e[2]));p=z['PX'][k,:3,:3]
        rows.append(dict(bias=r.bias,Jxy_max=float(np.linalg.norm(z['J'][:,1,:2],axis=1).max()),sigma_y_141p2_cm=float(np.sqrt(z['PX'][k,1,1])*100),ey_141p2_cm=float(e[1]*100),nees3_141p2=float(e@np.linalg.solve(p,e))))
pd.DataFrame(rows).to_csv(OUT/'R5_MBVAR_POLE_EVENT.csv',index=False);pd.DataFrame(state_rows).to_csv(OUT/'WRAPPED_STATE_DIFFERENCES.csv',index=False)
q=d[(d.route=='R5')&(d.stage=='PROPOSED_MB_VAR')]
section='''## 結果の要点

'''.replace('結果の要点','확인된 결과')
section+='- 순환·지그재그는 각 구성의 네 bias 모두 수정 구간을 방문하지 않아 수정 전과 상태·공분산이 정확히 같다. 사행 경로 중 다중경로 일반 EKF B0/L0도 정확히 같다. 따라서 변경은 실제 수정 관측함수를 방문한 궤적에서 발생했다.\n'
section+='- 사행 경로 MB_VAR의 네 bias 전체 집계에서 heading RMSE는 0.5536→0.5815°, XY RMSE는 4.5655→4.7963 cm로 증가했다. pose NEES는 26.0794→3.1466, XY NEES는 5.0377→2.4634로 감소했다. pose 95% 포함률은 75.65%→94.43%였다. 수치상 공분산 과신이 완화됐지만 단일 seed의 시간 포함률을 정식 일관성 검정 통과로 해석하지 않는다.\n'
section+='- 사행 경로 LOS 일반 EKF는 heading 0.5385→0.4963°, XY 6.6139→3.4825 cm, pose NEES 14.3380→2.3846으로 감소했다. 다중경로 일반 EKF는 heading 2.5950→2.6475°, XY 20.1009→21.4877 cm, pose NEES 51.8784→56.5350으로 증가했다. 관측함수의 극점 결함 수정이 모든 오차 지표의 감소를 보장하지 않는다.\n'
section+='- L1 MB_VAR의 141.2 s에서 y 표준편차는 수정 전 0.1276 cm에서 수정 후 2.8912 cm가 되었고, 실제 y 오차는 3.6027→3.1619 cm였다. 해당 시점 pose NEES는 816.78→8.13으로 줄었다. 사행 경로 전체 최대 위치 Jacobian은 수정 전 36.31/m에서 수정 후 1.31/m로 줄었다.\n'
section+='- MB_VAR의 네 bias는 수정 전후 gate mask가 모두 같다. 다중경로 일반 EKF의 L1/L2는 각각 두 시점의 수용 여부가 달라졌으며 gate 규칙은 그대로다. 적용 분산의 상태 의존 변화는 CSV에 보존했다.\n\n'
section+='| 사행 MB_VAR bias | heading °: 전 / 후 / SourceFFD | XY cm: 전 / 후 / SourceFFD | pose NEES: 전 / 후 / SourceFFD |\n|---|---:|---:|---:|\n'
for b in ['B0','L0','L1','L2']:
    v=q[q.bias==b].set_index('observer')
    section+='| '+b+' | '+' | '.join(' / '.join(f'{v.loc[ob,key]:.4f}' for ob in ['LUT_original','LUT_fixed','SourceFFD']) for key in ['head_rmse','xy_rmse_cm','nees_pose'])+' |\n'
section+='\n'
p=OUT/'00 수정 전후 비교.md';text=p.read_text(encoding='utf-8');assert text.count('## 전체 조건별 수치')==1
text=text.replace('## 전체 조건별 수치',section+'## 전체 조건별 수치')
text+='\n보충: `GATE_VARIANCE_AND_CAP_USAGE.csv`의 원시 X 최대차에는 heading 래핑 경계의 2π 차이가 포함될 수 있다. 물리적인 상태 차이는 heading을 래핑해 계산한 `WRAPPED_STATE_DIFFERENCES.csv`를 사용한다.\n'
p.write_text(text,encoding='utf-8')
manager=json.loads((OUT/'MANAGED_FINISH.json').read_text(encoding='utf-8-sig'))['processes'][0]
assert manager['exit_code']==0 and manager['ref_count']==0 and manager['actual_process']['state']=='absent' and manager['actual_supervisor']['state']=='absent'
locked=json.loads((OUT/'CONTRACT.json').read_text())['input_hashes']
for f,h in locked.items():
    with Path(f).open('rb') as handle:assert hashlib.file_digest(handle,'sha256').hexdigest()==h,f
assert hashlib.sha256((OUT/'pole_regularized_lut.py').read_bytes()).hexdigest()==hashlib.sha256((OUT.parent/'lut_pole_fix_20261102_v2/pole_regularized_lut.py').read_bytes()).hexdigest()
par=pd.read_csv(OUT/'ORIGINAL_LUT_BASELINE_PARITY.csv')
assert len(par)==36 and par.gate_mismatch.sum()==0
qa=json.loads((OUT/'FIGURE_FORMAT_QA.json').read_text())
qa.append(dict(visual_review='All three rendered previews inspected; 3-series identity, route labels, B0/L0/L1/L2 order, units, common scales and text readable.'))
(OUT/'FIGURE_FORMAT_QA.json').write_text(json.dumps(qa,indent=2),encoding='utf-8')
(OUT/'FINAL_SELF_CHECK.json').write_text(json.dumps(dict(status='COMPLETED',input_hashes_unchanged=True,original_lut_parity_max=par[['X_max_abs','P_max_abs','R_max_abs']].max().to_dict(),manager_natural_exit=manager['termination'],manager_released=True,v2_model_identical=True,independent_audit=False,defect='Pole approach-direction artifact repaired and revalidated on requested frozen scene; original LUT and failed attempts preserved',adoption=False),indent=2),encoding='utf-8')
hashes={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in OUT.iterdir() if f.is_file() and f.name!='OUTPUT_HASHES.json'}
(OUT/'OUTPUT_HASHES.json').write_text(json.dumps(hashes,ensure_ascii=False,indent=2),encoding='utf-8')
print('FINAL_CHECKS_COMPLETE',len(hashes),'files')
