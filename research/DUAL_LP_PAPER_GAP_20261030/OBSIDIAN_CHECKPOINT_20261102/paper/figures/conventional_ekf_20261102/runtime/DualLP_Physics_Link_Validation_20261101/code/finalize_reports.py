"""Create evidence-backed comparison and Korean handoff from completed computations."""
from __future__ import annotations
import json,hashlib,sys,platform,datetime
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads((ROOT/p).read_text())
def write(p,x):(ROOT/p).write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 r=read('results/REPLAY_QA.json');p=read('results/PHYSICS_QA.json');s=read('results/SHADOW_QA.json');c=read('results/COMPARISON_QA.json');m=read('results/MEAN_LINEAGE_QA.json');t=read('results/TRACE_CONTRACT_QA.json')
 d=pd.read_csv(ROOT/'results/tables/LEGACY_PRESERVATION_12.csv');v=pd.read_csv(ROOT/'results/tables/MB_LOOKUP_VS_CONSTANT_24.csv');sh=pd.read_csv(ROOT/'results/tables/SAME_PRIOR_VARIANCE_CONTRASTS_12.csv')
 assert r['historical_csv']['all_pass'] and r['control_trace']['all_pass'] and p['all_raw_observers_pass'] and p['stable_derivative_failures']==0 and p['invariance_failures']==0 and s['all_gain_identity_pass'] and c['score_and_update_and_masks_all_pass'] and m['archived_prediction_replay']=='PASS' and t['all_pass']
 wins={g:dict(lookup_better_both=int(((x.lookup_minus_constant_heading<0)&(x.lookup_minus_constant_xy_cm<0)).sum()),constant_better_both=int(((x.lookup_minus_constant_heading>0)&(x.lookup_minus_constant_xy_cm>0)).sum())) for g,x in v.groupby('gate')}
 hwin=int((d.head_rmse_MB_VAR<d.head_rmse_BB_ORIG).sum());xywin=int((d.xy_rmse_cm_MB_VAR<d.xy_rmse_cm_BB_ORIG).sum());sel=sh[sh.case.str.startswith(('R2','R5'))];local=int((sel.combined_minus_mean_head_mse_deg2>0).sum())
 checks=[('Historical CSV metrics (6 significant digits)',864,r['historical_csv']['passed'],'ARCHIVED_CSV'),('Previous chat RMSE values (4 decimals)',48,c['chat_display_matches'],'CHAT_ONLY'),('Actual full recursions',132,r['actual_full_recursions'],'CHAT_ONLY'),('Logical treatment comparisons',144,r['logical_comparisons'],'CHAT_ONLY'),('Stable derivatives passing',9356,p['stable_derivatives']-p['stable_derivative_failures'],'CHAT_ONLY'),('Branch-transition derivatives recorded',52,p['transition_derivatives'],'CHAT_ONLY'),('Scalar/port invariance tests passing',28224,p['invariance_tests']-p['invariance_failures'],'CHAT_ONLY'),('Same-prior update candidates',50176,s['shadow_candidates'],'CHAT_ONLY'),('Archived prediction linkage rows',6272,m['rows'],'CHAT_ONLY'),('Heading improvements vs BB_ORIG (self)',12,hwin,'CHAT_AND_CSV'),('XY improvements vs BB_ORIG (self)',8,xywin,'CHAT_AND_CSV'),('Lookup wins vs constant (self, both errors)',8,wins['self']['lookup_better_both'],'CHAT_ONLY'),('Constant wins vs lookup (self, both errors)',4,wins['self']['constant_better_both'],'CHAT_ONLY'),('R2/R5 immediate heading loss favors mean-only',8,local,'CHAT_ONLY')]
 comp=pd.DataFrame([dict(item=a,previous_report=b,rebuild=c,evidence_kind=e,status='MATCH' if b==c else 'DIFFERENT') for a,b,c,e in checks]);comp.to_csv(ROOT/'results/tables/PREVIOUS_REPORT_CLAIM_COMPARISON.csv',index=False)
 assert (comp.status=='MATCH').all()
 qa=dict(package='DualLP_Physics_Link_Validation_20261101',execution_class='NEW_RETROSPECTIVE_RECONSTRUCTION',technical_status='PASS_WITHIN_EXECUTED_SCOPE',scientific_interpretation='MIXED',independent_audit='NOT_PERFORMED_SELF_REVIEW_ONLY',original_archive_byte_identity='NOT_VERIFIABLE_ORIGINAL_ARCHIVE_UNAVAILABLE',phases={'V0':'PASS','V1':'PASS_WITH_TRANSITION_STRATIFICATION','V2':'PASS_ALGEBRA_RECURSIVE_CAUSAL_COMPLETENESS_NOT_CLAIMED','V3':'PASS_EXECUTION_MIXED_SCIENTIFIC_RESULT','V4':'NOT_RUN_OPTIONAL','V5_archived_predictions':'PASS','V5_fresh_inference':m['fresh_model_inference']},previous_claims_all_matched=True,actual_recursions=132,logical_comparisons=144,heading_improved_conditions=hwin,xy_improved_conditions=xywin,lookup_constant_comparison=wins,replay=r,physics=p,shadow=s,comparison=c,mean_lineage=m,trace_contract=t)
 write('QA.json',qa)
 table='|조건|기존 Heading °|평균+lookup Heading °|기존 XY cm|평균+lookup XY cm|\n|---|---:|---:|---:|---:|\n'
 for _,a in d.iterrows():table+=f'|{a.case[:2]}-B / {a.bias}|{a.head_rmse_BB_ORIG:.4f}|{a.head_rmse_MB_VAR:.4f}|{a.xy_rmse_cm_BB_ORIG:.4f}|{a.xy_rmse_cm_MB_VAR:.4f}|\n'
 compare='|검사|이전 보고|재구현|대조 수준|\n|---|---:|---:|---|\n'
 for _,a in comp.iterrows():compare+=f'|{a["item"]}|{a.previous_report}|{a.rebuild}|{a.evidence_kind}|\n'
 constants=read('results/CONSTANT_VARIANCE_TRAIN_LOCK.json')['held_route_constants'];ct='|평가 경로|학습 경로|고정 추가분산 λ|\n|---|---|---:|\n'
 for case,x in constants.items():ct+=f'|{case[:2]}-B|'+', '.join(z[:2]+'-B' for z in x['train_routes'])+f'|{x["variance"]:.17g}|\n'
 report=r'''# Dual-LP 물리–EKF 연결 검증: 재구현 및 이전 결과 대조

## 1. 결론과 파일의 정체

이 패키지는 없어졌던 결과 ZIP의 바이트 복구본이 아니라, 보존된 GitHub 소스·RF·CONTROL·제안 명세로 **새로 구현하고 실제 실행한 재현본**이다. 기존 모델을 개선하거나 결과를 맞추기 위한 재학습·파라미터 탐색은 하지 않았다.

**실행한 수치 검증은 통과했다. 과학적 해석은 MIXED이며 독립 감사 완료본은 아니다.** 기존 결과의 Heading 12/12 개선, XY 8/12 개선, R4-B의 XY 악화가 유지됐다. 거리 lookup은 사전에 정한 상수에 대해 R2/R5 8조건에서 유리하고 R4 4조건에서 불리했다.

원래 208.7 MB ZIP·그 안의 전체 trace·원래 구현 코드·동결/감사 서명·커밋 `1550335002367c656939bab4876675c612f0915c`는 회수하지 못했다. 따라서 원 ZIP과 파일별 byte 비교, 원 trace 전체와의 equality, 원 감사 서명 재현은 주장하지 않는다. 비교 수준은 세 가지로 분리했다: 원격에 남아 있는 CSV, 원격 CONTROL trace, 대화에만 남은 보고 수치.

## 2. 유지한 실험과 비교 대상

대상은 R2-B·R4-B·R5-B × B0/L0/L1/L2. 모두 같은 기존 장면의 반복 경로이며 독립 환경 12개가 아니다. 상태는 `[x,y,psi,b_g]` 4개이고 sensor seed는 0이다. 거리 관측은 원래 정수 first-path 연산, 편파 관측은 공통 tap의 signed `(Pplus-Pminus)/(Pplus+Pminus)`다. 거리 예측 함수는 원래의 연속 surrogate `distance+B_OLD`이며, 이를 정수 detector로 바꾼 것이 아니다.

`BB_ORIG`는 기존 평균·기존 분산, `MB_ORIG`는 저장된 range 평균만 교체, `BB_VAR`는 기존 평균·기존 lookup 추가분산, `MB_VAR`는 평균 교체와 lookup 결합이다. MB는 range 평균 교체다. 편파 평균은 그대로이며 저장된 μs 차이가 0임을 확인했다. CONST는 동일한 range 평균 설정에서 편파 추가분산만 상수로 바꾼 대조군이다.

원 `diag_mbvar.run`을 변경 없이 호출했다. Jacobian 기록은 모델 반환값을 저장하는 수동 wrapper이며 원 필터 상태를 수정하지 않는다. 추가분산은 **prediction 전의 직전 posterior 거리**, k=0에서는 x0로 조회한다. sigma를 선형 보간한 뒤 제곱하고, 끝점 밖은 원 np.interp의 endpoint hold를 유지했다. 측정 후보가 아니라 전 시간점 `t>=30 s`로 최종 RMSE를 계산했다.

원 factorial 96개 논리 비교와 상수 48개 비교를 구성했다. BASE의 self mask로 고정한 BASE fixed는 같은 결과이므로 12건을 alias로 재사용했다. **실제 전체 재귀 132회, 논리 비교 144개**이며 추가 mask 생성용 전체 재귀는 0회다. RT·재학습·신규 sensor seed sweep도 0회다.

## 3. 이전 결과와 재실행 비교

''' + compare + r'''

CSV 비교는 표시된 6유효숫자까지의 일치이지 원 CSV가 보존하지 않은 내부 float 전체의 일치가 아니다. 대화 수치 48개 비교는 소수 넷째 자리 표시값 기준이다. 대화에서 보고된 검사 개수의 일치는 원 검사 코드·표본별 결과 파일의 복구를 뜻하지 않는다.

B0/L2 원 CONTROL과 `BB_ORIG/MB_ORIG`의 fixed 결과를 12건 대조했다. acceptance mask 차이는 0, 최대 XY 상태차는 **3.936e-14 m**, wrapped Heading 차이는 **5.329e-15 rad**, 공분산 차이는 **2.811e-16**이다. 원 CONTROL이 없는 L0/L1은 저장된 최종 CSV와 비교하고 동일 소스 sensor generator로 재생했다.

[원 CSV 864개 지표 대조](results/tables/LEGACY_96x9_PARITY.csv) · [CONTROL 상태·공분산 대조](results/tables/CONTROL_STATE_COVARIANCE_PARITY.csv) · [대화 수치 48개 대조](results/tables/PREVIOUS_CHAT_VS_REBUILD_48_VALUES.csv)

### 12조건 결과 — self gate

''' + table + r'''

R4-B도 제거하지 않았다. R2/R5는 결합 설정이 기존 기준보다 Heading·XY 모두 개선되고 R4는 Heading만 소폭 개선되고 XY는 악화된다. 분산 단독 `BB_VAR`의 Heading 개선 역시 12/12이며, 결합 설정이 모든 단독 설정보다 우수하다는 주장은 하지 않는다.

## 4. V1: FFD·관측·Jacobian 연결

Full/LoS 원 채널과 source complex FFD를 같은 관측 연산으로 처리했다. 3,136개 유일 RF packet에서 Full 채널로 재계산한 관측과 CONTROL의 최대 차이는 거리 **3.553e-15 m**, signed 비 **2.220e-16**이다. 각 packet의 포트 power, 공통 tap, strongest port, 상대 기하, `J_sx,J_sy,J_spsi`, signed 잔차가 보존되어 있다.

위치 두 축과 Heading의 central difference 및 half-step 검사는 9,408개다. 중심/±step/±half-step에서 tap·port·보간 cell이 동일한 **9,356개는 모두 통과**, 나머지 **52개는 비매끄러운 branch 전환으로 별도 기록**했다. 전환 packet을 EKF 평가에서 제거하지 않았다. 기준은 위치 step 1e-4 m, Heading 1e-5 rad, atol 1e-5 + rtol 1e-3다.

주파수에 무관한 공통 복소 scalar 두 개와 port swap을 Full/LoS/Source 세 채널에 적용한 28,224개 검사도 통과했다. 이 결과는 관측 연산의 불변성이지 실제 하드웨어의 이득·위상 오차를 보정했다는 의미가 아니다.

SourceFFD와 native LoS는 **정확히 같은 복소 스펙트럼으로 가정하지 않았다**. 세 경로의 signed s 최대 차이는 각각 1.067e-5, 2.416e-6, 5.041e-6이다. 저장된 RF sample 좌표가 반올림되어 CONTROL truth와 최대 약 5e-7 m 차이가 있고 source의 pole chart 등 연산 차이도 구분해야 한다. 해당 차이를 전체 성능 차이의 확정 원인으로 해석하지 않았다.

![물리 작동점과 잔차](results/figures/F1_PHYSICAL_SENSITIVITY_RESIDUAL.png)

[packet ledger](results/PHYSICS_PACKET_LEDGER.csv.gz)에는 Full−LoS를 각각 own tap과 Full 공통 tap에서 계산한 값, LoS−Source, signed 잔차를 별도 열로 둔다. scatter는 기하 의존 작동점을 보여주며 상관의 인과관계를 입증하는 그림은 아니다.

## 5. V2: 같은 prior·같은 lookup 상태에서의 갱신

BASE의 같은 prior, 공분산, J, 직전 posterior lookup 상태를 복제하여 평균×분산 2×2 후보를 계산했다. 총 50,176개 후보는 shadow 계산이며 원 재귀 상태를 덮어쓰지 않는다. 여기서 즉시 손실의 주요 표본은 **BASE fixed accepted AND t>=30 s**이고 최종 RMSE의 전 시간점 표본과 다르다.

`epsilon = z - h(truth) - mu`, `delta_h = h(truth) - h(prior)`, `nu = epsilon + delta_h`를 사용하고 `delta_x = K epsilon + K delta_h`로 분해했다. range와 편파의 signed 기여를 별도로 보존했다. truth는 이 사후 진단과 평가에만 사용한다. 기존 controls의 ground-truth 기반 센서 모사와 구분되며 truth가 필터 측정값이나 gain 선택에 입력되지 않는다.

동일 prior에서는 평균만 바꾸면 K는 그대로이고 innovation만 바뀐다. 편파 분산에 λ를 더하면 `K1[:,s] = K0[:,s] / (1 + lambda * inv(S0)[s,s])`가 성립한다. 그 최대 오차는 8.327e-17이다. innovation 분해 오차는 1.388e-16, correction 분해 오차는 1.388e-17, Schur complement로 계산한 Heading 정밀도와 posterior 역분산의 상대 오차는 1.880e-13이다.

**R2/R5의 8조건 모두 동일 prior의 즉시 Heading MSE는 평균만 교체한 후보가 결합 후보보다 낮았다. 그런데 최종 재귀 Heading RMSE는 결합 설정이 더 낮다.** 따라서 ‘추가분산이 매 순간 오차를 줄여서 최종 성능을 개선했다’고 설명할 수 없다. 이후 prior와 covariance, gate 이력의 변화가 관련되어 있지만 이 재현만으로 전체 누적 인과 경로를 완전히 분해했다고 주장하지 않는다. XY는 R2 L1/L2에서 즉시 효과 방향이 다르다.

![같은 prior 즉시 손실](results/figures/F2_SAME_PRIOR_HEADING_CONTRAST.png)

[모든 signed shadow 갱신](results/MATCHED_PRIOR_2X2.csv.gz) · [12조건 즉시 손실 비교](results/tables/SAME_PRIOR_VARIANCE_CONTRASTS_12.csv) · [최초 상태·gate 분기](results/tables/FIRST_DIVERGENCE.csv)

## 6. V3: 상수 대 거리 lookup

평가 route를 제외한 다른 두 B-route의 B0 BASE 직전 posterior에서 기존 sigma lookup²의 평균을 계산하고, 두 route를 동일 가중했다. 모든 finite t>=30 표본을 사용하며 accepted-only 평균이나 sigma 평균의 제곱으로 바꾸지 않았다. 상수는 treatment 성능 계산 전에 기록했지만 과거 결과를 이미 알고 있는 **회고적 재현**이므로 새 사전등록 실험이라고 부르지 않는다.

''' + ct + r'''

**fixed와 self 모두 R2/R5 8조건은 lookup이 Heading·XY 둘 다 우수하고, R4 4조건은 상수가 둘 다 우수했다.** R4-B/B0 self의 lookup은 1.4312° / 9.4325 cm, 상수는 1.1369° / 5.4898 cm다. 이전 보고값과 소수 넷째 자리까지 같다. 평가한 하나의 상수 산식에 대한 결과이지 최적 상수 탐색 결과가 아니다.

![Heading 정책 비교](results/figures/F3_HEADING_VARIANCE_POLICIES.png)
![XY 정책 비교](results/figures/F4_POSITION_VARIANCE_POLICIES.png)

같은 우열이 fixed mask에서도 유지되므로 수용 packet 집합 차이만으로 설명되지는 않는다. fixed에서도 각 정책의 prior·covariance는 달라진다. 따라서 이 비교가 모든 재귀 효과를 제거한 인과실험인 것은 아니다.

## 7. V5와 검토 범위

원 HG/MR 압축 CSV 및 `x1/run_stage.py::load_case`의 식으로 저장된 range 평균을 복원했다. `mu_MB = HG.e_r - MR.MU_R_EXDS__meas_r_cm/100`, `mu_BB = HG.e_r - MR.BASE__meas_r_cm/100`를 사용했다. 세 경로 × B0/L2의 **6,272행 모두 pose_id·시간 일치 및 평균 대조 통과**다. μBB 최대차 6.523e-16 m, μMB 최대차 1.110e-16 m로 허용오차 1e-12 m 이하다. 이 식은 역사적 예측의 계보 확인이며 truth를 사용하는 신규 배포 예측기가 아니다.

원 ML 모델·scaler·fold 산출물은 회수되지 않아 fresh inference는 BLOCKED다. V4 시간적 지속성의 누적 전달 실험은 선택 항목으로 미실행이다.

별도 수식으로 2×2 역행렬, covariance contraction, 상태 갱신 및 점수를 재계산했고 144개 논리 trace를 대조했다. rejected packet의 상태·공분산 변화는 정확히 0, 모든 prior lookup/R/innovation/NIS 계약 검사도 통과했다. 13개 음성/항등 fixture에는 중복 key, 누락, 시간 이동, port 교환, range 오염, 빈 행, 범위 밖 s, NaN, RF byte 변조, 비양정 covariance 및 두 null intervention이 포함된다. 이들은 고립된 fixture이며 전체 파이프라인에 대한 모든 가능한 음성시험을 뜻하지 않는다.

**이 모든 검토는 같은 세션의 SELF_REVIEW_ONLY다. 서로 다른 algebra를 사용했더라도 독립 감사자 인증은 아니다.** 원고·원 RF·원 CONTROL·legacy 필터 소스의 내용을 변경하지 않았으며 새 결과 경로에만 기록했다. sparse 실행 묶음이므로 저장소 전체 inventory/release/MATLAB 검사는 수행하지 않았다.

## 8. 사용 가능한 주장과 금지할 확대 해석

보존된 12조건에서 실제 source FFD로 정의된 signed 관측 민감도, 잔여 오차, EKF gain 및 갱신을 같은 packet 키로 연결했다는 주장은 수치 근거가 있다. 평균과 분산의 국소 효과 및 최종 재귀 효과가 다를 수 있고, lookup의 상대 이점이 경로별로 달라진다는 결론도 유지된다.

반면 모든 환경 개선, 최적 거리 함수, 정확한 시공간 covariance 처리, 실제 하드웨어 보정 완료, 독립 장면 일반화, R4의 특정 반사체를 단일 원인으로 확정, 원본 ZIP과 byte-identical 복원, 독립 사전·사후 감사 완료는 주장하지 않는다.

## 9. 산출물과 재현

[QA.json](QA.json)이 최종 상태, [MANIFEST.json](MANIFEST.json)이 출처·환경·코드 hash, [REPRODUCE.md](REPRODUCE.md)가 실행 안내다. 132개 실제 trace와 144개 논리 trace의 대응은 [FIXED_SELF_TRACE_INDEX.json](results/FIXED_SELF_TRACE_INDEX.json)에 있다. 원 제안자 문서는 `evidence/proposer_package/`에 그대로 남겼다.

메인 ZIP은 코드·모든 새 결과·원 RF·CONTROL·원 HG/MR·참고 문서를 담는다. 각각 약 247.7 MB인 FFD bank 2개만 별도 ZIP으로 제공한다. **결과 열람·점수 재검사는 메인 ZIP만으로 가능하고, 물리 모델과 필터 전체 재실행은 두 bank를 추가해야 한다.** bank 없이 전체 재현 완료로 표시하지 않는다.
'''
 (ROOT/'REPORT.md').write_text(report,encoding='utf-8')
 (ROOT/'README_KO.md').write_text('''# DualLP Physics Link Validation — 재구현본

**제안자 패키지가 아니라 실제 실행 결과를 담은 재구현 패키지입니다.** 원래 사라진 ZIP과 byte-identical 복원본은 아닙니다.

|핵심 확인|결과|
|---|---|
|실제 재귀 / 논리 비교|132회 / 144개|
|원 CSV 결과 대조|864/864, 6유효숫자 일치|
|이전 대화 RMSE 대조|48/48, 소수 넷째 자리 일치|
|원 CONTROL 상태·공분산|B0/L2 × 3경로 × 2평균 = 12건 통과|
|물리 미분|안정 9,356 통과, 전환 52 별도 보존|
|동일 prior 후보 갱신|50,176개|
|원 저장 평균 계보|6,272행 통과|
|독립 감사|미실행 — SELF_REVIEW_ONLY|

[한국어 상세 보고서](REPORT.md) → [최종 QA](QA.json) → [이전 보고 대조표](results/tables/PREVIOUS_REPORT_CLAIM_COMPARISON.csv) → [12조건 결과](results/tables/LEGACY_PRESERVATION_12.csv)

기존 Heading 12/12 개선, XY 8/12 개선이 재현됐습니다. lookup 대 사전 지정 상수는 R2/R5 8조건에서 lookup 우세, R4 4조건에서 상수 우세로 이전과 같습니다. 과학적 해석은 MIXED입니다.

메인 ZIP에는 코드, 원 RF/CONTROL, 원 예측 CSV, 132개 전체 trace, shadow ledger, 검사표와 그림을 포함합니다. 큰 입력인 FFD bank 두 개만 외부 companion ZIP입니다. 필터 전체 재실행에는 [REPRODUCE.md](REPRODUCE.md)에 따라 두 bank를 추가하세요. 원 결과는 덮어쓰지 않고 새 출력 폴더에서 실행합니다.

V4는 선택 항목으로 미실행. V5 fresh inference는 원 모델/scaler/fold 미회수로 BLOCKED입니다. 원 아카이브·동결 서명·감사 파일이 복구되었다고 주장하지 않습니다.
''',encoding='utf-8')
 (ROOT/'contracts/RECONSTRUCTION_METADATA_CLARIFICATION.md').write_text('''# 재구현 설정 메타데이터 해석 기록

수치 설정은 실행 전에 저장한 CONFIG_LOCK.json을 변경하지 않는다. 그 파일은 제안 JSON에서 상속한 allowed_now(문서 작업), statuses=NOT_RUN, input_lock_sha256=null 필드를 포함한다. 이는 과거 제안 상태와 실행 시작 시점의 snapshot이며, 최종 실행 상태나 독립 동결 서명이 아니다.

실제 실행 권한은 사용자의 “다시 구현해서 만들어라 이전 결과랑 비교해” 요청에 따른 회고적 재구현이다. 실제 입력 hash는 INPUT_LOCK.json과 RECONSTRUCTION_START_RECEIPT.json, 최종 상태는 루트 QA.json에 기록했다. base_git_sha는 제안 원고 기준이고 실제 사용한 소스 commit은 RECOVERY_MANIFEST.json의 source_old/source_evidence다. governance_reference_sha 역시 제안의 역사적 참조이며 이번에 취득한 문서 commit은 recovery manifest에 별도 표시된다.

이 기록은 수치 규칙 변경이 아니다. 과거 결과를 이미 본 상태이고 독립 pre-run auditor가 없으므로 FROZEN 사전등록 실험 또는 독립 scientific release라고 표시하지 않는다. 어떤 불리한 결과도 삭제하거나 튜닝하지 않았다.
''',encoding='utf-8')
 (ROOT/'audit/SELF_REVIEW_VERDICT.json').parent.mkdir(exist_ok=True)
 write('audit/SELF_REVIEW_VERDICT.json',dict(status='PASS_WITHIN_EXECUTED_NUMERICAL_SCOPE',reviewer_independence='NO_SAME_SESSION',scientific_interpretation='MIXED',original_audit_recovered=False,checks=['legacy CSV display parity','B0/L2 CONTROL full state/covariance parity','raw H observer parity','stable finite differences','scalar/port invariants','same-prior algebra','explicit 2x2 inverse and covariance contraction','mask/lookup/rejection contracts','archived HG/MR to CONTROL linkage','13 isolated negative/null fixtures'],not_checked=['independent pre-run audit','independent external post-run audit','old full archive equality','V4 cumulative temporal effects','fresh learned-model inference','repository-wide inventory/release/MATLAB checks']))
 print('REPORTS_FINALIZED',json.dumps(dict(heading_wins=hwin,xy_wins=xywin,lookup_constant=wins,claim_checks=len(comp)),ensure_ascii=False))
if __name__=='__main__':main()
