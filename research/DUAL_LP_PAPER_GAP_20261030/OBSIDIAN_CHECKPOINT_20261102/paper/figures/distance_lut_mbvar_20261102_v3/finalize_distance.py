from pathlib import Path
import json,hashlib,datetime
import numpy as np,pandas as pd
OUT=Path(__file__).resolve().parent
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(n):return json.loads((OUT/n).read_text(encoding='utf-8-sig'))
contract=load('CONTRACT.json');checks=load('RESULT_CHECKS.json');finish=load('MANAGED_FINISH.json')
assert checks['new_runs']==checks['baseline_parity']==12 and checks['actual_fd_max']<2e-5
assert all(sha(p)==h for p,h in contract['input_hashes'].items())
assert len(finish['processes'])==2
assert all(p['exit_code']==0 and p['termination']=='natural' and p['ref_count']==0 and p['actual_process']['state']=='absent' and p['actual_supervisor']['state']=='absent' for p in finish['processes'])
scores=pd.read_csv(OUT/'ALL_SCORES_36.csv');rpool=pd.read_csv(OUT/'ROUTE_POOLED_SCORES_9.csv');pool=pd.read_csv(OUT/'POOLED_SCORES_3.csv')
rescore=[]
for p in sorted(OUT.glob('*_MB_VAR_DISTANCE_LUT.npz')):
    parts=p.stem.split('_');case='_'.join(parts[:3]);bias=parts[3]
    with np.load(p) as z:
        m=z['t']>=30-1e-9;e=z['gt'][:,:3]-z['X'][:,:3];e[:,2]=np.angle(np.exp(1j*e[:,2]));P=z['PX'][:,:3,:3]
        nees=np.sum(np.linalg.solve(np.linalg.cholesky(P),e[...,None])[...,0]**2,axis=1)
        v=dict(head_rmse=float(np.sqrt(np.mean(np.degrees(e[m,2])**2))),xy_rmse_cm=float(100*np.sqrt(np.mean(np.sum(e[m,:2]**2,axis=1)))),nees_pose=float(nees[m].mean()))
        row=scores[(scores.case==case)&(scores.bias==bias)&(scores.observer=='LUT_distance')].iloc[0]
        assert all(np.isclose(value,row[k],rtol=1e-10,atol=1e-10) for k,value in v.items())
        rescore.append(dict(case=case,bias=bias,**v))
assert len(rescore)==12
pd.DataFrame(rescore).to_csv(OUT/'FINAL_TRACE_RESCORE_12.csv',index=False)
same=pd.read_csv(OUT/'SAME_STATE_MODEL_CHECK.csv');effect=pd.read_csv(OUT/'GATE_R_EFFECTS.csv')
assert len(effect)==24 and effect.gate_mismatch.max()==0
reduction=[]
for route in ['R2','R4','R5']:
    sub=same[same.case.str.startswith(route)]
    old=float(np.sqrt(np.mean(sub.same_fixed_prior_s_RMS_fixed_source**2)));new=float(np.sqrt(np.mean(sub.same_fixed_prior_s_RMS_distance_source**2)))
    reduction.append(dict(route=route,old_rms=old,new_rms=new,reduction_pct=100*(1-new/old)))
pd.DataFrame(reduction).to_csv(OUT/'SAME_STATE_ROUTE_REDUCTION.csv',index=False)
analysis='''## 결과 해석

- 전체 heading RMSE는 기존 수정 LUT 0.968851°에서 거리 반영 LUT 0.959092°로 감소해 SourceFFD 0.959158°와 거의 같아졌다. 반면 XY RMSE는 6.411489 cm에서 6.439532 cm로 소폭 증가했다.
- 순환(R2): XY 6.079517→5.305665 cm, pose NEES 3.061901→2.713315로 감소했으나 heading은 0.983073→1.013570°로 증가했다.
- 지그재그(R4): heading은 1.477496→1.405889°로 감소했으나 XY는 9.251815→10.236353 cm, pose NEES는 14.816099→15.516617로 증가했다. 거리 반영만으로 이 경로의 공통 정합성 문제를 해소하지 못했다.
- 사행(R5): XY 4.796308→4.534800 cm, pose NEES 3.146627→2.463045로 감소해 SourceFFD의 XY 4.501395 cm, pose NEES 2.409071에 가까워졌다. heading은 0.581514→0.595757°로 소폭 증가했다.
- 전체 pose NEES는 5.692454→5.417322로 감소했지만 heading NEES와 XY NEES는 각각 증가했다. pose 명목 95% 영역의 포함 비율도 80.78%→80.73%로 거의 같았다. 따라서 pose NEES 감소만으로 필터 전체의 통계적 정합성이 개선되었다고 결론내리지 않는다.
- 세 방식 모두 12조건에서 gate 결정이 동일하다. gate 차이가 이번 결과를 설명하지 않는다. 상태 의존 분산 배열의 최대 차이는 기존 수정 LUT 대비 약 0.000021이다.

같은 기존 수정 LUT prior에서 관측함수만 평가하면, SourceFFD와의 편파 s 차이 RMS는 모든 조건에서 감소했다. 아래 집계는 전체 prior 시점 기준이며 성능 평가의 t≥30 s 집계와 구분한다.

| 경로 | 기존 수정 LUT와 SourceFFD의 차이 RMS | 거리 LUT와 SourceFFD의 차이 RMS | 감소율 |
|---|---:|---:|---:|
'''
for r in reduction:analysis+=f"| {r['route']} | {r['old_rms']:.6f} | {r['new_rms']:.6f} | {r['reduction_pct']:.2f}% |\n"
analysis+='''
즉 같은 상태의 함수값은 가까워졌지만, 성능이 모두 같은 방향으로 변하지는 않았다. 거리 반영 후에도 2° 스칼라 보간의 미분은 SourceFFD의 전계 보간·첫 경로 분기 미분과 다르고, 기존 MB 평균 보정도 그대로다. 이 결과는 거리 항을 추가한 개입의 효과까지 보여 주며, 남은 차이의 고유 인과 기여율이나 분산 재설계의 효과를 분리 입증하지 않는다.

'''
path=OUT/'00 거리 반영 LUT MB_VAR 비교.md';text=path.read_text(encoding='utf-8')
assert '## 결과 해석' not in text
path.write_text(text.replace('## 전체 12조건 합산',analysis+'## 전체 12조건 합산',1),encoding='utf-8')
qa=load('FIGURE_FORMAT_QA.json');assert len(qa)==3 and all(x['text_bounds_pass'] for x in qa)
final=dict(status='COMPLETED_SELF_CHECK_NOT_INDEPENDENT',conditions=12,three_observer_rows=36,final_trace_rescore=12,input_hashes_unchanged=True,all_gate_decisions_equal=True,visual_review='All three PNG previews inspected; labels, legends, common scales, bias order and hatches readable; vector PDF and 600dpi PNG preserved',figure_count=3,actual_prior_fd_samples=checks['actual_fd_samples'],actual_prior_fd_max=checks['actual_fd_max'],managed_processes_natural_exit_and_released=2,adopted=False,scope='Local verified frozen-input paired experiment only; no manuscript/GitHub mutation',finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
(OUT/'FINAL_SELF_CHECK.json').write_text(json.dumps(final,ensure_ascii=False,indent=2),encoding='utf-8')
manifest={p.name:sha(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='OUTPUT_HASHES.json'}
(OUT/'OUTPUT_HASHES.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(final,ensure_ascii=False));print(pd.DataFrame(reduction).to_string(index=False))
