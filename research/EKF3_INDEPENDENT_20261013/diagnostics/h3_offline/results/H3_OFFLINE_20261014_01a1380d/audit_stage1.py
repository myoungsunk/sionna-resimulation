"""Recompute stage1 aggregates from saved raw CSV; descriptive units are cells."""
import csv,json,math,sys
from collections import defaultdict
from pathlib import Path
import numpy as np
import h3_offline as h
import run_full as r

base=h.ROOT/'STAGE1_01'
out=base/'REVIEW_02';out.mkdir(exist_ok=False)
receipt=json.loads((base/'VALIDATION_RECEIPT.json').read_text())
if receipt['status']!='PASS':raise RuntimeError('Stage1 did not pass')
keys=('case','route','condition','level','seed')
groups=defaultdict(list)
with (base/'H3_GEOMETRY_JACOBIAN_DECOMPOSITION.csv').open(encoding='utf-8',newline='') as f:
    for row in csv.DictReader(f):groups[tuple(row[k] for k in keys)].append(row)
with (base/'H3_GEOMETRY_CASE_SEED_METRICS.csv').open(encoding='utf-8',newline='') as f:
    metrics={tuple(row[k] for k in keys):row for row in csv.DictReader(f)}
if len(groups)!=84 or sum(map(len,groups.values()))!=74412 or set(groups)!=set(metrics):raise RuntimeError('Coverage mismatch')
maximum=0.;totals=defaultdict(list)
for key,rows in groups.items():
    a=np.array([[float(row[name+'_delta_s']) for name in ('theta','phi_TX','phi_RX')] for row in rows])
    linear=np.array([float(row['s_change_linear']) for row in rows]);nonlinear=np.array([float(row['s_change_nonlinear']) for row in rows])
    cross=np.array([[float(row[name]) for name in ('cross_0_1','cross_0_2','cross_1_2')] for row in rows])
    rawid=np.abs(np.sum(a*a,axis=1)+cross.sum(1)-linear**2).max()
    if rawid>1e-10:raise RuntimeError('Squared contribution identity failed')
    calc=dict(linear_delta_s_RMS=float(np.sqrt(np.mean(linear**2))),nonlinear_delta_s_RMS=float(np.sqrt(np.mean(nonlinear**2))),linear_remainder_RMS=float(np.sqrt(np.mean((nonlinear-linear)**2))))
    for j,name in enumerate(('theta','phi_TX','phi_RX')):
        calc[name+'_delta_s_mean']=float(a[:,j].mean());calc[name+'_delta_s_RMS']=float(np.sqrt(np.mean(a[:,j]**2)));calc[name+'_positive_fraction']=float(np.mean(a[:,j]>0))
    for j,name in enumerate(('cross_0_1','cross_0_2','cross_1_2')):calc[name+'_mean']=float(cross[:,j].mean())
    diff=max(abs(value-float(metrics[key][name])) for name,value in calc.items());maximum=max(maximum,diff)
    if diff>h.C['parity_absolute_tolerance']:raise RuntimeError('Raw/aggregate mismatch')
    totals[(key[2],key[3])].append(dict(n=len(rows),component_MS=float(np.mean(np.sum(a*a,axis=1))),linear_MS=float(np.mean(linear**2)),cross_MS=float(cross.sum(1).mean()),**calc))
summary=[]
for (condition,level),cells in totals.items():
    row=dict(condition=condition,level=int(level),cells=len(cells),timepoints=sum(cell['n'] for cell in cells),aggregation='equal_case_seed_cell_mean_descriptive_not_independent_RF')
    for name in ('theta_delta_s_RMS','phi_TX_delta_s_RMS','phi_RX_delta_s_RMS','linear_delta_s_RMS','nonlinear_delta_s_RMS','linear_remainder_RMS','cross_MS'):
        values=np.array([cell[name] for cell in cells]);row[name+'_cell_mean']=float(values.mean());row[name+'_cell_min']=float(values.min());row[name+'_cell_max']=float(values.max())
    components=np.mean([cell['component_MS'] for cell in cells]);summed=np.mean([cell['linear_MS'] for cell in cells])
    row['cross_term_MS_cell_mean']=float(np.mean([cell['cross_MS'] for cell in cells]));row['component_MS_cell_mean']=float(components);row['linear_MS_cell_mean']=float(summed);row['squared_cancellation_fraction']=float(1-summed/components)
    summary.append(row)
r.save_csv(out/'H3_GEOMETRY_CONDITION_SUMMARY.csv',summary)
audit=dict(status='PASS',scope='self_check_saved_raw_aggregates_and_identity',cells=len(groups),rows=sum(map(len,groups.values())),max_raw_aggregate_difference=maximum,tolerance=h.C['parity_absolute_tolerance'],weak_heading_rows=sum(row['weak_heading_sensitivity']=='True' for rows in groups.values() for row in rows),boundary_rows=sum(row['boundary']=='True' for rows in groups.values() for row in rows),clipping_rows=sum(row['clipping']=='True' for rows in groups.values() for row in rows),source_sha256={p.name:h.c.file_sha(p) for p in (h.ROOT/'run_stage1.py',Path(__file__))},input_csv_sha256={p.name:h.c.file_sha(p) for p in base.glob('*.csv')},output_sha256={p.name:h.c.file_sha(p) for p in out.glob('*.csv')},scientific_PASS=False,stages_2_5='NOT_RUN')
h.c.atomic_json(out/'RESULT_AUDIT.json',audit)
text=['# H3 1단계 — 위치 오차의 LUT 기하 전파 분해','','## 실제 실행 결과','','1단계 실행·수치 계약·원본 D0 prior 재현·원시 CSV 집계 재검산이 PASS다. 7개 RF 기하 조건 × 4개 센서 조건 × 3개 seed = 84셀, 평가 시점 74,412개를 계산했다. RF 채널 및 Range 모델은 이 단계의 기하 미분에 들어가지 않으므로 동일 기하 행을 LoS/Full·B_OLD/E1별로 중복 복제하지 않았다. RF 오차모델 학습은 호출하지 않았다.','','- Jacobian 수치미분 최대 오차: %.12g; 동결 허용치 1e-5.'%receipt['max_numeric_jac_error_smooth'],'- 분해항 합과 원본 Jacobian의 최대 차이: %.12g.'%receipt['max_chain_error'],'- D0 prior 252개 기준 셀 최대 차이: %.12g; 허용치 1e-8.'%receipt['prior_max_absolute_difference'],'- 저장된 원시 행과 집계 지표 재검산 최대 차이: %.12g.'%maximum,'- LUT 경계 행 %d개, clipping 행 %d개, 약한 Heading 민감도 행 %d개.'%(audit['boundary_rows'],audit['clipping_rows'],audit['weak_heading_rows']),'','경계·clipping은 원시 파일에 표시하고 smooth 수치미분 gate에서 분리했다. abs(H_psi)<1e-3/rad 시 국소 Heading 환산값을 비웠다. 나머지 환산값도 국소 보상량이며 실제 Heading RMSE나 정확한 역해 오차가 아니다. 큰 위치 오차에서는 비선형 잔차와 함께 해석해야 한다.','','## 조건별 분해','','아래 수치는 경로·장착조건·seed별 RMS의 동일 가중 평균이다. 시점 또는 sensor seed를 새로운 독립 RF 장면으로 취급하지 않는다. 항별 RMS는 합산하지 않는다.','','| 조건 | theta 항 RMS | phi_TX 항 RMS | phi_RX 항 RMS | 항 합 RMS | 실제 비선형 delta_s RMS | 선형화 잔여 RMS |','|---|---:|---:|---:|---:|---:|---:|']
for row in summary:
    label='무편향 noise_pair L1' if row['condition']=='noise_pair' else 'gyro_bias L'+str(row['level'])
    text.append('| %s | %.5f | %.5f | %.5f | %.5f | %.5f | %.5f |'%(label,row['theta_delta_s_RMS_cell_mean'],row['phi_TX_delta_s_RMS_cell_mean'],row['phi_RX_delta_s_RMS_cell_mean'],row['linear_delta_s_RMS_cell_mean'],row['nonlinear_delta_s_RMS_cell_mean'],row['linear_remainder_RMS_cell_mean']))
text.extend(['','단위는 signed power ratio s다. 비선형 변화는 Heading을 DR prior에 고정하고 DR 위치와 정답 위치의 전체 기하 모델을 비교한 값이다. 관측된 Full–LoS s 차이나 Multipath 잔차를 직접 분해한 결과가 아니다.','','## 결과 해석','','네 센서 조건 모두에서 phi_TX·phi_RX의 개별 RMS가 크지만 교차항 평균은 음수다. 국소 분해항 사이에 상쇄가 있으며, 각 항의 RMS를 합산하거나 독립 기여율로 해석하면 안 된다. phi_RX를 무시할 수 없지만 phi_TX도 유사한 규모여서 한 각도만 바꾸는 보정으로 전체 위치 기하 효과를 설명할 수 없다.','','국소 선형 합과 실제 비선형 변화의 차이도 작지 않다. 특히 큰 gyro bias에서는 선형화 잔여 RMS의 셀 평균이 약 0.162다. 이는 DR 위치에서 평가한 국소 미분을 유한한 위치 오차에 외삽한 한계를 보여준다. EKF 업데이트의 실패 원인이나 Heading 분기 오류를 이 결과만으로 확정하지 않는다. 그 질문은 다음 역해/MAP 단계에서 별도로 평가해야 한다.','','## 보존 및 중단 위치','','기존 코드·RF·LUT·센서·B_OLD/E1·기존 FAIL_CLOSED 기록을 수정하지 않았다. 출처·해시·명령은 INPUT_MANIFEST.json에, 실제 실행 상태는 VALIDATION_RECEIPT.json에 기록했다. 원본 checkout은 기준 커밋 fc8b6c1ca56540570fdbe5e4d228a0e23fdcc00b의 clean 상태다.','','독립 외부 감사는 수행하지 않았으며 자체 수치·집계 검산 결과다. `scientific_PASS=false`. 2단계 역해/MAP, 3단계 다봉 posterior, 4단계 Range 기하 비교 및 5단계 재귀 융합은 이번 실행에서 수행하지 않았다. 요청한 단계별 중단 규칙에 따라 1단계 결과 검토에서 멈춘다.'])
(out/'SUMMARY_KO.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
print(json.dumps(dict(audit=audit,summary=summary),indent=2))
