"""Audit saved stage2 pairs, report matched-root and all-frame results separately."""
import csv,json,math,sys
from pathlib import Path
from collections import defaultdict
import numpy as np
import h3_offline as h
import run_full as r

base=h.ROOT/'STAGE2_01';out=base/(sys.argv[1] if len(sys.argv)>1 else 'REVIEW_01');out.mkdir(exist_ok=False)
receipt=json.loads((base/'VALIDATION_RECEIPT.json').read_text())
if receipt['status']!='PASS':raise RuntimeError('Stage2 incomplete; no effectiveness interpretation')
p0=json.loads((h.ROOT/'GATES_02/VERIFIED_INPUTS.json').read_text())['p0'];cases={case['id']:case for case in p0['cases']}
cache,_=r.load_caches(p0);lut=h.c.original_lut(p0)
groups=defaultdict(list);maxerror=0.;maxparity=0.;maxrootres=0.;maxTV=0.;maxMAPchange=0.;maxHPDchange=0.
with (base/'H3_INVERSE_VS_MAP.csv').open(encoding='utf-8',newline='') as f:
    for row in csv.DictReader(f):
        k=int(row['sample']);data=cache[(row['case'],row['channel'])];truth=float(data['truth'][k,2])
        if float(row['s_observed'])!=float(data['s'][k]) or int(row['pose_id'])!=int(data['pose_ids'][k]) or float(row['t_s'])!=float(data['t'][k]):raise RuntimeError('Saved pair/input alignment drift')
        for value,error in [('prior_heading_rad','prior_heading_error_deg'),('exact_inverse_rad','exact_inverse_error_deg'),('legacy_nearest_root_rad','legacy_nearest_root_error_deg'),('legacy_corrected_rad','legacy_corrected_error_deg'),('MAP_rad','MAP_error_deg'),('oracle_exact_root_rad','oracle_exact_root_error_deg')]:
            if row[value]:maxerror=max(maxerror,abs(float(h.wrap(float(row[value])-truth)*h.RAD)-float(row[error])))
        for value,flag in [('exact_inverse_error_deg','exact_inverse_opposite_branch'),('legacy_corrected_error_deg','legacy_opposite_branch'),('MAP_error_deg','MAP_opposite_branch')]:
            if row[value] and int(abs(float(row[value]))>90)!=int(row[flag]):raise RuntimeError('Branch label mismatch')
        maxparity=max(maxparity,float(row['legacy_parity_abs']));maxrootres=max(maxrootres,float(row['exact_inverse_residual']));maxTV=max(maxTV,float(row['angle_TV']));maxMAPchange=max(maxMAPchange,float(row['MAP_grid_change_deg']));maxHPDchange=max(maxHPDchange,float(row['internal_HPD_width_change_deg']))
        key=tuple(row[name] for name in ('case','route','condition','level','seed','channel'));groups[key].append(row)
if len(groups)!=168 or sum(map(len,groups.values()))!=148824:raise RuntimeError('Incomplete requested coverage')
if maxerror>1e-8 or maxparity>h.C['parity_absolute_tolerance'] or maxrootres>1e-10 or maxTV>h.C['posterior_TV_tolerance'] or maxMAPchange>h.C['MAP_angle_convergence_deg'] or maxHPDchange>h.C['HPD_width_convergence_deg']:raise RuntimeError('Numerical or scoring audit gate failed')
metrics=[];conditions=defaultdict(list)
for key,rows in groups.items():
    b=dict(zip(('case','route','condition','level','seed','channel'),key));present=np.array([bool(row['exact_inverse_rad']) for row in rows])
    for subset,indices in [('ALL_FRAMES',np.ones(len(rows),bool)),('EXACT_ROOT_PRESENT_PAIRED',present),('EXACT_ROOT_ABSENT',~present)]:
        for method,col in [('DR_PRIOR','prior_heading_error_deg'),('EXACT_INVERSE','exact_inverse_error_deg'),('LEGACY_NEAREST_ROOT','legacy_nearest_root_error_deg'),('LEGACY_CORRECTED','legacy_corrected_error_deg'),('MAP','MAP_error_deg'),('ORACLE_EXACT_ROOT','oracle_exact_root_error_deg')]:
            values=np.array([float(row[col]) for selected,row in zip(indices,rows) if selected and row[col]])
            if not len(values):continue
            item=dict(b,subset=subset,method=method,n=len(values),heading_RMSE_deg=float(np.sqrt(np.mean(values**2))),absolute_error_p95_deg=float(np.quantile(np.abs(values),.95)),opposite_branch_rate=float(np.mean(np.abs(values)>90)),oracle=method=='ORACLE_EXACT_ROOT')
            metrics.append(item);conditions[(key[2],key[3],key[5],subset,method)].append(item)
    status=dict(b,n=len(rows),exact_no_root_n=int((~present).sum()),exact_roots_disappeared_n=sum(row['roots_disappeared']=='True' for row in rows),legacy_applied_n=sum(row['legacy_status']=='applied' for row in rows),legacy_no_root_n=sum(row['legacy_status']=='no_root' for row in rows),legacy_low_slope_n=sum(row['legacy_status']=='low_slope' for row in rows),legacy_NIS_rejected_n=sum(row['legacy_status']=='rejected_NIS' for row in rows),MAP_vs_exact_opposite_n=sum(row['MAP_vs_exact_opposite_branch']=='1' for row in rows))
    metrics.append(dict(status,subset='COUNTS',method='STATUS'))
summary=[]
for key,items in conditions.items():
    summary.append(dict(condition=key[0],level=int(key[1]),channel=key[2],subset=key[3],method=key[4],cells=len(items),n=sum(item['n'] for item in items),cell_mean_heading_RMSE_deg=float(np.mean([item['heading_RMSE_deg'] for item in items])),cell_min_heading_RMSE_deg=min(item['heading_RMSE_deg'] for item in items),cell_max_heading_RMSE_deg=max(item['heading_RMSE_deg'] for item in items),cell_mean_p95_deg=float(np.mean([item['absolute_error_p95_deg'] for item in items])),cell_mean_opposite_branch_rate=float(np.mean([item['opposite_branch_rate'] for item in items]))))
r.save_csv(out/'CASE_SEED_METRICS.csv',metrics);r.save_csv(out/'CONDITION_SUMMARY.csv',summary)
# Show branch disagreements and vanishing-root events without selecting parameters.
examples=[]
for key,rows in groups.items():
    for kind,predicate in [('OPPOSITE_SELECTION',lambda row:row['MAP_vs_exact_opposite_branch']=='1'),('ROOT_DISAPPEARED',lambda row:row['roots_disappeared']=='True')]:
        candidates=[row for row in rows if predicate(row)]
        for row in candidates[:2]:examples.append(dict(event=kind,**row))
r.save_csv(out/'BRANCH_AND_NO_ROOT_EXAMPLES.csv',examples)
audit=dict(status='PASS',scope='SELF_AUDIT_NOT_INDEPENDENT_CODE_ACCEPT',cells=len(groups),rows=sum(map(len,groups.values())),max_saved_error_recalculation_difference=maxerror,max_legacy_parity_abs=maxparity,max_exact_root_residual=maxrootres,max_angle_TV=maxTV,max_MAP_grid_change_deg=maxMAPchange,max_internal_HPD_width_change_deg=maxHPDchange,source_sha256=h.c.file_sha(Path(__file__)),input_sha256=h.c.file_sha(base/'H3_INVERSE_VS_MAP.csv'),output_sha256={path.name:h.c.file_sha(path) for path in out.glob('*.csv')},scientific_PASS=False,stages_3_5='NOT_RUN')
h.c.atomic_json(out/'RESULT_AUDIT.json',audit)
text=['# H3 2단계 — 순수 역해·원본 inverse 보정·MAP','','## 실행 및 수치 판정','','168개 셀, 148,824개 시점에서 2단계 실행과 저장 결과 자체 검산이 PASS다. 7개 기하 조건 × 센서 조건 4개 × seed 3개 × LoS/Full 2개다. Range는 사용하지 않아 Full B_OLD/E1의 동일 Heading 결과를 중복 계산하지 않았다. 두 Range 입력과 기존 결과는 보존했다.','','정확한 역해는 고정 XY에서 LUT phi_RX 보간의 모든 구간을 조사해 구한 해다. 원본 0.5도 역해 탐색은 별도로 재현한다. 원본 inverse 필터는 기울기 거부·NIS gate·Kalman 보정 후 결과다. MAP은 같은 DR 위치·Heading prior와 동결 Rs=0.0081을 사용하고 원 전체를 조사하며 역해 방정식 만족을 강제하지 않는다. 원본 inverse gate는 유지한다. MAP에는 원본 inverse gate를 추가하지 않는다.','','정답은 오차 평가 및 명시된 oracle 해 선택에만 사용했다. 어떤 결과도 다음 DR prior로 피드백하지 않았다. RF 오차모델 학습, 공분산 조정, 3단계 posterior 표현 비교, Range 기하 보정 또는 재귀 융합은 이번에 실행하지 않았다.','','## 동일한 정확한 역해가 존재하는 시점의 비교','','표는 경로·seed 셀별 RMSE의 동일 가중 평균이다. 역해가 없는 시점은 별도 표본군으로 보고한다. 시점을 독립 반복 실험으로 취급하지 않는다.','','| 조건 | 채널 | 순수 정확한 역해 | 원본 보정 후 상태 | MAP |','|---|---|---:|---:|---:|']
lookup={(row['condition'],row['level'],row['channel'],row['subset'],row['method']):row for row in summary}
for condition,level in h.C['conditions']:
    for channel in ('los','full'):
        values=[lookup[(condition,level,channel,'EXACT_ROOT_PRESENT_PAIRED',method)]['cell_mean_heading_RMSE_deg'] for method in ('EXACT_INVERSE','LEGACY_CORRECTED','MAP')]
        label='noise_pair L1' if condition=='noise_pair' else 'gyro_bias L'+str(level)
        text.append('| %s | %s | %.4f° | %.4f° | %.4f° |'%(label,channel,*values))
counts=[item for item in metrics if item.get('subset')=='COUNTS']
text+=['','## 无해·gate 및 해석 경계'.replace('无해','무해'),'','- 정확한 역해 없음: %d / 148,824시점.'%sum(item['exact_no_root_n'] for item in counts),'- 원본 inverse 낮은 기울기 거부: %d시점; NIS 거부: %d시점.'%(sum(item['legacy_low_slope_n'] for item in counts),sum(item['legacy_NIS_rejected_n'] for item in counts)),'- MAP과 nearest-prior 정확한 역해가 90도 이상 다른 선택: %d시점.'%sum(item['MAP_vs_exact_opposite_n'] for item in counts),'','ALL_FRAMES 집계에서는 순수 역해의 무해 시점에 임의의 값을 대입하지 않는다. 그래서 방법마다 n이 다를 수 있다. 공정한 정확도 비교는 EXACT_ROOT_PRESENT_PAIRED를 먼저 보고, 무해에서는 MAP·원본 fallback·DR prior를 따로 비교한다. ORACLE_EXACT_ROOT는 온라인 방법이 아니라 진단용 기준이다.','','원본 보정 후 상태와 MAP의 차이는 해 선택뿐 아니라 gate·보정량의 차이도 포함한다. 순수 정확한 역해와 MAP을 비교해야 역해 강제 여부를 더 직접적으로 평가할 수 있다. 이 단계에서 pose 공분산 일관성, 다봉 신뢰영역 또는 재귀 성능 개선을 주장하지 않는다. `scientific_PASS=false`. 2단계 결과 검토에서 멈추며 3–5단계는 NOT_RUN이다.']
(out/'SUMMARY_KO.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
print(json.dumps(dict(audit=audit,table=[row for row in summary if row['subset']=='EXACT_ROOT_PRESENT_PAIRED' and row['method'] in ('EXACT_INVERSE','LEGACY_CORRECTED','MAP')]),indent=2))
