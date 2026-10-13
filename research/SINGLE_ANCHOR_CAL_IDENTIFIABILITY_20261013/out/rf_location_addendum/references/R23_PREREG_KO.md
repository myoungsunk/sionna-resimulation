# R2-3 사전등록 — E1 일관성 개선 (noisy-CIR 온라인 E1, fold-wise 잔차 모델, 구조적 시간상관 모델)

실행 전 동결. 선행: R2-2(`R22_ADR_PREREG_KO.md`) 결과로 DR 기준선이 정해진다. R2-2가 `DR_MODEL_MISMATCH_UNRESOLVED`이면 아래 절대 일관성 판정(G3)은 수행하지 않고 상대 비교만 보고한다.

## 데이터·잡음
- 12 케이스의 H_full(P5와 동일 파일), 3 드리프트 레벨, 센서 seed 7000..7031(32개; R2-2의 6000대, P5의 5000/5100대와 분리).
- **seed마다 새 잡음 CIR**: `P.predict`/`observe`와 동일한 잡음 모델(SNR 30 dB 주 조건, 10 dB 보조), 잡음 RNG = `default_rng([20261013, case_idx, seed])`. 검출 임계는 관측기의 `detection_threshold`; 미검출 포즈는 range 갱신 없음.
- E1 계수: P3의 `loro_fold_params[held]['E1']`(학습 fold, noise-free에서 적합; **noisy 특징량에 그대로 적용** = 온라인 시험). 평가 케이스의 route는 학습에서 제외(LORO).
- 한계(명시): RF 다중경로 편향 시리즈는 케이스당 고정이고 잡음만 seed마다 새로 뽑힌다 → 독립 RF 실현은 여전히 12개(`P5_AUDIT_R2_1_KO.md`). 이 한계는 오피스 경로 데이터(`OFFICE_SIM_DATA_REQUEST_SPEC_KO.md`)로만 해소된다.

## 잔차 모델 학습 (fold-wise, 정답 사용 허용 범위 = 학습 route만)
평가 route X에 대해 나머지 2 route의 케이스(8개)에서 별도 잡음 seed(90..93, 4개)로 E1 보정 range 오차 시계열 e(k)=z_E1−d_true를 시간순(dt=0.2 s)으로 만든다.
- σ²_tot = e의 분산(케이스 풀링).
- 자기상관 ρ(l), l=1..10 (시간 간격 기반, 타임스탬프 정렬; 결측 포즈는 쌍에서 제외).
- AR(1)+백색 적합: ρ(l)=(σ_b²/σ²_tot)·φ^l (l≥1), 비선형 최소제곱 → σ_b², φ(τ=−dt/lnφ), σ_w²=σ²_tot−σ_b² (σ_w² 하한 = 양자화 분산).
- IAT_fold = 1 + 2·Σ_{l=1..10} ρ(l) (R 팽창 대조용). 이전 상수 5.8은 폐기.

## 암(arm) — 모두 range-only, `s` 미사용, pose-SMALL prior(R2-2와 동일)
| arm | 내용 |
|---|---|
| A_DR | R2-2에서 확정된 DR 기준선 구성(RF 없음) |
| B0_fixed | 고정 오프셋 B, 기본 R (P5 B_OLD 대응, 잡음 CIR) |
| E1_defR | E1 보정, 기본 R |
| E1_Rvar | E1 + R=σ²_tot(fold) |
| E1_RIAT | E1 + R=σ²_tot×IAT_fold (**R 팽창 대조군** — 해결책으로 인정하지 않음) |
| E1_GM | E1 + 시변 range 편향 1차 가우스–마르코프 상태(σ_b², φ), 백색 R=σ_w² (제안 구조) |
| B0_GM | B 고정 오프셋 + GM 상태(B 잔차로 학습한 σ_b², φ, σ_w²) — 구조 효과와 E1 효과의 분리 |
GM 구현은 7상태 EKF(`gm_ekf.py`). 단위 시험: σ_b²→0일 때 6상태 EKF(R=σ_w²)와 추정치 차이 ≤ 1e-9를 통과해야 결과를 읽는다.

## 지표·판정 (사전 고정)
각 arm·셀(case×drift)에서 앙상블(32 seed): 위치 RMSE, heading RMSE, ANEES(t≥30), pose95 coverage, 정규화 range 혁신 lag-1 상관. 비교는 (case,drift,seed)로 짝지음, CI는 12 케이스 군집 부트스트랩(4000회, seed 20261013). **정확도와 일관성은 별도 판정.**
- **G1 정확도 비열등**: E1_GM 위치 RMSE / E1_defR 위치 RMSE의 CI 상한 < 1.10.
- **G2 일관성 개선**: 지표 d=|ln(ANEES/3)|, d(E1_GM) − d(E1_defR)의 95 % CI 상한 < 0. 추가로 d(E1_GM) < d(E1_RIAT)이면 "구조적 모델이 R 팽창보다 낫다"로 기록(CI 상한 < 0일 때만).
- **G3 절대 일관성(R2-2가 DR 기준선을 찾은 경우에만)**: E1_GM의 케이스 평균 pose95 coverage의 90 % 군집 CI가 [0.92, 0.98]에 전부 포함(TOST, 마진 ±0.03). 통과하지 못하면 `CONSISTENCY_NOT_ESTABLISHED` 유지.
- **G4 동등성 서술 규칙**: "차이가 유의하지 않다"를 "동등/비열등"으로 쓰지 않는다. 동등/비열등은 위의 마진이 있는 검정을 통과한 항목에만 쓴다.
- 판정어: 각 G를 개별로 PASS/FAIL 보고. 종합 `scientific_PASS`는 변경하지 않는다(단일 scene·12 RF 시리즈).
- 결과를 본 뒤 마진·arm·지표를 바꾸지 않는다. 추가 arm은 "사후 탐색"으로 분리.
