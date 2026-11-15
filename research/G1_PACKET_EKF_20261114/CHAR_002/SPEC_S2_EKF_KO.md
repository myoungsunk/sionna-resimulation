# G1-CHAR-002 S2: TEACH/REPEAT 학습 모형으로 R2/R4/R5 궤적 packet EKF 평가 사양 (2026-11-15)

상태: DIAGNOSTIC_ONLY, mount 0. S2′ STOP, Step 3 보류, G-T2/G-V 봉인을 유지한다. 구현과 실행은 사용자가 하며, 이 문서는 실행 전 동결 사양이다.

## 0. 목적과 질문

S1(packet calibration, [REPORT_KO.md](REPORT_KO.md))에서 TEACH/REPEAT로 학습한 오차 모형이 R2/R4/R5에서 과대 보수(coverage 0.985–1.00)임을 확인했다. S2는 같은 학습 모형을 재귀 packet EKF에 넣었을 때 각 궤적에서 다음이 어떻게 되는지 본다.

- **Q1 integrity.** 학습 모형을 넣은 EKF가 궤적별 integrity(Pose95, heading 95% coverage, NEES)를 확보하는가? 이때 packet 단위의 과대 보수가 오차 상관 때문에 상쇄되는지가 핵심이다.
- **Q2 accuracy 비용.** 기존 native O30 + MB_VAR(frozen)보다 heading/XY RMSE를 얼마나 잃거나 얻는가?
- **Q3 heading 조건의 기여.** heading 조건(ψ)과 꼬리(Student-t)가 위 두 질문에 각각 얼마나 기여하는가?

## 1. 학습 전제 (사용자 결정 반영)

- **TEACH/REPEAT의 참값 사용.** TEACH/REPEAT 주행에서는 참 heading과 참 거리가 주어진다고 가정한다. 오차는 아래와 같이 학습한다.
  - e_s = s_meas − h_s(x_true)
  - e_r = r_meas − offset − d_true
  - S1 학습은 이 가정과 같다. LoS 모형 h_s와 RT LoS의 parity가 1e-6이므로 동치다.
- **학습 모수는 S1에서 동결된 값을 그대로 쓴다.** 출처는 `out/FIT.json`(180° 접기, 사전 등록)이다. 360° 수정안 A1은 민감도로만 둔다.
- **학습 scale을 주행 조건에 맞춰 줄이는 규칙은 두지 않는다.** 대신 E5 oracle-scale 진단 arm으로 그 비용을 잰다(§3). TEACH 경로 재설계와, LUT·heading 모듈 분리 학습은 §8 보류 질문으로 남긴다.

## 2. 입력

| 항목 | 출처 | 비고 |
|---|---|---|
| R2/R4/R5 앵커 B, B0, Full, sensor seed10의 online.npz / evaluator.npz | GitHub Release `fp-sc-original-npz-20261108` (6 NPZ, SHA는 `FP_NATIVE_B_CAUSAL_ABLATION_20261108/RELEASE_INPUT_LOCK.json`) | 각 979 / 742 / 1,415 packet |
| FFD bank 2개 | 같은 Release | SHA b29ae471…, 39729fe9… |
| SourceFFD, motion core, W0 재귀, gate | `analysis/fp-native-b-causal-20261108`의 `fp_ns_ablation.py`, `replay_evidence.py` | native 기준선 parity 함수 포함 |
| 학습 모형 | `CHAR_002/out/FIT.json` (SHA는 RUN 계약에 고정) | S1, S2, S3, R1, R2 |

- 앵커 A는 기존 online packet이 없다. 2b 단계(§7)로 미룬다.
- L2(gyro bias 0.20 °/s)는 E0 A2에서 재생성한 controls를 쓸 수 있다. 그렇게 할 경우 B0와 같은 방식으로 추가하며, 추가 여부는 RUN 계약에 적는다.

## 3. arm (사전 고정)

| arm | 거리 관측 모형 | 편파 관측 모형 | 비고 |
|---|---|---|---|
| E0 NATIVE_FROZEN | 기존 muMB_r(t), R_rr(t) | 기존 muMB_s(t), R_ss(t) | 기준선. 기존 trace와 상태·공분산·gate parity 1e-10 확인 후에만 진행 |
| E1 LEARN_D | R1: μ_r(d), σ_r(d) | S1: 평균 0, σ_s(d) | heading 조건 없음 (MB_VAR형) |
| E2 LEARN_PSI_D_GAUSS | R2: μ_r(ψ_f,d), σ_r(ψ_f,d) | S2: 평균 0, σ_s(ψ_f,d) | heading 조건, Gaussian |
| E3 LEARN_PSI_D_T | R2 | S3: Student-t scale(ψ_f,d), ν=2.63. update마다 R_ss를 반복 재가중 | heading 조건 + 꼬리. **1차 arm** |
| E4 LEARN_PSI_D_T_YAWCOR | R2 | S3 + yaw 상관 상태 c_s (φ=exp(−\|Δψ\|/ℓ_ψ), 이동 상관은 0) | ℓ_ψ는 TEACH sweep에서 학습한다(§4.3) |
| E5 ORACLE_SCALE [진단] | R2를 평가 궤적 자체로 재적합 | S3를 평가 궤적 자체로 재적합 | 과대 보수의 비용을 재는 상한이다. integrity/정확도 주장에는 쓰지 않는다 |

공통 규칙은 다음과 같다.

- 관측 함수 h(x)=SourceFFD(h_r, h_s), 운동 모형, Q, 초기 상태·공분산, gate 규칙은 E0와 같다. 바꾸는 것은 관측 평균 보정과 관측 잡음 공분산뿐이다.
- 거리 평균 보정 μ_r는 ranging 수준 보정이므로 Goal 1 허용이다. **s 평균 보정은 어느 arm에도 넣지 않는다.**
- R_rs 교차항은 0으로 둔다. S1 학습에서 교차상관을 추정하지 않았기 때문이다.

## 4. 학습 모형을 EKF에 넣는 방식

### 4.1 조건 변수는 prior 상태에서 계산한다

- packet k에서는 측정 이전 prior x⁻_k = (x, y, ψ, b_g)로 다음을 계산한다.
  - d⁻ = ‖(x, y, z_tag) − anchor‖
  - ψ_f⁻ = (ψ⁻ − bearing(x⁻→anchor)) mod 180°
- 참값, 현재 측정 z_k, 미래 정보는 쓰지 않는다.
- d⁻가 학습 최대 거리 10.89 m를 넘으면 d=10.89에서의 scale에 (d⁻/10.89)^k를 곱해 외삽한다. 외삽 packet은 따로 표시한다.

### 4.2 Student-t 재가중 (E3, E4)

- 혁신 ν_s와 혁신 분산 S_ss = H_s P⁻ H_sᵀ + R_ss로 가중치를 계산한다. w = (ν_t + 1)/(ν_t + ν_s²/S_ss)
- R_ss ← R_ss/w로 바꾸고 S_ss를 다시 계산한다. 이를 3회 반복한 뒤 update한다.
- ν_t=2.63은 S1에서 동결된 값이다. 거리 쪽은 Gaussian(R2)이다.

### 4.3 yaw 상관 상태 (E4)

- **ℓ_ψ 추정.** TEACH station sweep(dense49)에서 e_s의 yaw 자기상관에 지수 모형을 맞춘다. 결과는 `FIT_S2.json`에 동결한다.
- **상태 정의.** c_s를 상태에 추가한다. 분산은 학습 scale², 전이는 c_s,k = φ c_s,k−1 + w, φ = exp(−|ψ⁻_k − ψ⁻_{k−1}|/ℓ_ψ)로 둔다.
- **이동 시 상관.** 이동에 의한 상관은 학습 데이터(TEACH에는 직진 RF pose가 없다)로 식별할 수 없다. 그래서 이동 거리가 0.02 m를 넘는 packet 쌍에서는 φ=0으로 둔다.

## 5. 평가 지표 (궤적 R2/R4/R5 × B0, 그리고 pooled)

| 지표 | 정의 |
|---|---|
| Heading RMSE, XY RMSE | 기존 `metrics`와 같은 정의. 표본 가중 MSE의 제곱근 |
| NEES3 평균 | 3열 pose(x, y, ψ) 기준 |
| Pose95, XY95 | 3D / 2D χ² 95% 포함률 |
| heading 95% coverage | \|ψ̂−ψ\| ≤ 1.96√P_ψψ 비율 |
| 외삽 packet 비율과 그 구간의 Pose95 | §4.1 |
| 구간별 지표 | 직진 / 제자리 회전 / 곡선, 그리고 ψ_f 구간별 heading coverage |

시간 상관을 고려한 불확도는 FP-B 보정과 같은 5 s, 10 s moving-block paired bootstrap(1,500회)으로 E3−E0 차이의 95% 구간을 낸다. 이는 같은 seed10 조건부 구간이며 일반화 구간이 아니다.

## 6. 판정 (사전 등록)

| 판정 | 조건 |
|---|---|
| INTEGRITY_PASS (E3 기준) | pooled Pose95 ≥ 0.90이고, 어느 궤적도 Pose95 < 0.75(심각 실패)가 아니며, pooled heading 95% coverage ≥ 0.90. 옵션 B의 pooled + 궤적별 심각 실패 구조를 따른다 |
| ACCURACY_COST | E3의 pooled heading RMSE가 E0 대비 +10% 이내면 "비용 작음", 그보다 크면 "비용 큼". XY도 같은 기준 |
| HEADING_CONDITION_EFFECT | E2 대 E1, E3 대 E2의 Pose95와 heading RMSE 차이를 bootstrap 구간과 함께 보고한다. 효과 유무는 구간이 0을 포함하는지로만 말한다 |
| OVERCONSERVATISM_COST | E5 대 E3의 heading RMSE 차이. 진단값이며 판정에는 쓰지 않는다 |

결과를 본 뒤 학습 모수, ν, ℓ_ψ, gate, 판정 기준을 바꾸지 않는다. 바꿔야 할 사유가 생기면 새 실행으로 등록한다.

## 7. 단계

1. **2a.** 앵커 B, B0. E0 parity 통과 → E1–E5 실행.
2. **2b (선택).** 앵커 B, L2. controls 재생성 입력이 확보되면 실행한다.
3. **2c (선택).** 앵커 A. 기존 online packet이 없으므로 다음 순서로 진행한다.
   - BLOCK_C `FULL_RF/H_R*_aA_m0.npy`에서 같은 O30 체인으로 z를 만든다.
   - 앵커 B와 같은 sensor seed10, controls를 쓴다.
   - z 생성기 parity를 앵커 B 기존 z와 맞춘 뒤 실행한다.

## 8. 보류된 설계 질문 (S2 결과 후 논의)

- **TEACH 학습의 형태.**
  - (L) TEACH 참값으로 현장 s-LUT 보정을 학습한다. 이는 s 평균 보정이므로 Goal 2다.
  - (H) heading 추정 모듈을 따로 두고, s→ψ 역변환과 그 불확실성을 학습해 EKF에는 의사 heading 관측으로 넣는다.
  - (N) 현재처럼 관측 잡음 모형만 학습한다. Goal 1이다.
- **과대 보수 처리.**
  - TEACH 경로를 주행 조건(직진, 벽 거리)에 맞게 다시 설계한다.
  - 또는 TEACH에서 직진 구간 RF pose를 추가해 ℓ_d와 직진 scale을 직접 학습한다.
- **장면 분리.** BLOCK_C 장면에서 TEACH 경로 RT를 생성하면 장면 효과와 경로 효과를 분리할 수 있다.

## 9. 산출물

`CHAR_002/S2_EKF/`

- `RUN_CONTRACT.json`: 입력 SHA, FIT.json SHA, arm 정의, L2/앵커 A 포함 여부
- `FIT_S2.json`: ℓ_ψ
- `RESULTS.json`
- 궤적별 trace
- `REPORT_KO.md`
