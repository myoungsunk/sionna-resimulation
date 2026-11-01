# 01. 제안자 검증 계약 — DLP-PHYS-LINK-001

## 1. 권한·역할·원본
- role: **PROPOSER**, status: **DRAFT-v1 / DESIGN_ONLY**, allowed_execution_now: **NONE**.
- contract_id: `DLP-PHYS-LINK-001`. 기존 `DLP-EKF-GAPS-001`, `MBVAR-INFO-001`, `POL-XCORR-001`을 변경·대체하거나 그 실행 권한을 승계하지 않는다.
- base_git_sha / manuscript_v4_sha: `1aac4d38a6fa335116bcecbebc91ba53c876ecfd`.
- manuscript_blob: `155fd6ae66f4863680d2b6c9f642923e0ea88767`.
- evidence_snapshot: `6c7200091028fd3f0e55aa83b777d0f10b7cf063`.
- governance_reference_sha: `250d617ad89a4105fa1af546cc83ceed9de98f42`; scoped 규칙을 자율 채택한 대응은 06 문서에 명시한다.
- input_lock_sha256: **NOT_FROZEN**. SOURCE_REGISTER는 출처 목록이며 실제 H·CONTROL·학습모형 모든 바이트를 확인한 실행 입력 lock이 아니다.
- draft_contract_sha256 / numeric_config_sha256: 이 파일과 제안 config의 SHA는 PACKAGE_MANIFEST.json에 기록한다. 자기 참조 해시를 파일 안에 넣지 않는다.
- implementer: **NOT_ASSIGNED**; independent_pre_run_auditor: **NOT_ASSIGNED**; proposer_signature: **DRAFT_AUTHOR_ONLY**; approval_for_science: **NONE**.

## 2. 연구 질문과 범위
물리적 Dual-LP 관측의 기하 민감도와 잔여 오차가 EKF 상태 갱신으로 전달되는 과정을 설명하고, 기존 평균 교체·추가분산 모델이 선택 12조건에서 보인 효과를 검증한다. 모든 case 성공·전 환경 일반화·모든 XY 개선을 완료 조건으로 추가하지 않는다.

| 요소 | 고정 규칙 |
|---|---|
| RF | C0 Corridor의 `R2_aB_m0`, `R4_aB_m0`, `R5_aB_m0`; 같은 원본 Full/Native LoS |
| 기하 | B=(10,0,2.65)m, RX z=0.45m, mount=0°; 동일 source의 축·각도·편파부호 |
| 상태 | `[x_m,y_m,psi_rad,b_g_rad_per_s]`; 기존 f,F,Q,P0,x0 그대로 |
| 관측 | 원본 정수 first-path 거리 r, 공통 tap의 signed s; 새 fractional ToA·s1 관측 추가 금지 |
| gyro | B0=0, L0=.01, L1=.05, L2=.20 deg/s; sensor/initial seed=0 |
| 평균 | 저장된 mu_B / mu_M; EXDS는 전체 거리 오차 평균의 교체, mu_s 유지 |
| 공분산 | 기존 packet R_B 유지; 편파 Rss에만 lookup sigma² 추가; 다른 교차항을 지우거나 추가하지 않음 |
| lookup | **prediction 전 이전 posterior**에서 수평 rho 계산; k=0은 초기 상태. PRIOR 방식으로 조용히 변경하지 않음 |
| gate | 최종 성능 SELF_NIS; fixed BASE는 인과 진단. 2DoF 기존 threshold 9.210340371976184 |
| 실행·점수 | recursion t=0부터, 평가 t>=30s; 원래 timestamp·finite mask·샘플 키 보존 |
| 분모 | RF 3개 / 조건 12개 / 물리 scene 1개; packet과 gyro label은 독립 scene이 아님 |

## 3. 경쟁 설명과 분석 추정량
| ID | 추정하려는 것 | 검정/대조 | 기대 부호와 한계 |
|---|---|---|---|
| V1 | 실제 h_s의 yaw/위치 민감도와 잔차의 정렬 | native LoS parity, derivative, common-scalar 불변, port swap | 안정 branch에서 물리 모델 검산. 민감도 존재가 전체 성능 개선을 보장하지 않음 |
| V2 | 평균·분산이 같은 prior에서 gain·signed correction·NIS를 바꾸는 효과 | 2×2 shadow, sigma=0, mu_M=mu_B, 공통 lookup | gain s-column 축소는 대수 예측. MSE 변화는 양/음 모두 허용 |
| V3 | 거리 조건이 동일 규모의 상수 down-weighting보다 추가 가치가 있는가 | zero/constant/lookup × 두 평균 × 두 gate | lookup 우위 가정하지 않음. 같거나 열등하면 거리 특별성 주장 축소 |
| V4 | 잔차 지속성이 상태 방향으로 투영·누적되는가 | raw/조건부 평균제거 ACF, 이동·회전 lag, fixed 선형화 투영 | 순서·기하·mean·prior 효과 분리. 시간-only 원인·정확한 colored likelihood로 확대 금지 |
| V5 | 기존 결과가 동일 입력·학습·예측·재생으로 재현되는가 | fold·scaler·weights·예측·source·trace SHA | 저장 예측 재생과 회귀모형 새 inference를 별도 판정 |

추가분산은 새로운 관측정보를 생성하지 않는다. 고정 prior의 편파 gain은 축소되지만 재귀 상태·gate가 달라져 최종 오차는 비단조적일 수 있다. 통계적 유의성은 지금의 독립 RF 표본으로 승인하지 않는다.

## 4. 작업 순서·상한
V0 source/numeric preflight → 동결·독립 사전 감사 → V1와 V2 → V3 → 조건부 V4/V5. V1/V2를 보기 전에 V3 상수 정의를 잠그며, 실제 V1/V2 결과로 비교군·상수를 고치지 않는다.

기본 source replay: 12조건×4기존 arm×2gate=96 full traces. V3의 상수 arm은 두 평균×12조건×2gate=48개 추가 traces. 합계 상한 **144 full-recursive traces**, 별도 RF 생성·학습 seed sweep·RT는 **0**. 캐시 재사용과 결과 체크포인트로 중복 실행을 피한다. V2 shadow는 12조건 전체의 유한 packet×4 arm이며 full rerun으로 세지 않는다. 추가 short fork·gamma sweep·새 seed는 이 초안의 기본 실행 범위가 아니다.

## 5. source/수치 품질 관문
숫자는 설계 허용오차이며 아직 통과한 결과가 아니다. 단위·검사 정의는 config와 02 문서가 함께 고정된다.
- 원본 H/pose/fgrid/CONTROL/평균/R/마스크 키·sha 확인; 허위 대체·누락·중복·port swap·time shift는 fail-close.
- H→r: abs<=1e-9m, H→s: abs<=1e-12, tap/port integer **exact**; 무효 관측은 이유·전체 분모에 남김.
- baseline 전체 x/P/innovation/gate를 원본과 대조; wrap-angle로 psi 차이를 계산. identity/matrix 허용오차는 numeric config 참조.
- fixed BASE의 실제 accepted packet 키가 arm별 같아야 한다. 새 eligibility guard를 끼워 넣고 same-mask라고 부르면 FAIL_METHOD.
- 사실상 동일 변수 중복으로 생긴 특이 covariance를 임의 jitter로 가역화 금지. 기존 R_B는 유지하고 이 범위에서 새 R를 학습하지 않는다.
- 학습 label/GT/Full–Direct decomposition은 TRAIN·SCORING·OFFLINE_DIAGNOSTIC으로만 표시. TEST inference에는 GT 금지.

## 6. 해석·중단
기계적 상태는 PASS/FAIL/BLOCKED/NOT_RUN, 과학적 판정은 SUPPORTED/MIXED/NOT_SUPPORTED/INCONCLUSIVE로 따로 쓴다. 기대한 성능 개선이 없어도 정의한 개입과 산출이 맞으면 유효 결과이다. 실패한 case를 제외하거나 stage 결과에 맞춰 threshold·거리 knots·seed·anchor를 변경하지 않는다.

오류는 원 log·입력·부분 산출물과 함께 보존하고, 종속 단계만 중단한다. 비지지 결과는 새 hyperparameter를 찾아 성공시키는 계기가 아니라 04 문서의 주장 변경 규칙으로 처리한다. 계산·과학상 중요한 변경은 새 버전/AMENDMENT와 결과 관찰 여부를 기록한다.

## 7. 후속 동결 조건
다른 구현자는 이 초안으로 무제한 구현/실험을 시작하지 않는다. 별도 사용자 배정 후 source-only V0 preflight 및 구현설계 검토를 요청한다. 실제 입력해시·소스 버전·선택 packet 분모·학습 경로·schema·기준선 parity 타깃·FD active-branch 규칙을 확정한 후보 lock을 제출한다. 제안자 승인과 별도 감사자의 pre-run 서명을 얻은 **새 FROZEN 버전**만 승인된 과학 실행을 허용한다. 현 원고 v4·기존 계약·현재 결과는 그 과정에서 덮어쓰지 않는다.
