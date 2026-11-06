# prior provider 1단계 — 정보 출처·시간축·독립성 점검

질문 ID FP-SC-PRIOR-PROVIDER-STAGE1. 역할 PROPOSER / 동일 작업자 저장 기록 자체검사.
기준 commit 94b49a5abe8443b8eacf4a1e3600ad3d52b10e9f, 작성일 2026-11-06 KST.
범위: 기존 기록과 소스 조사, SHA/배열 연결 및 저장 산술 대조. provider/DR 궤적/새 RF/SourceFFD/EKF/E1-02/E2 실행 없음.
판정: **정보 출처 점검 완료, prior VALID 근거 확보는 미완료**.

## 1. 실제 정보 계보

| 항목 | 실제 출처·의존성 | 시점·단위 | 독립성 판단 |
|---|---|---|---|
| DR 입력 ds/gy/dt | 동작 궤적에서 생성한 wheel/gyro 모사 입력; seed10. gy는 각속도가 아닌 각도 증분 | 구간 (t[k-1],t[k]], m/rad/s, 5Hz | 생성 recipe에 RF/UWB 갱신 입력은 없음. 하지만 비교 대상 EKF prior가 바로 같은 입력을 사용하므로 prior와 독립적인 추정치는 아님 |
| 초기 x0 | 원래 recipe는 초기 truth pose + 선언한 초기 오차; 추정 gyro bias는 0으로 확장 | k=0, x/y/yaw/bias | 모사 초기조건이다. 실제 절대 위치·Heading 센서의 정확도 증거가 아님 |
| 초기 P0 | frozen packet의 초기 covariance; 과거 OFF_BB 초기값에서 보존된 경로가 S1 materialize에 있음 | 첫 측정 전 | 배열 보존을 확인해도 공분산 보정/실제 오차 coverage 입증은 아님 |
| prior[k] | W0 replay의 이전 UWB posterior x[k-1]에 동일 ds/gy/dt로 예측 | 현재 z[k] 갱신 전 | 현재 관측 이전이라는 인과성은 있음. 과거 UWB와 DR에 모두 의존함 |
| Pprior[k] | 같은 필터의 이전 posterior covariance와 Q로 예측 | 현재 갱신 전 | 공통 모델 오차/과신을 공유할 수 있음 |
| 주 필터 innovation nu[k] | z[k] - h(prior[k]) - muMB[k] | 현재 관측을 받은 뒤, 갱신 전 | 관측-예측 불일치 지표이며 독립 위치 정답이 아님. 현재 prior 신뢰 판단에는 j<k만 허용해야 함 |
| 주 필터 S/nis | H Pprior H^T + Reff, nu^T S^-1 nu | 현재 관측 이후 | Pprior 및 관측모델에 의존. 작은 값만으로 prior 정확성을 증명하지 못함 |
| mask[k] | 별도 shadow 필터의 muBASE 기반 innovation과 R로 결정 | 현재 관측 이후 | 주 필터 nis와 동일 통계량이 아님. mask와 주 nis를 직접 임계값 등식으로 연결하면 안 됨 |
| M의 과거 FP·native offset | UWB raw 이력과 prior/model 기반 offset에 의존하는 원래 경로 | 과거 raw 및 현재 prior | P와 독립적인 센서 증거가 아님. 현 R1 보호에서는 trusted 이력 활성화 자체가 차단됨 |
| Native_LoS | 같은 궤적/초기상태/DR에서 direct spectrum을 쓴 실험 대조군 | 대응 pose/time | 실제 운용에서 얻는 별도 독립 센서가 아님. Full provider에 주입하면 oracle 정보 사용 |
| evaluator truth·clean_H | 별도 평가용 NPZ | 평가 전용 | provider 입력 금지 |

특히 현재 prior를 출발점으로 같은 DR을 한 번 더 계산하는 검사는 필터 산술의 자기일관성 검사다.
독립 DR 비교를 하려면 UWB로 상태를 재설정하지 않는 별도 궤적이 필요하다. 그래도 공통 x0/DR 오차는 공유한다.
그 DR 궤적은 이번에 생성하지 않았다.

## 2. 시간 순서

1. t[k-1]까지의 관측·갱신 상태가 존재한다.
2. (t[k-1],t[k]]의 ds/gy/dt로 prior[k]를 만든다. k=0은 x0/P0 그대로다.
3. 향후 provider가 prior[k]를 판정한다면 사용할 innovation/mask는 **j<k**여야 한다.
4. z[k]를 받아 shadow mask 및 주 innovation을 계산한다.
5. UWB 갱신으로 x[k]/P[k]를 만든다. 이 정보는 다음 시점부터 과거 이력으로 사용할 수 있다.

원본 offline 배열에는 전체 시간열이 있으므로 파일이 분리되어 있다는 사실만으로 미래 정보 접근이 차단되지는 않는다.
추후 로더는 prior 키·pose/time·이력 cutoff를 묶고 미래 값 변조 시 현재 출력 불변 검사를 해야 한다.
현재 innovation으로 현재 FP를 판정하는 탐지 특징과, 그보다 먼저 prior에 신뢰를 부여하는 특징은 구분한다.

## 3. 6,272행 저장 기록 대조

입력/trace/control/receipt SHA를 manifest 또는 baseline ARTIFACT_HASHES와 대조했다.
모든 case의 time/pose join, ds/gy/dt, x0, prior/Pprior 배열 연결을 확인했다.

| case | 행수 | 갱신 채택 | 갱신 기각 |
|---|---:|---:|---:|
| R2 Full | 979 | 971 | 8 |
| R2 Native_LoS | 979 | 979 | 0 |
| R4 Full | 742 | 728 | 14 |
| R4 Native_LoS | 742 | 742 | 0 |
| R5 Full | 1,415 | 1,384 | 31 |
| R5 Native_LoS | 1,415 | 1,415 | 0 |
| 합계 | 6,272 | 6,219 | 53 |

- 3개 경로 모두 Full/Native_LoS의 ds/gy/dt/x0가 배열 단위로 정확히 같다.
- canonical prior/Pprior는 baseline replay 배열과 정확히 같다.
- 저장 이전 posterior에서 원래 운동식을 단일 단계 산술로 대조한 prior 최대차: 5.56e-17 이하.
- nu = z-h-muMB의 차이: 0. 저장 S로 계산한 nis 최대차: 3.56e-15 이하.
- 기준 허용오차 1e-10을 사용했다. 새 필터 재귀 실행, 정확도/탐지 성능 시험이 아니다.
- 기각 53건을 포함한 전 행 nu/S/nis/x/P가 원본 replay에 존재하고 유한하다.
- 반면 canonical online NPZ에는 x/P/nu/S/nis가 빠져 있다. 보존된 trace 필드는 h/H/prior/Pprior/Reff/K/mask다.
- shadow의 innovation/S/nis/상태는 이 원본 trace에 별도 필드로 저장되어 있지 않다. 주 nis를 대신 사용해 gate 원인을 재현했다고 할 수 없다.

R2 controls는 ARCHIVED_CONTROLS다. R4/R5는 LINUX_REMATERIALIZED_ORIGINAL_RECIPE이며
과거 원본 ds 바이트 복구 미해결 상태와 구분된 A2 identity를 유지한다.
준비 script가 모든 case에 control_origin=A2_REMATERIALIZED를 적은 상위 표기보다 case별 실제 receipt를 우선했다.
재료화된 파일의 provenance를 새 센서 측정이나 새 독립 환경으로 해석하지 않는다.

## 4. 어떤 문제를 구분할 수 있는가

| 오류/상황 | 사용할 수 있는 근거 | 이번 판단 |
|---|---|---|
| NaN/비PSD/시간 역전/누락 | 구조·시간 검사 | INVALID 사유가 될 수 있음. 물리적 정확성 판정과 별개 |
| UWB 갱신 이후 점프/DR와 불일치 | 별도 DR 경로와 과거 innovation, 갱신 전후 변화 | 후속 반례 검증 가치 있음. 일치 여부의 위험 기준은 미검증 |
| DR와 prior가 같은 초기 위치 bias를 공유 | 공유 x0·상대 운동만으로 비교 | DR 일관성만으로 구분 불가 |
| DR와 prior가 같은 Heading/gyro 오차를 공유 | 동일 센서·초기화 사용 | 공통 오류가 감춰질 수 있음. 오차 개입으로 식별 범위를 확인해야 함 |
| 잘못된 prior를 multipath 관측이 계속 지지 | innovation·상태가 서로 일치 | 작은 innovation이 거짓 신뢰가 되는 반례가 필요 |
| 공분산은 작지만 중심이 틀림 | covariance/구간폭만 검사 | 정확성 근거가 되지 않음. 기존 11,095건 제한 유지 |
| 장시간 누적 drift | DR 불확실성·경과시간·별도 절대 기준 | 독립 절대 기준이 없으면 신뢰를 무기한 갱신할 수 없음 |

이 표의 '구분 불가'는 DR 일관성 등 명시된 근거만 사용할 때의 한계다.
전체 RF/편파 시스템의 수학적 관측불가능성을 증명한 것은 아니다.

## 5. 남은 근거와 다음 단계에 넘길 조건

1. **별도 DR의 정의:** UWB reset 없는 진단 궤적, 초기화 출처/불확실성, 동일 입력으로 인한 상관을 기록해야 한다.
   이를 prior와 독립인 확률로 곱하지 않는다. 두 추정치의 차이를 정규화할 때 교차 공분산을 무시한 독립 가정을 자동 적용하지 않는다.
2. **과거 기록 연결:** x/P/nu/S/nis/mask를 별도 SHA-locked provider 입력으로 준비할 필요가 있다.
   기존 canonical schema와 원본을 덮어쓰지 않고 버전을 추가한다. shadow gate 원인을 쓰려면 별도 기록 확보 범위를 먼저 정한다.
3. **초기 절대 근거:** 현재 범위의 canonical 입력에는 독립 절대 위치/Heading 센서 관측이나 초기화 인증이 없다.
   truth 기반 모사 초기조건을 실제 운용 초기화의 안전 근거로 바꾸면 안 된다.
4. **innovation 보정 근거:** muMB/muBASE/R은 고정된 offline 모델 입력이다. 이번에는 전 학습/donor/분할의 인과성까지 감사하지 않았다.
   provider에 쓰기 전에 해당 calibration의 사용 가능 시점·노출·분할을 확인해야 한다.
5. **식별 반례:** 공통 초기 bias, 과신, drift/점프, prior를 지지하는 잘못된 RF, stale/복구를 다음 개입 계약에 포함한다.
6. **VALID 의미:** P와 M의 사용 근거/만료 조건을 별도로 정의한다. 아직 VALID 생성 조건·허용 위험·활성화율을 동결할 단계는 아니다.

현재 자료는 prior 신뢰 가설을 검증하기 위한 개발 재료로 사용할 수 있다.
독립 절대 정확도 근거가 확인됐거나 provider가 VALID를 출력해도 된다는 결론은 아니다.

## 6. 소스 근거와 산출물

아래 경로는 기준 commit의 코드다. local/commit SHA는 LINEAGE_CHECK.json에 기록했다.

- scripts/prepare_fp_sc_e102.py:31-60 — 실제 A2 baseline export 경로 및 배열 연결.
- src/qclean_uwb/fp_sc/followup/data.py:14-16,84-106 — canonical 필드 제한과 prior/이력 복사.
- research/MBVAR_PRR_001_20261103/S1/online.py:18-64 — 이전 posterior 예측, shadow gate, 주 innovation, trace 저장.
- research/EKF4_RANGE_S_STAGED_20261014/core.py:54-78 — 운동식과 bias 처리.
- src/qclean_uwb/fp_sc/e0_baseline.py:222-261,399-423 — archived/A2 control routing 및 W0 replay 저장 경로.
- src/qclean_uwb/fp_sc/e0_rematerialized.py — R4/R5 A2 identity와 역사적 ds 바이트 미해결 경계.
- research/DS_MASK_CAUSAL_X1_X2_20261026/pol_bias_model/exp_pb.py:build_controls — 모사 입력/초기화 recipe (Git blob 읽기).
- research/MBVAR_PRR_001_20261103/S1/materialize.py — frozen 관측/평균 보정/초기 covariance 입력 계보 (Git blob 읽기).
- src/qclean_uwb/drivesim/sensor_v2.py:67-68,115-166 — seed별 stream과 wheel/gyro 모사 입력.
- src/qclean_uwb/fp_sc/followup/integrity.py:25-41 및 contracts.py:234 — 현 VALID/실행 차단 유지.

새 파일: inspect_lineage.py, LINEAGE_CHECK.json, RESULTS_KO.md 및 ARTIFACT_HASHES.json.
기존 코드/입력/실패 결과/VAB 주안/권한 변경 없음. 파일 이동·삭제 없음.
이번 1단계는 로컬 결과로 저장했으며 GitHub 추가 푸시는 수행하지 않았다.
2단계 개입 설계·provider 구현·C-only/E1-02/E2 실행으로 넘어가지 않았다.
