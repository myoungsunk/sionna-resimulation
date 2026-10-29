# 2단계: 입력·시간 정렬 감사

질문 ID: MBVAR-AUDIT-S2-INPUT-TIME-ALIGNMENT-20261029

기록일: 2026-10-29. 역할: AUDITOR. 이 문서는 같은 대화에서 수행한 검사를 정리한 것이며 독립 감사라고 주장하지 않는다.

적용 지침: 저장소 AGENTS.md와 [COMMON_CONTRACT](https://github.com/myoungsunk/sionna-resimulation/blob/73d589ebd0b9da37fc60d2e34c87de5ffb95c107/docs/research-governance/COMMON_CONTRACT.md), [ROLE_AUDITOR](https://github.com/myoungsunk/sionna-resimulation/blob/73d589ebd0b9da37fc60d2e34c87de5ffb95c107/docs/research-governance/ROLE_AUDITOR.md). 정책 기준 커밋은 `73d589ebd0b9da37fc60d2e34c87de5ffb95c107`이다. 로컬 지침은 보조로 읽었으며 동결 정책을 덮어쓰지 않았다.

자료 범위: 접근 가능한 GitHub 코드·workflow·실행 로그·manifest·선택한 artifact, 동결 저장소 bytes, 기존 대화의 직접 검사 기록. 기존 노트는 탐색·과거 결과 설명에만 사용했다. 원래 상위 대화의 개별 감사 전문을 모두 확보한 것은 아니다. 아래 브랜치별 문서는 이번에 확보한 근거를 통합한 기록이며 미확보 전문을 복원한 문서가 아니다.

## 범위와 실행

사용자의 별도 2단계 진행 지시에 따라 입력·시간 필드와 실제 코드의 표본 선택을 읽기 전용으로 확인했다. 필터 수학 전체, 시간상관 인과효과, 성능 채택은 판정하지 않는다. Python 3.13 / NumPy 2.2.4에서 저장소 모듈 import 없이 bytes·NPZ·JSON 필드 검사 스크립트를 실행하여 exit 0을 확인했다. 필터·시뮬레이션·RF 생성은 실행하지 않았다.

동결 기준은 9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13이다. [검사 스크립트](evidence/stage2_input_checks.py)와 [실제 출력](evidence/stage2_input_checks.json)을 함께 보존한다. 스크립트는 14 trace와 7 SAMPLES 검사의 범위이며, 아래 별도 timeline 3개 비교 및 코드·기존 CSV 검토 전부를 자동화하는 스크립트라고 주장하지 않는다.

## 실제 입력 검사

- CONTROL 14/14 파일, 총 14,590,582 bytes: lock SHA256와 현재 동결 저장소 bytes의 SHA256 일치(B).
- 모든 trace에서 유한한 단조 증가 t_s, dt≈0.2초, pose_id 중복 0, 관련 배열의 첫 차원 일치. 최대 dt 오차 4.5464e-14초.
- R2: 979행/195.6초; R4: 742행/148.2초; R5: 1415행/282.8초.
- B0/L2 7쌍은 t_s·pose_id·truth[:3] 일치. z=nu+h+mu 재구성 최대 차이 2.22e-16, 기본 R 동일. BASE mask는 R2_aA_m0에서 8행, R5_aA_m0에서 1행 다름. 다른 5쌍은 차이 0. 입력 정렬 일치가 mask 동일성을 뜻하지 않음.
- 14개 모두 BB/MB의 편파 평균 mu_s와 기본 R은 일치. Δs 거리 평균 보정은 별도 평균 경로이고 MB_VAR 추가 분산은 runtime R 보강 경로로 구분.
- SAMPLES 7개 검사에서 trace pose_id 누락·중복 0. 좌표 차이는 JSON 반올림 범위인 5e-7m 미만, yaw 차이는 8.42e-9rad 이하. 추가 SAMPLES pose는 해당 trace에서 사용되지 않음.
- 원래 timeline_R2/R4/R5와 대표 B0 3개를 비교: pose_id 선택 일치, 시간 최대 오차 2.84e-14초, XY 3.55e-15m, yaw 8.88e-16rad. 3/7 B0 대표 검사이며 14개 전체를 원시 timeline과 직접 대조했다고 주장하지 않음.

원시 timeline 위치는 frozen commit의 results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/INPUTS/timeline_R{2,4,5}_Tnone.csv이다. SHA256은 증거 JSON에 기록했다. FULL/LoS RF bytes 및 행별 H의 상위 대응은 검사하지 않았다. 과거 실행 input artifact bytes의 검증 수는 여전히 0이다.

## S2-F1: 선택 표본 ACF의 초 단위 환산 — REDIRECT

[acf_stats](https://github.com/myoungsunk/sionna-resimulation/blob/3e291da9fdf5a8f6d1fe21f4c9350bc5edac9f18/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_control_correction_20261029/ctl_core.py#L213-L224)는 유한값을 모아 배열의 lag를 계산하고 첫 1/e 교차 lag에 0.2를 곱한다. [summarize](https://github.com/myoungsunk/sionna-resimulation/blob/3e291da9fdf5a8f6d1fe21f4c9350bc5edac9f18/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_control_correction_20261029/ctl_core.py#L238-L270)는 S_base/S_used로 eps를 먼저 선택한다. 이 선택 후 이웃은 원래 시간에서 반드시 0.2초 이웃이 아니다.

선택 인덱스를 i_j라 하면 계산하는 것은 corr(e[i_j],e[i_{j+l}])이다. t[i_{j+l}]-t[i_j]=0.2l일 때만 l×0.2초의 시간 상관으로 해석할 수 있다. 이번 입력에서 실제 선택 간격 누락을 확인했다.

| B0 case, t≥30 BASE | 선택 수 | 원래 인덱스 비연속 이웃 쌍 | 최대 간격(초) |
|---|---:|---:|---:|
| R2_aA_m0 | 810 | 3 | 2.4 |
| R2_aA_m45 | 792 | 16 | 2.4 |
| R2_aB_m0 | 822 | 4 | 0.8 |
| R4_aA_m0 | 568 | 16 | 0.6 |
| R4_aB_m0 | 578 | 6 | 1.4 |
| R5_aA_m0 | 1199 | 13 | 3.6 |
| R5_aB_m0 | 1236 | 14 | 1.6 |

기존 control A_SUMMARY_R4의 R4B / MB_VAR / seed 0 / S_base 행에는 acf_lag1≈0.69982027, acf_l1e_s=0.4가 기록되어 있다. 현재 B0 입력의 해당 BASE 선택은 578개, 선택 이웃 577쌍 중 6쌍이 0.2초 이웃이 아니다. 따라서 lag1은 다음 accepted event의 상관으로 유지할 수 있으나 acf_l1e_s를 고정 실제 초 단위 상관길이로 그대로 해석하는 것은 보류한다.

영향 범위: 선택 표본 ACF의 물리 시간 해석. 오차의 크기·성능 변화는 재계산하지 않았으며 다른 모든 결과를 무효화하지 않는다. 코드 수정 미수행, 필터 재실행 미수행, 이 항목 재검증 미수행이다.

## 구분해야 할 경로와 기존 한계

- K의 lag cross-correlation은 원래 인덱스 차이 1을 검사한다(ctl_core.py 265–268). 위 ACF와 동일 오류로 묶지 않는다.
- 현재 S_all의 유한 eps는 원래 연속 시간축에 있으므로 S_base 압축 문제로 E2/E2R 전체를 무효화하지 않는다.
- causal [acf1 / shuffle](https://github.com/myoungsunk/sionna-resimulation/blob/4e14448a8af81c3e99cd257f23cb07615ebd8a15/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_causal_isolation_20261029/causal_isolation.py#L30-L92)은 accepted 표본의 lag이다. [기존 보고서](https://github.com/myoungsunk/sionna-resimulation/blob/3af005b8491b5668c0989b82bc3cbc990cfcf8b7/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_causal_isolation_20261029/RESULTS_RUN_40825807998.md#L11-L21)가 accepted lag 및 개입 한계를 이미 명시한다. 새로 발견한 미수정 결함으로 중복 등록하지 않는다.
- E1 decimation과 E4 block permutation은 accepted/stratum 구성원 개수 기준이다. [permute_eps](https://github.com/myoungsunk/sionna-resimulation/blob/3e291da9fdf5a8f6d1fe21f4c9350bc5edac9f18/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_control_correction_20261029/ctl_core.py#L322-L341)의 round(block_s/.2)는 연속 실제 시간 구간을 보장하지 않는다. 프로토콜의 361–362행 부록이 개수 기준을 명시하므로 계약 위반으로 단정하지 않고 해석 한계로 유지한다.
- premodel의 유한값 압축 ACF는 현재 검사한 관측이 모두 유한하고 연속이므로 실제 관측 누락 오류로 판정하지 않는다. scratch 과거 실행 연결은 별도 G2이다.
- time-GM [moments / whiten](https://github.com/myoungsunk/sionna-resimulation/blob/7fab61cb1b26240b8031b77e277bc6ab92651245/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_time_gm_20261029/time_gm_study.py#L32-L85)는 원래 인덱스 및 시간 차이 조건을 사용한다. TRAIN_ACF 12행에서 R2/R4/R5의 n=829/592/1265 및 lag8 쌍 수 n−8, HELD 6행에서 n−1=828/591/1264가 그 경로와 부합한다. 이것은 AR1 모델 적합성·일반화·채택 승인과 별개이다.

## 경로별 결론

| 브랜치/범위 | 판단 | 남는 제한 |
|---|---|---|
| forensics 신규 실행 | BLOCKED | 실행 receipt·D3/D4 결과 연결 미확보 |
| premodel 저장 코드·현재 입력 | 제한적 ACCEPT / READY_WITH_GAPS | 과거 scratch 실행본 동일성 미확보 |
| control 입력 행·시간 | 제한적 ACCEPT | 과거 artifact 입력 bytes 미확인 |
| control 선택 ACF의 초 해석 | REDIRECT | 실제 시간 lag 처리 또는 accepted-event 명명 필요; 이번 수정/재실행 없음 |
| causal 행·시간 구조 | 제한적 ACCEPT | accepted lag·geometry 교란 한계 유지; 인과 승인 없음 |
| revalidation 입력·유한 전체 시간축 | 제한적 ACCEPT | 전체 갱신/Jacobian 수학 감사 미수행 |
| time-GM 원래 시간 인덱스 경로 | 제한적 ACCEPT | 모델 적합성·채택 감사 미수행 |

확인한 것은 현재 동결 입력 bytes·필드·표본 선택과 해당 경로의 시간 의미이다. 미확인 범위는 과거 실행 입력 bytes, scratch 원본, 원시 RF/H 대응, 공통 필터 수학 전체 및 인과·채택 판단이다. 전체 상태는 READY_WITH_GAPS이며 시스템 정확성 PASS가 아니다. 이번 2단계는 종료하고 다음 단계는 자동 진행하지 않는다.
