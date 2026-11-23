# 대체 블록 적용 가능성 검증 (블록 v2 반영 전, DIAGNOSTIC_ONLY)

| 항목 | 내용 |
|---|---|
| 목적 | nadir 기준 heading 오염 제거(근·중거리)와 station 간 평균(원거리)으로 만든 대체 블록을 필터에 쓸 수 있는지, 블록 v2 계획에 반영하기 전에 확인 |
| 입력 | RT Corridor station sweep, 궤적 R2·R4·R5, dev seed 10–29, B0와 L2_GYRO_ARW |
| 결론 | **블록만으로는 쓸 수 없다**(N_I 0). **블록 + 근거리(ρ < 3 m) kriging 평균 보정**은 dev에서 S0-id 대비 비열등 규칙을 통과했다(N_I 16/16, XY 상한 1.08, heading 상한 1.06). 확정 seed 판정은 하지 않았다 |

## 1. 블록 BV

- station마다 기준 LoS 모델 대비 heading 오염 d와 편파비 손실 k를 구한다. 2ψ 위상과 진폭을 쓰며, nadir 기준으로 상수까지만 정해진다.
- 같은 앵커 쪽 station들의 d, k를 ρ Gaussian 커널(0.75 m)로 평균해 δ̄(ρ), κ̄(ρ)를 만든다. 원거리에서는 이 평균이 station 간 평균 역할을 한다.
- 블록: m = (1 − κ̄)·h_ref(x, y, ψ − δ̄)
- 분산: station 잔차로 a_m²σθ²(ρ) + σres²(ρ)를 적합한다(거리 bin 0–3, 3–6, 6–10 m).
- 평균 보정 μ_s는 없다.
- 코드: [code/bv_block.py](code/bv_block.py)

| arm | 내용 |
|---|---|
| BV | 기준 모델 FFD |
| BV_P1 | 기준 모델 FFD′(+5°). Stage 2 실패 조건 |
| BV0 | δ̄ = κ̄ = 0 (FFD 그대로, 평균 보정 없음). heading 제거 효과의 대조군 |
| BVK | BV + ρ < 3 m에서만 kriging 평균 보정(라벨 s_full − m, S0 근거리 초모수). 근거리 bin 분산은 LOSO 잔차로 다시 적합 |

## 2. 정적 (궤적 pose, RT 참값)

| 거리 | LoS | S0-id (kriging / POWER) | BV | 비고 |
|---|---|---|---|---|
| < 3 m RMS | 0.025 | **0.013** | 0.022 | 근거리는 S0-id kriging이 앞선다 |
| 3–6 m RMS / heading 등가 | 0.089 / +2.5° | 0.071 / +1.4° | **0.070 / +0.8°** | 2b_P1은 0.109 / +3.8° |
| ≥ 6 m RMS (packet pose) | 0.164 | 0.156 (POWER) | **0.152** | BV + POWER는 0.151 |

BV_P1의 값은 BV와 소수점 넷째 자리까지 같다. nadir 기준이라 전역 기준 모델 오차가 상쇄된다. → [BV_STATIC_ROUTE.csv](BV_STATIC_ROUTE.csv), [BV_FAR_POWER.csv](BV_FAR_POWER.csv)

## 3. 필터 (dev seed 10–29, S0-id 대비)

| 조건 | arm | N_I (S0-id 16) | 거울해 | XY 비율 중앙값 / 상한 | heading 비율 중앙값 / 상한 | heading 편향 |
|---|---|---|---|---|---|---|
| B0 | BV | 0 | 3 | 1.70 / 1.82 | 1.33 / 1.57 | +0.73° |
| B0 | BV_P1 | 0 | 3 | 1.70 / 1.82 | 1.33 / 1.57 | +0.73° |
| B0 | BV0 | 1 | 5 | 1.69 / 1.82 | 1.46 / 1.61 | +0.80° |
| B0 | **BVK** | **16** | 0 | **1.06 / 1.08** | **1.01 / 1.06** | +0.23° |
| L2 | BV / BV0 | 0 / 1 | 3 / 6 | 1.66 / 1.63 (중앙값) | 1.33 / 1.44 (중앙값) | — |
| L2 | **BVK** | **16** | 0 | **1.05 / 1.08** | **1.01 / 1.05** | +0.24° |

궤적별 20 seed 합산 RMSE (B0, XY cm / heading °):

| arm | R2 | R4 | R5 |
|---|---|---|---|
| S0-id | 9.80 / 1.61 | 6.68 / 1.05 | 7.43 / 1.30 |
| BV | 17.31 / 2.33 | 8.95 / 1.20 | 11.47 / 1.57 |
| BVK | 10.22 / 1.57 | 6.75 / 1.08 | 8.21 / 1.33 |

→ [BV_JUDGE.csv](BV_JUDGE.csv), [BVK_JUDGE.csv](BVK_JUDGE.csv), [BV_PERSEED.csv](BV_PERSEED.csv), [BVK_PERSEED.csv](BVK_PERSEED.csv)

## 4. 해석

- **heading 제거 자체는 효과가 있다.** BV는 BV0보다 heading이 낫다(1.46 → 1.33, R4 1.39° → 1.20°). 그러나 손실의 대부분은 평균 보정이 없어서 생긴다.
- **필요한 평균 보정은 근거리뿐이다.** 근거리 오차는 공간 상관이 길다(이웃 열 상관 0.49, y 0.7–0.8, 궤적 위에서 0.5까지 떨어지는 거리 0.28–0.48 m). 그래서 station 사이에서도 재현되고, kriging(ℓx 1.0 m)이 이를 가져간다. 중·원거리는 상관이 짧다(0.08–0.2 m). 블록과 분산만으로 충분하다. 상관 길이 대 station 간격 기준과 맞는다.
- **기준 모델 오차에 견고하다.** 전역 오차(+5°)는 nadir 기준 블록에서 상쇄된다. BVK의 라벨도 s_full − m이므로 같은 이유로 상쇄된다. 위치에 따라 변하는 기준 모델 오차는 상쇄되지 않는다(nadir 확인의 P4: 중거리 +2.25°).
- **남은 비용.** R5(원거리 비중이 큼) XY가 7.4 → 8.2 cm로 늘었다. S0-id 원거리 POWER가 런타임 채널 특징으로 얻는 몫이다.

## 5. 남은 일

- 확정 seed(새로 생성할 70–89) 판정
- 위치에 따라 변하는 기준 모델 오차 시험
- station heading 영점 오차 시험
- 블록 v2 계획 개정

## 6. 함께 올린 사전 확인

| 파일 | 내용 |
|---|---|
| [NADIR_REF_CHECK.csv](NADIR_REF_CHECK.csv) | nadir 기준 heading·편파비 추정. code/nadir_ref_check.py |
| code/heading_split_check.py | 매끄러운 몫 / 흩어짐 분리와 2차 모멘트 |
| code/corr_length_check.py | station 격자 상관 |
| [ROUTE_CORR_CHECK.csv](ROUTE_CORR_CHECK.csv) | 궤적 위 자기상관과 필터 핵 비교. code/route_corr_check.py |
| [STATION_CHI_L.csv](STATION_CHI_L.csv), [STATION_CHI_L_SUMMARY.csv](STATION_CHI_L_SUMMARY.csv) | station별 편파각 χ·편파비 L (Full, LoS), nadir 대비 LoS 변화. code/station_chi_check.py |
| [LOSFREE_CHI_INTERP.csv](LOSFREE_CHI_INTERP.csv), [LOSFREE_CHI_INTERP_SUMMARY.csv](LOSFREE_CHI_INTERP_SUMMARY.csv) | LoS 없이 근거리·원거리 평균 기준으로 중거리 χ 보간 (1차·2차). code/losfree_chi_interp.py |
| [CORR_LENGTH_CHECK.txt](CORR_LENGTH_CHECK.txt) | station 격자 x·y·ψ 상관과 궤적 packet 간격 (corr_length_check.py 출력) |
| [HEADING_SPLIT_CHECK.txt](HEADING_SPLIT_CHECK.txt) | heading 매끄러운 몫·흩어짐 분리와 2차 모멘트 (heading_split_check.py 출력) |
| [groups_bv_bvk.tar.gz](groups_bv_bvk.tar.gz) | seed별 GROUP.json |
