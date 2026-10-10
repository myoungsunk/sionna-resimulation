from pathlib import Path
import json, re, hashlib
root=Path(__file__).resolve().parent
p=root/'INDEPENDENT_SCIENTIFIC_AUDIT_KO.md'
s=p.read_text(encoding='utf-8')
start=s.index('## 9. Claim boundary')
s=s[:start]+'''## 9. Claim boundary

### 현재 주장 가능한 것

- 고정된 한 복도·FFD·센서 가정과 좁은 초기 prior 아래에서, 많은 paired Monte Carlo 조건의 range+s heading RMSE가 odom+IMU보다 낮았다. Gyro-only 비교와 악화 조건도 함께 제시해야 한다.
- 지정 표본 pose에서 저장된 Method A/B 관측량 parity가 통과했다. 원본 trace 독립 검사에서는 strict G3 FAIL, relaxed delay eligibility PASS를 확인했다.
- 원본 CSV 통계와 선택한 H→observation→EKF 재생이 저장 요약을 뒷받침한다. Full RF regeneration을 완료한 것은 아니다.
- 실제 LUT가 ideal angular curve보다 유리하다는 개발 exploratory 결과가 있으며, angular/FFD correction의 중요성을 시사한다.

### 조건부로만 주장 가능한 것

- RF-derived s가 single-anchor tracking에 유용한 orientation 정보를 제공한다. Known polarization/mount, eligible geometry, model mismatch 및 informative initial prior를 명시해야 한다.
- Probe는 일부 불리한 조건의 sampled accuracy를 개선한다. 추가 정지시간·측정 수와 악화 조건을 함께 보고해야 한다.
- Anchor B와 route 확장은 기하 민감도를 보여준다. Dual-anchor fusion 또는 다양한 실제 복도의 일반성을 입증하지 않는다.

### 아직 주장하면 안 되는 것

- Original preregistered gates의 전체 PASS, 유효한 pre-S6 G3 또는 개별 물리 경로 동일성의 완전 검증.
- 검증된 full-channel heading measurement, globally unique heading/position observability 또는 신뢰할 수 있는 covariance/uncertainty.
- Probe·mount·anchor의 보편적 우월성, 다른 환경·material·antenna·robot으로의 일반성, 실제 TurtleBot/UWB hardware validity.

| Claim level | 현재 상태 |
|---|---|
| Level 1 — Code validity | PARTIAL: core Jacobian/chain 확인, GSF PSD 결함 및 G3 gate bug 확인 |
| Level 2 — Simulation validity | PARTIAL: controlled diagnostic 결과; LUT/parity/covariance 한계 |
| Level 3 — Research evidence | 제한된 local tracking 가설을 조건부 지지; scientific PASS 아님 |
| Level 4 — Generality | UNKNOWN / 미확립 |
| Level 5 — Hardware validity | UNKNOWN / 미검증 |

## 10. Minimum correction/validation plan

다음은 후속 작업 제안이다. 이번 감사에서는 실행하지 않았다. 새로운 기준은 결과를 보기 전에 고정하고 original FAIL 기록을 보존해야 한다.

| Priority / Purpose | Necessary change | Minimal validation / criterion | Required compute | Affected existing results |
|---|---|---|---|---|
| P0 — Claim/provenance 정정 | strict/relaxed/void/post-S6 판정 분리; actual z·병렬성·승인시점 불일치 명시 | 보고서와 receipt 대조; original FAIL 유지 | 문서/offline | 기존 숫자 재실행 불필요 |
| P0 — G3 evidence 완성 | 전체 set changes와 원인 기록; identity claim 범위 한정 | 기존 5,630 trace의 모든 변화·missing/status 검토; 설명 불가는 미검증 표시 | CPU, 새 RF 없음 | Label claim에 영향; H/S6 유지 |
| P0 — GSF 수학적 안정성 | PSD를 보존하는 collapse 방식 정정 | 제시한 반례 및 production component PSD 검사; 기준 tolerance를 먼저 고정 | CPU | 영향 있는 GSF runs만 replay 여부 결정 |
| P1 — Covariance/model validation | Gyro 재사용, range–s 및 시간 correlation, bias를 구분 | Matched synthetic sanity checks 및 frozen held-out NEES/coverage 기준; RMSE와 분리 | CPU, 기존 H | Filter 변경 시 해당 S6만 targeted rerun |
| P1 — Independent calibration | Held-out trajectory/geometry에서 noise/offset/R 고정 | Calibration/evaluation 독립성 hash·manifest 확인; original L1/L2 FAIL 유지 | CPU; 필요하면 제한된 RF | 수정 모델 결과는 기존 결과와 분리 |
| P1 — Anchor B coverage | Production 최대 dropped-amplitude positions에서 A/B 대조 | 기존 G2/G2′ 기준과 complete coverage 요구; FAIL이면 영향 범위 산정 | 제한된 native RF poses, 별도 후속 scope | B의 영향 있는 H/S6만 rerun 판단 |
| P1 — Observation/LUT | FP switch·multipath bias 및 sensitivity map 분해 | Original L1/L2 또는 사전에 고정한 새 모델 기준; held-out noisy error/correlation 검사 | CPU, 기존 H/LUT | s/range fusion 해석 또는 해당 모델 replay |
| P1 — Probe fairness | Drive-only/common-station/time-budget 지표 추가 | Negative/worst/median 동시 보고; elapsed 효율은 matched comparison | CPU, 기존 자료; 필요 시 새 사전등록 | P1 claim; RF 재생성이 항상 필요한 것은 아님 |
| P1 — Observability | Actual 6-state conditioning 및 broad initial roots 검사 | Range gauge, sensitivity FD, rank와 global ambiguity 구분 | CPU, LUT/H | Global localization claim을 별도로 검증 |
| P2 — Physical generality | Material/geometry/FFD/solver depth·seed hold-out | 먼저 고정한 convergence/error/robustness 기준 | Controlled RF, 후속 scope | Level 4 주장 전 필요 |
| P2 — Hardware | Dual-port CIR/timing/gain/noise/ranging capability 확인 | 실제 독립 captures·calibration·held-out validation | 실제 장비, 별도 승인 task | Level 5 주장 전 필요 |

새 consistency/hold-out acceptance threshold의 구체적 값은 후속 사전등록에서 정해야 한다. 이번 결과를 통과시키기 위해 임의의 값을 선택하지 않았다. Validation failure 또는 model change가 확인될 때 targeted rerun의 범위를 결정한다.

## 11. Final decision

**`BOUNDED_CORRECTION_OR_VALIDATION_REQUIRED`**.

실행 provenance, 원본 CSV 통계, raw G3, core Jacobian 및 selected H replay를 확인했으므로 증거 전체가 부족하거나 방법을 즉시 폐기해야 한다는 판정은 타당하지 않다. 반면 LUT FAIL, uncertainty FAIL, GSF PSD 결함, anchor-B coverage와 calibration/probe/initial-prior 한계가 있어 핵심 물리·수학·통계 타당성 전체를 PASS로 승격할 수 없다.

현재 결과는 **명시적 한계가 있는 diagnostic local-tracking simulation**으로 보존한다. 강한 논문 claim은 위의 보완 검증이 끝날 때까지 보류해야 한다. 감사는 여기서 종료한다. Source 수정, tuning, threshold 변경, 새 production campaign 또는 다음 실험 단계는 시작하지 않았다.

### 감사 산출물

- 이 보고서: `INDEPENDENT_SCIENTIFIC_AUDIT_KO.md`.
- `EVIDENCE_INDEX.md`: 실제 접근 가능한 코드·원본 evidence의 파일 링크.
- `REVISION_FREEZE.json`: 고정 revision.
- `provenance_validation.json` / `audit_provenance.py`: 원본 source/hash/manifest의 읽기 전용 대조.
- `independent_numerical_evidence.json`: 독립 계산 결과와 범위.
- `pytest.log`: 기존 85개 tests PASS.
- `selected_raw/`: 선택된 원본 H/LUT/frequency axis의 감사 사본.

코드 locator의 공통 root는 이 폴더의 `checkout/`이다. 독립 계산의 실행 출력은 감사 lane의 tool 기록에 보존되며 원자료 경로·계산식·검사 범위를 위에 기재했다. CSV 요약 검사 또는 saved-H replay를 RF 자체 재현으로 표현하지 않는다.
'''
# Space mixed Korean/English findings outside literal code and link targets.
def space_text(t):
    t=re.sub(r'(?<=[A-Za-z0-9])(?=[가-힣])',' ',t)
    t=re.sub(r'(?<=[가-힣])(?=[A-Za-z0-9])',' ',t)
    t=t.replace('문제 geometry','문제 geometry').replace('회피지만문제','회피지만 문제')
    return t
parts=re.split(r'(`[^`]*`|<[^>]*>)',s)
s=''.join(t if i%2 else space_text(t) for i,t in enumerate(parts))
s=s.replace('것이다.Tool','것이다. Tool').replace('않았다.Required','않았다. Required')
p.write_text(s,encoding='utf-8')
repo=root/'checkout'
base=repo/'results/DRIVE_SIM_20261007'
index=['# 감사 evidence index','', '모든 저장소 파일은 frozen HEAD 155bf5a63558a4fba9ff02cd0da159c7636fb8d8의 격리 checkout이다. Raw RF regeneration은 수행하지 않았다.','']
for folder,label in [('SNOWBALL_RUNS/01a11582/final_B_20261007T1017Z','R1 E1'),('SNOWBALL_ROUTE_RUNS/01a11669/final_20261007T140446Z','Route E1'),('SNOWBALL_ROUTE_RUNS/01a11669/g3_recheck_20261008','Corrected G3 E1')]:
    index+=['## '+label,'']
    for q in sorted((base/folder).rglob('*')):
        if q.is_file() and (q.suffix in ['.json','.csv','.md','.jsonl']):
            index.append('- ['+q.relative_to(base/folder).as_posix()+'](<'+q.as_posix()+'>)')
    index.append('')
index+=['## E2 audit outputs','']
for name in ['provenance_validation.json','provenance_validation.log','pytest.log','independent_numerical_evidence.json','REVISION_FREEZE.json']:
    index.append('- ['+name+'](<'+(root/name).as_posix()+'>)')
(root/'EVIDENCE_INDEX.md').write_text('\n'.join(index)+'\n',encoding='utf-8')
g3rows=[['R2A',925,1,0,5.109035716e-14,2.577283985e-13],['R2B',925,1,0,5.831573750e-14,2.432944745e-13],['R4A',547,3,0,9.383682083e-14,1.026671568e-13],['R4B',547,3,0,8.187995700e-14,1.052943760e-13],['R5A',1343,9,0,1.006418859e-13,1.030390639e-13],['R5B',1343,9,0,9.678208470e-14,1.154111447e-13]]
num={'head':'155bf5a63558a4fba9ff02cd0da159c7636fb8d8','G3_independent_raw':{'files':5630,'exit_code':0,'columns':['combination','stations','strict_unmatched','relaxed_unmatched','max_residual_s','min_gap_s'],'rows':g3rows,'not_verified':'individual ray identity and all set-change causes'},'statistics':{'csv_files':16,'R1_rows':18000,'route_rows':54000,'missing_failed':0,'seeds_per_condition':50,'method':'independent exact signed-rank subset sum, Holm, paired medians, 10000 bootstrap','max_metric_diff':3.55e-15,'max_CI_diff':7.99e-15,'verdict_mismatches':0},'selected_H_replay':{'condition':'R2 A mount0 drift0 SNR30 seed0,9EKF baselines','exit_code':0,'baselines_close_to_roundoff':7,'P0_heading_difference_deg':2.26957e-5,'max_scalar_metric_difference':1.96240e-4,'min_pose_covariance_eigenvalue':8.50687e-5,'bit_identical':False,'full_RF_regeneration':False},'Jacobians':{'process_FD_max':7.67e-10,'range_FD_max':8.66e-10,'actual_LUT_FD_max':6.231e-9},'GSF_PSD_counterexample':{'input_min_eigenvalue':.2,'output_min_eigenvalue':-.2452444204,'production_incidence':'UNKNOWN'},'observability':{'selected_3pose_model_windows':[100,300,700],'range_rank':[2,2,2],'range_s_rank':[3,3,3],'six_state_global_physical_proof':False},'tests':{'passed':85,'exit_code':0},'raw_tool_chunks':{'G3':'e7cc97','DFT':'f9a412','FFD':'ab770b'},'limitations':['No full RF regeneration','No complete paired A/B raw channel recomputation','No hardware validation','Tiny P0 replay discrepancy cause not established']}
(root/'independent_numerical_evidence.json').write_text(json.dumps(num,ensure_ascii=False,indent=2),encoding='utf-8')
check=json.loads((root/'AUDIT_COMPLETION_CHECK.json').read_text(encoding='utf-8'))
check.update(report_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),report_bytes=p.stat().st_size)
(root/'AUDIT_COMPLETION_CHECK.json').write_text(json.dumps(check,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(check,ensure_ascii=False))
