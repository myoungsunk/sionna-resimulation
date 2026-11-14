# G1-DIAG-003 — 기존 RT(BLOCK_C 연속 주행)에서 packet 단위 EKF의 integrity 실패 기전 분리 사양서

- 작성: 2026-11-14 KST. 상태: **SPEC_DRAFT / NOT_RUN / DIAGNOSTIC_ONLY**
- 갈래: **기존 데이터 갈래.** 새 RT 갈래는 [SPEC_B_NEW_RT_KO.md](SPEC_B_NEW_RT_KO.md)(G1-MODEL-003)다.
- 배경: G1-FLOOR-001 → G1-MODEL-001/002는 sweep 전체로 station heading 1개를 맞추는 추정기를 썼다. 원래 접근(packet 단위 재귀 EKF)과 다르다. S2′ STOP, K1–K6, K9/K10, E1/c_L은 이 사양의 근거로 쓰지 않는다. K7·K8·tap 진단의 **기전**만 가설로 이월한다.
- 주장 경계: 모든 결과는 `DIAGNOSTIC_ONLY`다. 여기서 얻은 수치(분산, 상관길이, 편향, 표 값)는 G1-MODEL-003의 모수로 옮기지 않는다. 이 사양의 결과는 G1-MODEL-003의 **arm 우선순위와 S2 특성화 항목**을 정하는 데만 쓴다.

## 0. 질문

| Q | 질문 |
|---|---|
| QA1 | 원래 J4(백색 R)의 Full RF integrity 실패는 **packet 간 상관을 독립으로 센 것**인가, **경로 길이만큼 지속되는 s 평균 편향**인가, 둘 다인가? |
| QA2 | s 오차 e_MP = s_full − s_LoS의 공간 구조는 어떤가? 이동거리 상관길이, 회전(yaw) 상관, 장거리(≥ 5 m) 평균 성분의 몫은? |
| QA3 | range만 쓰는 4-state(R4) 대비 J4의 차이, 즉 편파의 순수 기여는 얼마인가? |
| QA4 | 분산만 키우는 Goal 1 처리(거리 의존 편파 분산, MB_VAR의 분산 부분)로 integrity가 회복되는가? |

## 1. Goal 1 경계 (연구자 확정, 2026-11-14)

| 허용 (Goal 1) | 제외 (Goal 2) |
|---|---|
| ranging multipath 완화: 첫 경로 검출 규칙, range 평균 보정 | s 평균 편향 보정(μ_s 학습·차감, BB_ORIG/POWER 계열의 편파 평균) |
| 오차의 불확도 표현: 상관 상태, Schmidt/consider, 분산 스케일, 거리 의존 분산, 꼬리 | 반사 경로를 명시한 편파 관측 모델 |
| ranging 규칙을 **거리 오차만으로** 고르고 s를 그 tap에서 읽기 | 오염 감지에 기반한 s 가중·기각, heading/s 오차로 tap 규칙 선택 |

이 사양의 oracle 항목(D3)은 원인 분리용이며 어느 쪽 모델로도 채택하지 않는다.

## 2. 입력 (고정)

| 항목 | 위치 | 비고 |
|---|---|---|
| EKF4 코드 | `analysis/b-mcg-v1-20261109`: `research/EKF4_RANGE_S_STAGED_20261014/` (`core.py`, `r2_bias_replay.py`, `r2_bias_score.py`, `test_r2_bias.py`) | 수정하지 않고 복사한다. arm은 flag로만 추가 |
| R2_aA 연속 주행 RF | Actions artifact `11782748118` (archive SHA-256 `88b0e89e…ecd63`) | 워크플로 `ekf4-r2-bias-l012.yml`과 같은 방식으로 받는다 |
| R2 결과 기준 | artifact `11940333419` (run 38664617622), 문서 `R2_MOUNT0_45_GYRO_BIAS_B0_L0_L1_L2_RESULTS_20261015_KO.md` | 회귀 기준 |
| Anchor B JOINT4 | `research/PJ_SEPARATE_RS_20261020/experiment.py`, Actions run 39376076166 | R4-B·R5-B 회귀 기준 |
| mount | **0°만** (연구자 결정). 원래 자료의 mount 45 행은 회귀 대조로만 재현하고 해석에 쓰지 않는다 | |

artifact를 받을 수 없으면(만료·권한) 중단하고 `INPUT_MISSING`을 기록한다. 원본 생성 코드로 RF를 다시 만드는 것은 별도 승인 항목이다.

## 3. 공통 설정

- 추정기: 원래 4-state [x, y, ψ, b_g] 재귀 EKF, Joseph 갱신, heading wrap. gate는 원래 값(S: χ²₁ 99%, J: χ²₂ 99%).
- DR 시나리오: Sensor-v2 B0/L0/L1/L2 = 0, +0.01, +0.05, +0.20 °/s.
  - S0 회귀는 원래대로 sensor seed 0, 양의 부호만 쓴다.
  - D1–D6은 sensor seed 0–19와 부호 ±를 쓴다. 단, L 수준 정의는 바꾸지 않는다.
- 평가: t ≥ 30 s. frame 지표와 함께, 고정 checkpoint(§3.1)에서의 ensemble 지표를 낸다.
- 지표: heading(1 dof), XY(2 dof), b_g(1 dof)를 따로 낸다. 각각 RMSE, 평균 NEES, 명목 95% 포함률, gate 기각률을 낸다.

### 3.1 checkpoint와 독립 단위

- checkpoint는 경로를 따라 1 m 간격으로 둔다(시각은 가장 가까운 frame).
- 독립 단위(site): 1 m 구간. 같은 site 안의 checkpoint는 하나의 군집으로 본다.
- CI는 sensor seed와 site를 함께 재표집하는 2단계 bootstrap(B = 2,000)으로 낸다.

## 4. 진단 항목

### S0. 회귀 재현 (선행, 실패 시 전체 중단)

| 항목 | 기준 |
|---|---|
| R2_aA B0 DR-only x·P | 원래 기준과 최대 차이 0 |
| R2_aA DR heading RMSE L0/L1/L2 | 1.69 / 6.59 / 24.97° |
| R2_aA J4 mount 0 LoS | 0.50 / 0.40 / 0.24° (L0/L1/L2) |
| R2_aA J4 mount 0 Full | 7.50 / 7.54 / 7.52° |
| L2 Full mount 0 J4 | heading 포함률 16.3%, NEES 86.37 |
| L2 b_g 최종 추정 4개 | 문서 값과 일치 |
| Anchor B JOINT4 Full | R4-B heading 1.323°, 포함률 40%. R5-B 2.541°, 22.1% |

수치는 원래 보고 자릿수까지 일치해야 한다. 원 artifact의 CSV가 있으면 frame 단위로 비교한다.

### D1. 혁신 자기상관에서 예측한 NEES 팽창 (QA1)

- J4 Full의 s 혁신 ν_s와 range 혁신 ν_r 각각에 대해 시차 τ(frame, 이동거리 m)별 자기상관 ρ(τ)를 구한다.
- 상관만 있을 때의 분산 팽창 F = 1 + 2 Σ_{τ≥1} ρ(τ)를 상관이 0으로 떨어지는 곳까지 합한다.
- 예측 NEES ≈ F와 실측 heading NEES를 비교한다.

| 판정(사전 고정) | 해석 |
|---|---|
| 실측 NEES ≤ 2F | 상관 이중 계수로 설명 가능 |
| 실측 NEES > 5F | 평균 편향 등 다른 기전이 지배 |
| 사이 | 혼합 |

### D2. s 갱신 솎기 (QA1)

- J4 Full에서 s 갱신을 m개 packet마다 1회만 적용한다(m = 1, 2, 5, 10, 20, 50). range 갱신은 그대로, R은 바꾸지 않는다.
- m별 heading 포함률·NEES·RMSE를 낸다.
- 해석: 포함률이 상관길이 근처의 m에서 0.90 이상으로 회복되면 이중 계수가 주원인이다. m = 50에서도 0.80 미만이면 평균 편향이 주원인이다.

### D3. oracle 평균 제거 (QA1, 원인 분리 전용)

- e_MP를 이동거리 창 W(1, 2, 5, 10 m)로 이동평균한 성분 ē_W를 s 관측에서 뺀다. 참 pose의 LoS를 쓰므로 oracle이다.
- W별로 남는 heading 포함률·NEES를 낸다.
- 해석: 작은 W에서만 회복되면 단거리 성분, 큰 W에서도 회복되면 장거리 평균 성분이 주원인이다.
- 이 arm은 Goal 2 기법(평균 보정)의 상한 대조이며 Goal 1 모델이 아니다.

### D4. e_MP의 공간 구조 (QA2)

- 전 frame에서 e_MP = s_full,clean − s_LoS,clean을 계산한다(잡음 없음, 같은 첫 경로 tap 규칙).
- 출력:
  - 이동거리 variogram과 상관길이 ℓ_d(지수 적합)
  - 회전 구간의 yaw 변화 대비 상관
  - 창 평균 분산 비율 V_long = var(ē_5m) / var(e_MP)
  - heading 환산 바닥 σ_ψ,floor = √var(ē_5m) / median |∂s/∂ψ|
- R2_aA, R2_aB, R4_aB, R5_aB 각각 낸다(RF가 있는 case만).

### D5. range-only arm (QA3)

- 같은 4-state에서 range만 갱신하는 R4 arm을 추가한다.
- J4 − R4의 heading·XY RMSE 차이와 포함률 차이를 bias 수준별로 낸다.

### D6. 거리 의존 편파 분산 (QA4)

- J4에 MB_VAR의 분산 부분만 넣는다: R_s ← R_s + σ_b(ρ)². 원래 표(0.011/0.020/0.050/0.120/0.240 at ρ = 0/1.5/3/6/10 m)를 쓴다.
- μ_s(편파 평균 보정)와 range 평균 교체는 넣지 않는다.
- 원래 표는 BLOCK_C mount 0/B0에서 in-sample로 정한 값이다. 그래서 이 결과는 "in-sample 분산으로도 회복되는가"의 상한 진단이다.
- 출력은 D5와 같은 표다.

## 5. 해석 규칙 → G1-MODEL-003에 주는 영향 (사전 고정)

| 결과 | G1-MODEL-003 영향 |
|---|---|
| D1·D2가 이중 계수 지배 | 1차 arm 후보 = J-C(유색 잡음 상태) + J-CS(Schmidt site 기억) |
| D1·D2가 평균 편향 지배, D3 큰 W에서만 회복 | 장거리 평균 성분이 주원인이다. G1-MODEL-003 S2의 사전 무용성 검사를 필수 선행으로 둔다 |
| D6에서 포함률 ≥ 0.90 회복 | 거리 의존 분산 arm(J-V)이 1차 후보에 오른다 |
| D6에서도 < 0.80 | J-V는 대조군으로만 둔다 |
| D5에서 J4 − R4가 0을 포함 | 편파의 순수 기여가 BLOCK_C에서 확인되지 않음. G1-MODEL-003 정확도 판정에서 J − R4를 필수 항목으로 둔다 |
| D4의 σ_ψ,floor가 해당 bias 수준 DR RMSE보다 큼 | 그 bias 수준에서 Goal 1 정확도 우위가 구조적으로 어렵다. G1-MODEL-003 주장 범위를 그 위 수준으로 제한하는 근거 |

## 6. 출력

`research/G1_PACKET_EKF_20261114/DIAG_A/` 아래:

```text
code/          (복사 코드, CODE_SHA256.txt)
out/S0_REGRESSION.json
out/D1_AUTOCORR.json  …  out/D6_DISTVAR.json
out/checkpoint_rows.csv  (case, bias, sign, seed, arm, checkpoint, site, 오차·P·포함 여부)
REPORT_KO.md   (§5 표 채움, 첫 줄 DIAGNOSTIC_ONLY)
MANIFEST.json  (입력 SHA, 명령, seed, 시각, 패키지)
```

## 7. 실행 순서

S0 → D4(필터 없이 관측만) → D5 → D1 → D2 → D6 → D3.

## 8. 변경 기록

| 날짜 | 변경 | 작성 |
|---|---|---|
| 2026-11-14 | 초판. 추정기 불일치 확인 후 packet 단위 EKF 기준으로 기존 데이터 진단을 재정의. Fable 2026-11-14 답변의 C1–C3를 D1–D3로 반영 | Claude |
