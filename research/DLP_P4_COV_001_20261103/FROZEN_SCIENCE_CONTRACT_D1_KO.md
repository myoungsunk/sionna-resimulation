# DLP-P4-COV-001 — D1 공분산 과신 분해 과학 계약 (PROPOSER FROZEN SPEC)

**Contract ID:** DLP-P4-COV-001 / D1-V1
**Role:** PROPOSER
**Scientific base / governance reference SHA:** e365b2f79eb86a3fd53d0d350f8e2d9364f285fe
**Status:** FROZEN_SPEC — INDEPENDENT_AUDITOR_PRE_RUN_PENDING
**Authorized scope after independent GO:** D1 read-only diagnostics only.
**Earlier exploratory results:** Seen before design freeze; C0+ single-scene retrospective only.
**Change policy:** New amendment ID and new audit; never edit signed/hashed frozen bytes.

## 1. 목적과 판정 범위

동일한 R4에서 ABC Native LoS의 위치 신뢰도 포함률과 ABC Full의 포함률 차이를 state error와 2D 위치 공분산으로 분해한다. R2/R4/R5에 대해 세 번째 앵커 추가의 XY 정확도와 공분산 신뢰도 효과가 일치하거나 역전하는 사실을 전수 기록한다. D1은 물리적 RF 원인, R 과소설정, ACF 인과효과, joint gate의 반사실적 AB 손실을 새로 검정하지 않는다. H1–H6의 지지 판정은 D2–D4 후로 보류한다.

## 2. 데이터·독립성·중단 조건

- 원본 sha: 과거 P4 실행 83b80299b42a1ea5e0794f2b26a4db512cff7367, 결과 base e365b2f79eb86a3fd53d0d350f8e2d9364f285fe; 원본 12 trace ZIP SHA-256 5ecf2a326ec17c8ce4ccc7a42fe76227ecf6ad7ec027df9cdfcd2304dcb0acfe. 자세한 모든 파일·Actions ID는 INPUT_SOURCE_LOCK.json으로 고정한다.
- 오프라인 정확한 GT는 과거 EKF3 #38331588521 원본 float64 truth_for_offline_scoring_only. P1의 6자리 반올림 GT로 엄격 NEES 재현을 대체할 수 없다. 동일 route/pose_id/t_s와 원래 timeline SHA로 교차 검증한다.
- R2 979(평가 829), R4 742(592), R5 1415(1265). 평가 t>=30s; route 3 × channel los/full 2 × bias B0/L2 2 × arm 7 = 84개, 12 NPZ. 한 채널·bias·arm의 경로 합산 n_eval=2686. 총 scored arm-epoch 75208. 원본의 실패·gate 거절도 절대 삭제하지 않는다.
- 비교 단위는 동일 route/time/pose/bias/observer, 독립 실험 단위는 **Corridor C0+ 장면 1개**. 시점·seed·route·anchor는 독립 scene replicate가 아니다. 독립 장면 CI, 보편적 확률 보정 주장, p-value 계산 금지.
- D0 구현자 산술 parity는 원본 재현의 근거이며 D1 감사 서명은 아니다. 실패한 SHA·경로·조건·trace key 하나라도 있으면 전체 D1 BLOCKED_INPUT; 그 조건만 삭제 후 계속 금지.

## 3. 고정된 물리·확률량

원래 상태는 x=[x(m),y(m),psi(rad),b_g(rad/s)]ᵀ, 원래 posterior P는 4×4. 포즈의 GT 오차는 e=[xhat−xGT, yhat−yGT, wrap(psi_hat−psi_GT)]ᵀ. 원래 P의 XY marginal A=P[0:2,0:2], pose marginal B=P[0:3,0:3], heading marginal c=P[2,2]. b_g는 3DOF pose NEES에 포함하지 않는다. 사후 공분산은 조건부 bg 제거가 아니라 **4D posterior에서 취한 marginal**이다.

- XY-only: NEES_xy = e_xyᵀ A⁻¹ e_xy; XY95 = mean(NEES_xy <= 5.991464547107979) [2-DOF].
- Heading-only: NEES_heading = e_psi²/c; Heading95 = mean(NEES_heading <= 3.841458820694124) [1-DOF].
- Pose joint: NEES_pose=eᵀ B⁻¹ e; Pose95=mean(NEES_pose <= 7.814727903251179) [3-DOF].
- 정확한 Schur 분해: B=[[A,b],[bᵀ,c]], s=c−bᵀ A⁻¹ b, r=e_psi−bᵀ A⁻¹ e_xy. NEES_pose = NEES_xy + r²/s. 조건부 heading r²/s는 heading marginal NEES_heading와 **다르다**.
- 위치 RMSE_xy = sqrt(mean(e_x²+e_y²)), Heading RMSE는 wrap 후 rad→deg. signed e_x/e_y 평균을 계산하며 Pxy 대칭·SPD 검사를 통과해야 한다.
- Pxy eigenvalue 오름차순 λmin/λmax; 1σ 단축/장축 sqrt(λmin/max) [m], 장축 각도는 180° 주기의 축(벡터 부호 무관). 실제 e_xy의 장축/단축 projection과, e_xy≠0일 때 장축과 이루는 0–90° 각도를 기록한다. e_xy=0이면 angle=null.
- 95% 타원 축 길이를 제시할 때 1σ 축과 혼동하지 않고 각 축에 sqrt(5.991464547107979)를 곱한다. 직접 XY95는 위의 Mahalanobis gate로 평가한다.

## 4. D1 산출·표본·비교 방법

(A) 84 case 전수: XY/Heading/Pose RMSE·NEES·coverage, signed XY bias, 1σ 타원 축·방향·실제 오차의 대응과 전체 원본 상태·status.
(B) 원래 scored 각 epoch 전수: route, channel, bias, arm, pose_id, t_s, state error, Pxy λ·고유벡터 orientation, 3개 NEES, Schur conditional heading, 3개 coverage bool, gate status. 원본 x/P만 읽기; Kalman gain 재개입 금지.
(C) window: 10/20/40 s **비중첩 고정 창을 각각 따로** t=30 s에서 시작하여 [30+jw,30+(j+1)w)로 집계. 마지막 부분창은 n을 표시하고 유지하며 n=0 창만 생성하지 않음. 같은 표본을 다중 창폭으로 본 것이지 추가 독립실험 아님.
(D) 동일 route/channel/bias/t_s/pose_id에서 기존 AB vs ABC, 동일 route/bias/arm/t_s/pose_id에서 Full vs Native LoS **기존 posterior**의 XY error norm, Pxy λ, NEES, coverage 차이를 paired 비교. 요인 통제하의 기술 비교이지 단일변수 D4 개입 아님.
(E) R4 Full/LoS 각 bias arm에서 t>=30 첫 XY95 실패시점, 그리고 25개 연속 평가 epoch 모두 XY95 밖인 최초 구간을 식별(없으면 NOT_FOUND). 조건별 failure run length와 Pxy 과신 시계열을 작성한다. 25 epoch는 0.2s 간격에서 약 5 s이지만 샘플 연속성은 실제 t/pose 정합으로 검사한다.

## 5. 사전 QA와 허용오차 (fail closed)

- 세 원본 ZIP/GT SHA와 원본 P4 내부 12 trace ZIP 해시를 직접 검증. 12 trace 중 하나라도 누락·중복·시간/pose 불일치 → STOP. case key 84개, 모든 성적표 행은 원본 score t>=30을 사용.
- D0를 읽기 전용으로 재검증: 기존 84 case XY RMSE·Heading RMSE·heading/pose NEES·coverage를 GT로 재계산, 최대 절대차 <=1e−9, counts/keys exact. 다른 GT/source를 대체하지 말 것.
- covariance: symmetric abs tol=1e−10, finite, SPD Cholesky 필수. 임의 diagonal jitter, eigenvalue clipping, 이상행 삭제 금지. 실패 -> ledger 및 BLOCKED_INPUT.
- pose joint vs XY+Schur 잔차: |delta| <= max(1e−8,1e−10·|NEES_pose|), 모든 scored epoch. 부동소수점 조건수가 크면 수치 불안정 기록 후 막되 판정 경계 조정 금지.
- time join abs <=1e−9s, route n / scored n exact. root source and D1 numeric config both SHA256 checked. source hash mismatch -> BLOCKED.
- 95% coverage는 <= (경계 포함), 범위 [0,1], window aggregate weighted count consistency and 84-case counts closed. 모든 window/route/Full/LoS/B0/L2 포함.
- D1의 '이유' 결론은 상태오차 대 공분산 불일치의 양상까지만 허용. 물리적 다중경로 원인과 gate 반사실적 효과는 D2/D3에서 분리해야 한다.

## 6. 산출물, 실패 기록, 재현

Append-only root: research/DLP_P4_COV_001_20261103/D1_RUNS/<run_id>/.

필수: D1_MANIFEST.json, INPUT_SHA256_VERIFIED.json, D1_QA.json, D1_EXECUTION_LOG.txt, ROUTE_STATE_COVERAGE.csv(84 case), EPOCH_STATE_COVARIANCE.csv(75208 scored arm-epochs), TIME_WINDOW_COVERAGE.csv(10/20/40s), MATCHED_AB_ABC_AND_FULL_LOS.csv, ONSET_R4_COVERAGE.csv, FAILURE_COUNTEREXAMPLE_LEDGER.csv, D1_STATE_COV_REPORT_KO.md. 코드 Git SHA, source SHA, exact command and python/numpy/platform, timestamps, independent_scene_count=1, 모든 원래 반례 포함. 결측/부적합 시 빈 성공 파일을 만들지 말고 FAIL와 이유 기록.

## 7. 단계 권한과 연구 결론

- D1 전: PROPOSER_FROZEN_SPEC만으로 실행 금지. 별도 세션/주체 AUDITOR의 해시 고정 문서 검토·독립 수학 사전검사, 서명한 GO_D1 필요. 사용자의 이번 지시는 **GO_D1 이후 D1 실행을 승인**한 것이며 감사 서명 대체가 아니다.
- D1 수행자는 새로운 covariance/gate/R/replay/multipath 변형을 만들지 않는다.
- D1 산출 결과 후 별도 독립 사후 감사. D2/D3/D4는 각 단계 별도 동결/승인 이후 진행; 현재는 NOT_AUTHORIZED.
- 기존 exploratory 결과가 지표 이상을 사전에 보여주므로 D1 확인은 retrospective diagnostic consistency만 허용. 다중경로 평균/시간상관과 Kalman gain의 인과 사슬은 D2–D4의 직접 검증을 기다린다.

**PROPOSER 서명 범위:** 과학 계약·지표·중단 규정만 확정. **AUDITOR 서명:** PENDING. **D1 실행:** NOT_STARTED.
