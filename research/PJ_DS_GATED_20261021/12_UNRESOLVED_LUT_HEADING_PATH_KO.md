# unresolved 다중경로와 Δs, LoS 모델 Δs-LUT 비교, range 보정의 heading 악화 경로 (2026-10-21)

실행: [run 39582073787](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39582073787) (패킷 CIR·LUT·경로 분해), [run 39586037715](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39586037715) (gate on/off·반사실). 로컬 분석 `hpath_analyze.py`, `hpath_strata2.py`.
QA: 분해 closure 1.2e-13. LoS 모델(SourceFFD) s 프로파일 대 측정 LoS: s(fp) 차 중앙값 1.9e-7, Δs₊₁ 차 2.7e-8, fp 100% 일치. 이전 run과 heading RMSE 1.7e-13 이내 일치.

## 1. unresolved 다중경로에서 Δs (9,519 패킷, Full)
다중경로 전용 CIR = Full − LoS (복소, 두 포트). MLR = fp에서 다중경로/LoS 전력비.

| 계층 | 패킷 비율 | e_s² 비율 | e_s RMS | Δs→e_s R² (원 Δs) | R² (Δs − LUT) | 큰 편향 중 평탄 비율 |
|--|--|--|--|--|--|--|
| A 깨끗함 (fp 그대로, MLR<−15 dB) | 44.8% | 2.5% | 0.040 | −1.03 | −0.65 | 4% |
| B 겹침, fp 그대로 | 17.4% | 13.0% | 0.147 | 0.375 | 0.489 | 9% |
| C fp ±1 tap | 32.7% | 32.7% | 0.170 | 0.428 | 0.464 | 14% |
| D fp 2–3 tap | 4.1% | 34.5% | 0.496 | 0.632 | 0.694 | 6% |
| E fp ≥4 tap (분리된 펄스로 이동) | 1.1% | 17.3% | 0.677 | −0.600 | −0.404 | 5% |
R²: route 제외 선형(Δs 8개 offset), 계층 안에서 평가. 평탄: LUT 차감 후 |Δs| (+1,+2,+4) 모두 <0.05. 큰 편향 = |e_s| 상위 20%.

- 편파 편향의 80%(B+C+D)가 펄스 안 겹침(fp 이동 0–3 tap)에서 생기고, 여기서 Δs가 편향을 설명한다(R² 0.38–0.69).
- 분리된 펄스로 fp가 넘어간 경우(E, 1.1% 패킷, 17% 편향)는 선형 Δs로 설명되지 않는다.
- B 안에서 다중경로 peak 지연별 R²(LUT 차감): ≤1 tap 0.49, 2 tap 0.53, 3 tap 0.54, 4–8 tap 0.40, >8 tap 0.33.
- LUT 차감 후에도 Δs가 평탄한 큰 편향은 큰 편향 패킷의 10%, 전체 e_s²의 3.8%.
- 사례 ② R4 A M0 #737 정정: fp에서 다중경로가 LoS보다 2.9 dB 낮을 뿐인 강한 겹침이고, 다중경로 peak는 +17 tap, 창 내 가중 평균 +5.7 tap. 단일 "동일 지연 경로"가 아니라 여러 경로의 겹침. 원 Δs는 +0.005/+0.010/−0.002 (+1/+2/+4)로 평탄하지만, LoS 프로파일 자체가 −0.032/−0.059/−0.109로 기울어 있어 LUT 차감 후 +0.036/+0.069/+0.107. 편향 −0.83에 비해 신호는 작다.

## 2. 예측 heading 기반 Δs-LUT 대 측정
LUT = LoS 모델로 계산한 상태 x에서의 s(fp+o) 프로파일. 1차 예측 상태 x̂⁻는 BASE 필터 prior(t≥30, 6,201 패킷/bias).

| 항목 | 값 |
|--|--|
| ∂s(fp)/∂ψ 중앙값 | 0.0128 /deg |
| ∂Δs₊₁/∂ψ, ∂Δs₊₂/∂ψ, ∂Δs₊₄/∂ψ | 0.00056, 0.0010, 0.0018 /deg (s 대비 4.4%, 8.1%, 14.7%) |
| LoS 자체 |Δs₊₁| 중앙값 / Full |Δs₊₁| | 0.007 / 0.019 |
| LUT(x̂⁻) − LUT(GT) |Δs₊₁| 중앙값 | 0.001 |
| e_s 설명 R²: 원 Δs → 측정 − LUT(x̂⁻) | 0.342 → 0.411 (B0, L2 동일) |
| corr(측정 − LUT(x̂⁻), prior heading 오차) | 0.045 |
| s 수준 innovation 분산 중 heading 오차 부분 / 다중경로 부분 | 4.7% / 101% |

- Δs-LUT는 heading에 거의 둔감하다. 예측 heading 오차(중앙값 0.74°)가 LUT를 바꾸는 양(0.0004)은 다중경로 Δs(0.019)보다 훨씬 작다. 그래서 측정 − LUT(x̂⁻)는 heading과 무관한(순환 없는) 다중경로 지표이고, 원 Δs보다 편향을 더 설명한다(R² +0.07).
- 같은 이유로 Δs 비교로는 heading을 직접 구별할 수 없다. heading 정보는 s 수준에만 있고, 그 innovation의 95%가 다중경로다.

## 3. range 평균 보정의 재귀 heading 악화 경로
heading MSE 분해 (BASE MSE 대비, 14 case-bias 중앙값):

| 항 | BASE | MU_R_EX | MU_R_EXDS | MU_R_ORACLE (μ_r = 참 e_r) |
|--|--|--|--|--|
| U_S·U_S (편파 오차 경로) | 0.863 | 0.990 | 1.029 | 1.051 |
| U_R·U_R | 0.137 | 0.068 | 0.070 | 0 |
| 2·U_R·U_S 교차 (표는 단방향 값) | −0.098 (8/14 음) | +0.065 | +0.072 | 0 |
| LIN·LIN | 0.018 | 0.032 | 0.052 | 0.006 |
| heading비 | 1 | 1.143 | 1.155 | 1.084 (5 개선/7 >10% 악화) |

gate on/off와 반사실(U_S 경로만, BASE MSE 대비 U_S MS 비):

| 조건 | 값 |
|--|--|
| BASE가 기각한 패킷(t≥30, 중앙값 24개) 평균 |e_s| / 전체 | 0.531 / 0.088 |
| range 보정으로 새로 받아들인 패킷 수, 평균 |e_s| | EXDS 7개 0.294, ORACLE 10개 0.420 |
| BASE 행렬 + 보정 arm의 accept mask | 1.179 (EXDS), 1.150 (ORACLE) |
| 보정 arm 행렬 + BASE mask | 0.965 (EXDS), 0.991 (ORACLE) |
| gate 끔: BASE 대비 heading | BASE_NOGATE 1.225 |
| gate 끔: BASE_NOGATE 대비 range 보정 | EXDS 1.044 (6 개선/4 악화), ORACLE 0.880 (8 개선/2 악화) |

- heading 악화의 주경로는 range 오차가 아니라 편파 오차 경로(U_S)의 증가(+17–19%)다.
- 그 증가는 이득(K, H) 변화가 아니라 χ²₂ gate의 accept 변화에서 온다: mask만 바꾸면 +15–18%, 행렬만 바꾸면 −1~−4%.
- 원리: 같은 다중경로가 range와 편파를 함께 오염시키므로, BASE에서는 큰 range innovation이 결합 NIS를 키워 편파 편향이 큰 패킷을 함께 기각했다(기각 패킷 |e_s| 0.53 = 평균의 6배). range를 보정하면 이 "다중경로 경보"가 꺼져 편파 오염 패킷이 들어온다.
- 부가 경로: BASE에서 range 오차의 heading 기여가 편파 기여를 일부 상쇄했다(교차 −0.098). 보정 후 남은 range 잔차는 편파와 같은 부호로 정렬(+0.072).
- gate가 없으면 완전한 range 보정은 heading을 12% 개선한다. HGB 보정은 +4%(중립).
