# EKF3 D0–D5 원인 진단 실행 계획 — Flat Detector / 보정 Range / RF Heading (2026-10-13)

**범위:** 진단 코드는 연구 브랜치에 추가하되, 새 시뮬레이션/진단 실행은 사용자가 직접 한다. P0 입력, P1 3-State 수학, P2 저장 RF One-step 결과는 수정하지 않는다. 새로운 숫자는 실제 실행 로그 없이는 결과로 기재하지 않는다. 모든 단계에서 `scientific_PASS=false`.

## 1. 연구 질문과 기존 확정 근거

### Q1. Flat detector가 Range 오차를 대부분 발생시키는가?

**결론의 기준을 구분한다.** 원시 거리 평균오차 분해는 다음과 같다(기존 V04/P2, 12조건 × 16,432 RF-pose):

- `e_flat=r_flat-d_true` 평균 **−0.696194 m**, 표준편차 0.042779 m.
- `e_FFD=r_LoS-r_flat` 평균 **+0.160064 m**, 표준편차 0.046314 m.
- `e_MP=r_Full-r_LoS` 평균 **+0.052460 m**, 표준편차 0.138165 m.
- `e_Full=e_flat+e_FFD+e_MP` 평균 **−0.483670 m**, 표준편차 0.135632 m.
- 이미 적용된 detector+FFD 결합 LoS 평균 오프셋은 **−0.5315983906250129 m**이다. *보정 전 평균*에는 flat detector 성분이 가장 크지만 **보정 후 산포/지속 오차**는 주로 multipath와 측정 관계의 불확실성이다. V04의 e_MP variance share는 1.038, e_LoS 0.117이며 상호 음의 covariance로 합이 1을 넘는다.
- 큰 `e_flat`만을 근거로 `R_s`(편파 기반 Heading 관측)의 오차 대부분이 검출기 때문이라고 단정해서는 안 된다.

**D3 분해는 본문과 같은 이상적 flat 채널을 정답거리 `d_true`로 합성한다. 이는 평가 전용 반사실 채널이며 실시간 필터 입력에 절대 사용하지 않는다.**

### Q2. 개선해야 할 detector/range 관측

- **B_OLD**: 기존 fixed LoS detector offset(−0.5316 m)만 사용. 기준선.
- **C_CONST_LOS**: 독립 route에서 얻은 평균 LoS 보정. 이전 연구에서 기존 fixed offset보다 나아지지 않음. 음성 대조.
- **D1_FRACTIONAL**: 30% leading-edge 직전·직후 샘플 사이의 fractional crossing과 학습 route 기준 D1 LoS offset. 디지털 tap 해상도에 의한 계단식 오차를 줄이는 진단.
- **E1_FULL_LORO**: 학습 route 두 개에서 고정한 P3 Ridge 모델. CIR peak–first tap 간격, peak, first/peak 비율, raw range, mount만 사용하여 Full RF 잔여 편향을 예측. 평가 route 제외 LORO **모델을 그대로 재사용**(재학습 금지). 실시간 추론 특징에는 정답 x/y/Heading/거리 없음.
- **E1_ON_LOS_NEGCTRL**: Full RF용 E1을 LoS에 적용하는 의도적 음성 대조. 기존 검증에서 LoS 과보정으로 RMSE +36~42% (조건별), Full에서는 약 −17% 범위. 실제 LoS 운용 모델로 채택 금지.

**중요:** D1은 검출된 integer first-path tap의 분율 위치를 추정할 뿐, 편파 `s`를 추출한 원래의 공통 tap을 재선택하지 않는다. E1 역시 수신 Range 추정의 편향만 보정한다. 두 방법 모두 **s와 RF Heading 정보 자체를 바꾸는 알고리즘이 아니다.** 따라서 같은 DR prior에서 A(s-only)는 모든 Range 보정 버전에서 **완전히 동일해야 함**.

### Q3. 왜 LoS와 Full RF Heading 차이가 큰가?

- LoS: 직접 전파파만 있고 FFD/기하 기반 `h_s(x,y,psi)`에 상대적으로 가까움.
- Full: 직접파 + 반사·산란 성분의 복소 합; LP 포트별 반사 편파 응답, 위상 간섭, 지연로브/first-path crossing 변화가 생김.
- 진단 분해 1: `s_Full-h_LUT(true)=(s_Full-s_LoS)+(s_LoS-h_LUT(true))`. 각각 multipath/channel 효과와 LoS-LUT 예측 불일치를 분리.
- 진단 분해 2 (**검출 tap 선택 효과를 더 정확히 식별**): `s_Full(tap_Full)-s_LoS(tap_LoS) = [s_Full(tap_Full)-s_Full(tap_LoS)] + [s_Full(tap_LoS)-s_LoS(tap_LoS)]`. 첫 항은 **Full H 내 tap 위치 변화**에 따른 s 변화, 둘째 항은 **동일 tap에서 Full–LoS 채널 간섭/편파 변화**. 두 번째 항이 클 경우 detector의 integer tap 시점이 같아도 s/Heading이 다를 수 있다. `s_Full(tap_LoS)`는 LoS tap을 알아야 하므로 오직 offline oracle-free counterfactual 분석에만 사용하고 온라인 품질 판단에 직접 사용하지 않는다.
- 진단 분해 3: `nu_s=(s_Full-s_LoS)+(s_LoS-h(true))+(h(true)-h(xprior))`. 다중경로 모델오차·기준 LUT 오차·상태 예측 오차의 차이를 분리한다. Truth는 offline 평가에만 사용.
- 측정 이득 `K_psi,s = (P_psi,x h_x +P_psi,y h_y+P_psi,psi h_psi)/S_s`을 각 항으로 분해. **s error가 크다는 사실만으로 heading gain이 커지는 것은 아니며** EKF prior geometry와 Jacobian에 따라 전파되는 보정량이 달라진다.

## 2. 진단 게이트·실행 순서

### D0 — 입력 계보·오차항등식 동결

입력: [Actions 38331588521 artifact](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38331588521/artifacts/11782748118)의 `P2_OUT`, 원 P0 39개 파일, 원 P3 frozen model SHA256 `10fdb76f0fe0236400afd10cd53d79845582182a79151bec390d3ea968ceca95`.

- `P2_ONE_STEP_SUMMARY.json` SHA-256이 `P2_RUN_RECEIPT.json`의 값과 일치해야 함.
- 14개 `*_ONE_STEP.npz` 각각 summary 기록 해시와 일치해야 함.
- original Full/LoS H 및 RF SAMPLES.json SHA-256, source observation parity, shared DR prior, timestamp/pose_id 유효성 검사.
- B_OLD 수정 재생으로 **기존 P2의 B/C xplus, H, R, S, K, Pplus/Gate** 수치 동일성 점검. 다르면 즉시 중단.
- Flat+FFD+MP 거리 잔차 합과 Full–LoS–LUT s 잔차 합 및 tap/same-tap 기여 합 항등식 오차 ≤ 1e-9.
- 같은 case/full/los의 `s/r` 수신 출력이 원 P2와 일치해야 함.

### D1 — 공분산 과신 여부 '진짜' 판정

`NEES_pose=eᵀP^{-1}e`와 `NEES_yaw=e_ψ²/P_ψψ`, 정확한 Schur `NEES_xy|yaw`, χ² 95% pose(7.8147) 및 yaw(3.8415) 포함률, 사후·사전 P 비교.

단일 noise_pair seed의 NIS/NEES는 기술통계다. 단순히 C의 Pplus가 A/B보다 작고 실제 RMSE가 크다는 이유로 과신을 확증하지 않는다. 여러 seed/공간 위치/새 RF scene에서 검증 필요.

### D2 — Heading 보정 악화 원인·Gain 경로 분해

- A: `Δψ=K_ψs ν_s`.
- B: `Δψ=K_ψr ν_r` (Range의 Hψ=0이라도 위치–Heading cross P로 yaw gain 발생).
- C: `Δψ=K_ψs ν_s+K_ψr ν_r`; 매 시점 numerical identity 검사.
- 실제 heading 오차의 제곱 변화: `(e^-+Δψ)^2−(e^-)²=2e^-Δψ+(Δψ)^2`. C에서는 RF(s), Range(r), 교차항을 모두 저장.
- Gate가 REJECT이면 적용 보정량은 0으로 기록하고, 진단용 Gain/Innovation은 별도 보관. Wrapped heading 경계에서 제곱식 항등식이 직접 성립하지 않는 샘플은 `squared_identity_valid=0`으로 플래그.

### D3 — Full vs LoS 전파·검출 원인 분해

거리와 tap 변화, `e_flat/e_FFD/e_MP`, Full–LoS `s`, LoS–LUT `s`, 동일 tap channel 효과 및 tap selection 효과를 case·mount·거리 bin으로 점검. 원인 후보는 direct/reflect polarization mixing, detector tap switch, near-pole LUT angular ill-conditioning, RF slope hψ 등. 모든 matched sample을 보존하고 진단 편의를 위해 bad sample을 제외하지 않는다.

### D4 — 보정 Range를 실제 같은-prior One-step에 주입

R0 `R_r=0.0068578637m²`, `R_s=0.0081`, `R_sr=0`와 Gate를 **고정**. Range만 B/C에 교체하며 `A`는 원본 유지. 이 실험은 **mean-correction ablation**으로서 조건부 R을 검증한 것이 아니다.

평가: Range 잔차 평균/SD/RMS, 거리 bin별 RMS²/R0, Heading·XY RMSE, pose/yaw NEES, Schur NEES, coverage, NIS–Heading 악화 비율, Range/s 잔차 ACF·상관관계. **E1의 LoS 악화는 사전 기록된 음성 대조군**.

### D5 — 여러 seed/DR 오차 수준에서 유익성 검증 (별도 사용자 실행)

P0 개발 seed 0–19와 확증 seed 10000–10049, `noise_pair` 및 `all` (drift 0/1/2), Frozen LoS/Full RF의 7 case, 동일 initial pose·wheel/gyro stream을 D0/A/B/C에 재사용. 여기서는 **각 arm posterior를 다음 시점으로 재귀 전달하는 full-route** 비교를 구현.

- R0와 E1만 Full RF에서 비교(LoS E1 과보정은 D4 음성 대조까지만).
- `all`에서 Gyro bias, gyro SF, Wheel asymmetry/slip은 3-State에 없는 **실제 생성 오차**로 남는다.
- Seed 반복은 같은 H와 같은 scene의 sensor noise/initial pose만 바꾸므로 **독립 RF site/environment 검증이 아님**.
- Heading/XY RMSE, NEES, coverage, accepted-heading-improvement 비율, 불리한 업데이트·구간별 진단. 이후 품질 기반 센서 선택 정책은 독립 검증을 거친 뒤 별도 단계에서 결정한다.

## 3. 평가 방법의 함정과 방지

1. **LORO와 중복 XY**: P3 계수는 평가 route를 제외한 fold에서 고정됐으나 기존 연구에서 교차 route가 공유한 XY 한 곳이 학습에 남은 제한이 있다. 그 위치의 성능을 독립 공간 일반화로 읽지 않는다. 진단은 기술통계로만 승인한다.
2. **조건부 오차 상관**: Range/s/시간 상관이 있고, 같은 site의 RF H는 seed마다 재생하지 않는다. 시점×seed 개수를 독립 RF 환경 표본수로 주장하지 않는다.
3. **R 보정 누락**: D4의 corrected-range도 기존 R0를 그대로 쓰므로 개선/악화를 보더라도 일관성이 확립되었다는 뜻이 아니다. 평균 편향 교정과 분산 모델 교정은 이후 분리 검증할 과제.
4. **진짜 absolute Heading 조건**: 역 LUT로 만든 Heading을 독립 센서처럼 취급하지 않는다. 첫 공식 분석은 Full spatial Jacobian `H_s=[h_x,h_y,h_ψ]`로 직접 `s`를 사용한다.
5. **최적화 금지**: 이 단계는 원인 진단. 범위/게이트/사후 선택 기준을 결과를 보고 임의 변경하지 않음. Truth로 '좋은 업데이트'만 선택하면 oracle.
6. **모델 범위**: 한 복도의 single anchor 주행, frozen 7 conditions. 2026-10-13 신규 Office scene에서 E1 Full RF range transfer 근거는 있지만 독립 EKF/s 성능이 아니다.

## 4. 코드와 산출물

- `E1_P3_FROZEN_LORO_20261012.json`: 원래 P3 frozen coefficients 원문 고정 복제, 독립 route fold 그대로 사용.
- `p3_compat.py`: P3의 online CIN/CIR feature, D1 fractional crossing, E1 ridge prediction **NumPy-only**. 원래 observer 함수 읽기 전용 재사용.
- `run_d0_d4.py`: 기존 P2 trace와 실제 H/LUT를 연결. D0 SHA 재검증, B0 parity, D1/D2 NEES–Heading Gain, D3 flat+FFD+MP 및 tap/same-tap, D4 보정 Range one-step replay.
- `run_d5_regimes.py`: 여러 seed, drift, correction scheme로 D0/A/B/C **재귀 Full-route**.
- `test_diagnostics.py`: 고정 모델·관측·보정·NEES·온라인 입력 계약 테스트(사용자 실행).
- 출력: `D0_D1_METRICS.csv`, `D2_HEADING_DECOMPOSITION.csv.gz`, `D3_FLAT_FFD_MP_AND_POLARIZATION.csv.gz`, `D4_RANGE_RESIDUAL_BY_DISTANCE.csv`, `D4_S_RESIDUAL_BY_DISTANCE.csv`, `D4_NIS_VS_HEADING_HARM.csv`, `D4_CROSS_CHANNEL_AND_TEMPORAL_AUDIT.csv`, `D0_D4_ARM_SUMMARY_DESCRIPTIVE.csv`, `D0_D4_RUN_MANIFEST.json`.
- D5 출력: `D5_MULTI_SEED_FULL_ROUTE_METRICS.csv`, `D5_RUN_MANIFEST.json` 및 선택적 Full Trace CSV.

## 5. 판정

| Gate | 완료 조건 |
|---|---|
| D0 | SHA / observer / P2 B0 matrix parity 및 두 개의 causal error identity PASS |
| D1 | heading/pose/conditional XY NEES 계산, 독립성 제한 명시 |
| D2 | A/B/C gain×innovation sum identity PASS |
| D3 | Flat+FFD+MP 및 Full–LoS s tap-selection vs channel-interference identity PASS |
| D4 | B0/D1/E1를 **같은 DR prior**에 주입, RF s 변경 없음 검증, 결과 저장 |
| D5 | 독립 IMU 센서 seed, drift 조건, 재귀 D0/A/B/C 비교; 외부 RF scene 검증과 구분 |

현재는 **코드만 커밋, 사용자 실행 미수행, 모든 진단 결과 NOT_RUN, scientific_PASS=false**. 실패를 PASS로 처리하거나 미검증 모델을 production에 반영하지 않는다.
