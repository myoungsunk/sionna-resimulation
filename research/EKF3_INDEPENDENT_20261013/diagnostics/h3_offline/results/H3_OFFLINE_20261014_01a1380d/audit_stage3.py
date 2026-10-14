"""Audit representation-only stage3; report matched local-valid samples."""
import csv,json,sys
from pathlib import Path
from collections import defaultdict
import numpy as np
import h3_offline as h
import run_full as r

base=h.ROOT/'STAGE3_01';out=base/'REVIEW_01';out.mkdir(exist_ok=False)
receipt=json.loads((base/'VALIDATION_RECEIPT.json').read_text())
path=base/'H3_MULTIMODAL_POSTERIOR.csv'
if receipt['status']!='PASS' or h.c.file_sha(path)!=receipt['output_sha256']:raise RuntimeError('Stage3 evidence gate failed')
p0=json.loads((h.ROOT/'GATES_02/VERIFIED_INPUTS.json').read_text())['p0'];cache,_=r.load_caches(p0)
groups=defaultdict(list);maxerr=0.;maxmass=0.;maxparity=0.
with path.open(encoding='utf-8',newline='') as f:
    for row in csv.DictReader(f):
        truth=cache[(row['case'],row['channel'])]['truth'][int(row['sample']),2]
        err=float(h.wrap(float(row['MAP_rad'])-truth)*h.RAD)
        maxerr=max(maxerr,abs(err-float(row['heading_error_deg'])))
        maxparity=max(maxparity,float(row['same_MAP_difference_rad']))
        modes=json.loads(row['modes_json']);maxmass=max(maxmass,abs(sum(m['mass'] for m in modes)-1))
        if row['local_sigma_deg']:
            sigma=float(row['local_sigma_deg'])
            if int(abs(err)<=1.95996398454*sigma)!=int(row['local95_contains_truth']):raise RuntimeError('Local coverage mismatch')
        elif row['local95_contains_truth'] or row['local95_width_deg']:raise RuntimeError('Invalid local Gaussian imputed')
        if abs(err)>90 and row['opposite_branch']!='1':raise RuntimeError('Branch score drift')
        groups[tuple(row[k] for k in ('case','route','condition','level','seed','channel'))].append(row)
if len(groups)!=168 or sum(map(len,groups.values()))!=148824 or max(maxerr,maxmass,maxparity)>1e-8:raise RuntimeError('Stage3 completeness or numeric gate failed')
metrics=[];summaries=defaultdict(list)
for key,rows in groups.items():
    valid=[row for row in rows if row['local_sigma_deg']]
    common=dict(zip(('case','route','condition','level','seed','channel'),key))
    for subset,rr in [('ALL_FRAMES',rows),('LOCAL_VALID_PAIRED',valid)]:
        if not rr:continue
        item=dict(common,subset=subset,n=len(rr),local_invalid_rate=1-len(valid)/len(rows),heading_RMSE_deg=float(np.sqrt(np.mean([float(q['heading_error_deg'])**2 for q in rr]))),opposite_branch_rate=float(np.mean([int(q['opposite_branch']) for q in rr])),hpd95_coverage=float(np.mean([int(q['hpd95_contains_truth']) for q in rr])),hpd95_mean_width_deg=float(np.mean([float(q['hpd_width_deg']) for q in rr])),hpd_disconnected_rate=float(np.mean([int(q['hpd_region_count'])>1 for q in rr])),meaningful_multimodal_rate=float(np.mean([int(q['mode_count'])>1 for q in rr])),truth_5deg_mean_mass=float(np.mean([float(q['truth_5deg_mass']) for q in rr])),local95_coverage=float(np.mean([int(q['local95_contains_truth']) for q in rr])) if subset=='LOCAL_VALID_PAIRED' else None,local95_mean_width_deg=float(np.mean([float(q['local95_width_deg']) for q in rr])) if subset=='LOCAL_VALID_PAIRED' else None)
        metrics.append(item);summaries[(key[2],key[3],key[5],subset)].append(item)
summary=[]
for key,items in summaries.items():
    result=dict(condition=key[0],level=int(key[1]),channel=key[2],subset=key[3],cells=len(items),n=sum(q['n'] for q in items))
    for name in ('local_invalid_rate','heading_RMSE_deg','opposite_branch_rate','hpd95_coverage','hpd95_mean_width_deg','hpd_disconnected_rate','meaningful_multimodal_rate','truth_5deg_mean_mass','local95_coverage','local95_mean_width_deg'):
        result['cell_mean_'+name]=None if items[0][name] is None else float(np.mean([q[name] for q in items]))
    summary.append(result)
r.save_csv(out/'CASE_SEED_METRICS.csv',metrics);r.save_csv(out/'CONDITION_SUMMARY.csv',summary)
audit=dict(status='PASS',scope='SELF_AUDIT_NOT_INDEPENDENT_CODE_ACCEPT',rows=148824,cells=168,max_saved_error_recalculation_difference=maxerr,max_MAP_stage2_parity_rad=maxparity,max_mode_mass_error=maxmass,input_sha256=h.c.file_sha(path),source_sha256=h.c.file_sha(Path(__file__)),output_sha256={p.name:h.c.file_sha(p) for p in out.glob('*.csv')},recursive_fusion='NOT_RUN_REQUIRES_STAGE4_GATE',scientific_PASS=False)
h.c.atomic_json(out/'RESULT_AUDIT.json',audit)
lines=['# H3 3단계 — 동일 posterior 표현 비교','','168개 조건·148,824시점의 수치 실행 및 저장 결과 자체 검산 PASS. 2단계와 MAP 점추정은 동일하다. 다봉 표현 자체가 분기 선택이나 Heading RMSE를 개선했다는 주장은 하지 않는다.','','표는 경로·seed 셀별 동일 가중 평균이며, 국소 Gaussian이 유효한 동일 시점만 짝지어 비교한다. 전체 시점 HPD 결과와 국소 근사 무효 비율은 별도 CSV에 보존한다.','','| 조건 | 채널 | 국소 95% 포함률 | 다봉 HPD 포함률 | 국소 폭 | HPD 총 폭 |','|---|---|---:|---:|---:|---:|']
for q in summary:
    if q['subset']=='LOCAL_VALID_PAIRED':lines.append('| %s L%d | %s | %.2f%% | %.2f%% | %.2f° | %.2f° |'%(q['condition'],q['level'],q['channel'],100*q['cell_mean_local95_coverage'],100*q['cell_mean_hpd95_coverage'],q['cell_mean_local95_mean_width_deg'],q['cell_mean_hpd95_mean_width_deg']))
lines+=['','분리된 HPD 구간과 모드별 확률질량을 원시 CSV에 기록했다. 신뢰영역이 넓어져 포함률이 높아지는 효과와 불확실성 표현의 효과를 함께 해석해야 한다. 동결된 RF 오차모델의 오지정이 있으면 전체 posterior 역시 정답을 충분히 포함하지 못할 수 있다. 시점을 독립 반복 실험으로 취급하지 않았다.','','RF 오차모델 학습·임계값 변경·재귀 모드 추적은 수행하지 않았다. 4단계 gate 전에는 재귀 융합을 실행하지 않는다. `scientific_PASS=false`.']
(out/'SUMMARY_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps(dict(audit=audit,summary=summary),ensure_ascii=False))
