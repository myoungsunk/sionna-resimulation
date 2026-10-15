# R5-PHY B0 중심 Hard/Soft 정책 감사·실행 계약 — 2026-10-15

**기준 소스:** `b437fd154a9cf38f6b0bfe11a21c59ca63e0b25e` PHYSICS_RS_STAGED 2026-10-15 A/B/C. 앞선 R5 연구 기준선과 별도 분기. 기존 R0/J4/S4/SR4, LoS LUT, RF/gyro 입력, 테스트 데이터 덮어쓰기 금지.

## 0. 사전 사실
- Physics G5 R_s-only는 **이미 실행**했고 R2 Full Mount0 B0 J4 7.4900°→G5 4.3038°이었으나 Mount45 0.8450°→1.3488°로 악화. L2 Mount0 Pose NEES 297.85→2787.35로 악화. 따라서 G5 성능을 신규 Hard/Soft 성공으로 오인하지 말 것.
- 이전 R5의 AUROC 0.8446은 `|s_Full−s_directLoS|>0.1` 프록시의 랭킹 면적이지 **84.46% 관측별 검출 확률이 아니다.**
- B0 true gyro bias=0°/s. 필터 상태 x=[x,y,ψ,b_g], bias 추정값은 **동결하지 않음**. Zero-bias에서 거짓 b 추정은 결과의 핵심.
- Original R2 one-step archive SHA256 `88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63`, validated recursive R2 ZIP SHA256 `ac98c5b50077484f10bb3898138c46115d4921ac099753c5f935db33521da399`. B0 Original seed0, mount0/45, LoS/Full.
- G3/G5의 복소 채널 주파수 Jones 관련 지표는 DWM1000에서 현재 획득이 확인되지 않았으므로 **research-only**. G0=range/s/first-path power는 추후 하드웨어 가용성 확인.

## 1. 데이터 구조·누설 차단
- P0 manifest에 등록된 7개 원본 RF H Full/LoS(총 14개), 같은 case SAMPLES, freq, frozen LUT/observer, R2 archived trace만 사용. 모든 입력 SHA256/Git blob audit-first; mismatch이면 계산 금지.
- 관측은 H에서 원래 FP observer와 동일하게 재구성, archived `z_s,z_r`와 4개 R2 trace 전수 parity 검사.
- 학습: R4+R5 두 route만. 테스트: R2의 모두(원본 3 case), 최종 재귀 R2 Anchor A mount0/45만. Route R2의 oracle/GT/e_MP/e_total/Heading 결과는 모델/threshold 선택에 사용 금지.
- Train R4/R5의 XY가 R2 test XY와 1e−4m 이내면 제외. train/test는 동일 복도의 경로 구분이며 independent-scene 아님.
- 연관 features: G0/G3/G4/G5를 physics`features.py` 정의 그대로 사용. 복합결과에 G3의 비하드웨어 현실성 명시.
- Regression target은 `e_total=s_meas-h_LUT(x_true)` signed/second moment, train truth **offline training only**. 학습된 모델은 RF 관측·자이로·사전상태 외의 GT를 필터에 사용하지 않음. Classification target `|s_Full−s_directLoS|>0.1`은 oracle training label일 뿐 Heading error GT와 혼동 금지.

## 2. 사전고정 비교군
- `DR4`, `R0_J4`: 원래 코드 기준선.
- `SOFT_G0_RS`, `SOFT_G4_RS`, `SOFT_G5_RS`: Physics 방식과 동일한 `R_eff=clip(E[e_total²|q], .0081, .81)` 및 original joint NIS gate.
- `SOFT_G5_MEAN`: 부호 있는 `μ_s(q)`를 관측 s에서 차감하되 R0 유지.
- `SOFT_G5_MEAN_RS`: μ_s 보정 + G5 Rs 변경. 두 모델의 잔차 상관에 따른 보정 과신은 NEES로 검증.
- `HARD_ALL_G5_p50`, `HARD_ALL_G5_p75`: 훈련 R4/R5에서 fit한 |eMP|>0.1 확률 proxy `p_bad(q)`가 각각 0.50/0.75 넘으면 전체 RF 업데이트 보류; 아니면 R0 J4.
- `HARD_S_G5_p50`, `HARD_S_G5_p75`: high risk이면 s만 보류하고 Range-only gated update, 아니면 R0 J4.
- `HARD_S_G0_p50`: 비교적 단순 관측 특징으로 같은 정책.
- `HARD_S_G5_p50_RANDOM_MATCH`: 관측 보류 개수를 test case에서만 맞춘 난수 대조(사후 진단, 배포 불가). s 보류 자체 vs q 선택 효과 분리.
- 모든 정상/차단 정책에서 B0 bias state 유지, gyro 측정 동일, 초기 perturbation·공분산 동일.

## 3. 필수 코드·물리 감사
1. 원본 파일·LUT·observer/R0와 PHYSICS `features.py`의 정확한 SHA.
2. FP tap, stronger branch, Hann/4N IFFT, port order, range+ s 측정 14,502 원본 parity.
3. G5 학습 분리(train R4/R5, R2 holdout), PHY predictor whitelist, scientific oracle leakage 없음.
4. soft mean 모델 및 R_eff PSD, σ_s floor/cap, q probability 0–1, gate 99% χ² joint vs scalar.
5. Hard_ALL은 R+s 둘 다 보류; Hard_S는 R-only 유지. 실패하는 관측이 아니라 **feature-prior policy** 결정이 원인임을 분리할 것.
6. E2E original R0 J4 vs archived B0 trace/legacy exact algorithm (baseline 수치 차이 있으면 숨기지 말 것).
7. NO GT in B0 filter; RF scanned factors unused; no packet duplication.
8. 한 복도·zero-noise RF 및 Gyro Bias seed0라는 범위 기록.

## 4. 평가·판정
- B0 Full Mount0 **primary**, B0 Full Mount45 **mandatory non-harm guard**; LoS mount0/45은 false reject guard.
- Heading RMSE, signed error, σψ, Heading NEES/95coverage, Pose RMSE/NEES/95coverage, wrong-high-confidence rate, b_g final/RMSE/coverage, packets RF rejected/s omitted/r-only, q decision %, accepted count.
- Bias state B0에 spurious b bias가 발생하는가. G5-R_s-only/Hard/Mean correction이 이에 미치는 효과.
- 알고리즘 실행과 독립 truth-only scorer, 원본 LoS/FULL pairing, seed/case/commit ID/sha, full per-time raw x/P output. 작은 RMSE와 심한 Pose overconfidence는 별개.
- Mount0가 나아도 Mount45 악화/XY covariance 악화면 **전역 정책 채택 실패**로 표시; 탐색적 개선으로만 보존.
- 최종 결과는 `GO_INTO_HEADING_VALIDATION`, `PARTIAL_ONLY`, `HOLD`로 한정, 이 실행만으로 R5 Active Gradient나 장면 일반화 완료 아님.

## 5. 다음 단계 연계
Hard/Soft 결과를 기존 R5-4 유한 yaw shape/gradient oracle와 결합 검증할 때는 현재 연구용 q가 DWM1000에서 실제 관측 가능한지 먼저 확인. 기존 H에서 angular Full 계산/GT를 RF packet으로 재사용하지 않음. 차분에 FP tap switch/2° LUT kink/gyro uncertainty/position lever arm 정보를 반드시 추가. 
