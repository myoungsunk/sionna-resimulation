# Office 적용 — station sweep 블록 SWB-O (RT, DIAGNOSTIC_ONLY, dev seed 10–29)

| 항목 | 내용 |
|---|---|
| 질문 | Corridor에서 확인한 sweep 블록 방식이 Office에서도 FFD를 대체할 만한가. 보유한 RT Office 자료로 확인 |
| 입력 | Office station sweep(35곳 중 LoS 25곳, 36 yaw, 간격 약 1.5 m, 앵커 (5, 2.2)). LoS 궤적 O01·O02·O03L(사용자 결정 2026-11-18). B0와 L2_GYRO_ARW |
| 비교 | H2(기준), F2T1V(기존 Office 최선: FFD + Office sweep kriging + V 표). 거리 보정은 F2T1V와 SWB-O 모두 Office sweep T1(`office/o3_build.py`) |
| 결론 | **중심 성능은 SWB-O가 F2T1V보다 좋다.** XY 9.2 대 15.8 cm, heading 1.37 대 2.54°, NEES 5.7 대 12.9, gross 0 대 1. 특히 기존 방법이 모두 실패하던 O02가 크게 좋아진다(XY 11.7 대 22.0 cm, heading 편향 −0.23 대 −2.39°). **그러나 N_I는 세 arm 모두 0이다.** O01의 위치 coverage(XY95)가 공통으로 미달하기 때문이다. O01에서는 SWB-O가 F2T1V보다 약간 나쁘다 |

## 1. 블록 SWB-O

Office는 Corridor 같은 열·줄 격자가 아니다. 앵커 행(y = 0.75 m)은 x 간격 1.5 m, 나머지 4개 열(x = 0.5, 3.3, 6.55, 9.5)은 y 간격 1.5 m다. 그래서 Corridor SWB의 거리별 처리(원거리 열 평균, 중거리 같은 줄 χ 보간)를 쓰지 않고 가장 단순한 형태로 만들었다.

- station별 36 yaw 곡선의 ψ 조화 19개 전체를 쓴다.
- (x, y)에서 Delaunay 선형 보간을 하고, 볼록 껍질 밖은 가장 가까운 station 값을 쓴다.
- ψ는 해석적으로, ∂/∂x와 ∂/∂y는 중앙차분(1 mm)으로 계산한다.
- 분산 표는 station 하나를 빼고 다시 만든 보간의 잔차로 c₁a² + c₀를 적합했다. 간격이 3 m로 벌어지므로 보수적이다(잔차 RMS 0.09–0.10). → [TABLE_SWBO.json](TABLE_SWBO.json)
- 평균 보정은 없고, FFD도 쓰지 않는다.
- → [code/office_swb.py](code/office_swb.py)

## 2. 정적 (LoS 궤적 pose, RT 참값)

| 거리 | 보간 한계 (LoS 곡선 블록 대 LoS) | SWB-O | FFD만 | FFD + Office kriging |
|---|---|---|---|---|
| < 3 m | 0.0159 | 0.0185 | 0.0125 | 0.0127 |
| 3–6 m | 0.0095 | **0.0205** | 0.0606 | 0.0219 |
| ≥ 6 m | 0.0054 | **0.0237** | 0.1317 (heading 등가 +7.6°) | 0.0254 |

- **근거리:** 1.5 m 간격으로는 앵커 근처에서 빠르게 변하는 LoS를 보간하지 못한다. 보간 한계 0.016이 FFD 잔차보다 크다.
- **중·원거리:** SWB-O가 FFD + kriging과 같거나 낫다.
- → [OFFICE_STATIC.csv](OFFICE_STATIC.csv), [code/office_static.py](code/office_static.py)

## 3. 필터

| 조건 | arm | N_I | gross | XY (cm) | heading (°) | Pose95 | Heading95 | NEES | 비율 대 F2T1V: XY 중앙값 / 상한 | heading 중앙값 / 상한 |
|---|---|---|---|---|---|---|---|---|---|---|
| B0 | H2 | 0 | 20 | 45.4 | 5.33 | 0.36 | 0.52 | 63.3 | — | — |
| B0 | F2T1V | 0 | 1 | 15.8 | 2.54 | 0.65 | 0.84 | 12.9 | — | — |
| B0 | **SWB-O** | 0 | **0** | **9.2** | **1.37** | **0.73** | **0.96** | **5.7** | 0.80 / 1.12 | **0.58 / 0.68** |
| L2 | F2T1V | 0 | 1 | 15.7 | 2.53 | 0.67 | 0.85 | 12.1 | — | — |
| L2 | **SWB-O** | 0 | **0** | **9.2** | **1.37** | **0.75** | **0.97** | **5.5** | 0.79 / 1.10 | **0.59 / 0.69** |

궤적별 (B0, seed 평균, XY cm / heading ° / 궤적 integrity 통과 seed 수 / heading 편향):

| arm | O01 | O02 | O03L |
|---|---|---|---|
| F2T1V | 4.64 / 0.93 / 1 / −0.36° | 21.96 / 3.53 / 0 / −2.39° | 9.55 / 1.88 / 15 / −0.75° |
| SWB-O | 5.93 / 1.22 / 0 / −0.34° | **11.69 / 1.29 / 5 / −0.23°** | **7.63 / 1.58 / 16 / −0.67°** |

O01의 integrity 실패는 두 arm 모두 XY95와 그 하한(위치 coverage)에서 나온다. O01 Pose95는 F2T1V 0.80, SWB-O 0.78이고, XY95는 0.74, 0.74다. 편파 블록 고유의 문제라기보다 이 궤적의 위치 공분산 문제다. → [OFFICE_JUDGE.csv](OFFICE_JUDGE.csv), [OFFICE_PERSEED.csv](OFFICE_PERSEED.csv)

## 4. 해석과 한계

- **O02에서 개선이 크다.** O02는 기존 Office 전이에서 oracle μ_s로도 실패했던 궤적이다. SWB-O는 heading 편향을 −2.4°에서 −0.2°로 줄인다. FFD 기반 방법이 이 궤적에서 가진 계통 편향을, 측정 곡선을 직접 쓰는 블록은 갖지 않는다는 뜻이다. 그 편향의 원인(FFD 모델과 Office RT의 차이, 또는 kriging의 한계)은 분리하지 않았다.
- **궤적이 station 줄 위를 지난다.** O01은 y = 0.75 m 행(station S01–S07), O02는 x = 3.3 m 열(S15–S21)을 따라간다. 그래서 이 Office 결과는 station 줄 위의 궤적에 유리한 조건이다. 줄에서 벗어난 임의 궤적은 근거리 보간 한계(0.016)를 고려하면 더 나쁠 수 있다. 시험하지 않았다.
- **근거리 station 밀도가 부족하다.** 근거리에서는 FFD가 더 정확하다. Office에서 sweep 블록을 쓰려면 앵커 주변 station을 더 촘촘하게 두거나, 근거리만 FFD(또는 nadir 기준 상대 모델)와 섞는 방식이 필요하다.
- **N_I 0은 판정 미달이다.** 세 arm 모두 O01 위치 coverage 때문에 seed 단위 integrity를 통과하지 못한다. Office에서 Goal 1 판정을 하려면 O01 위치 공분산(거리 채널)을 먼저 봐야 한다.
- **범위.** RT Office, LoS 구간만, dev seed, 이번 대화에서 정한 블록 형태다. station heading 영점 오차는 넣지 않았다(Corridor 시험에서 1°에도 크게 민감했다).

## 5. Corridor에서 학습한 SWB를 Office에 그대로 쓰는 경우

저장된 블록(SWB-O, SWB-C, SWB-C0의 계수·분산 표·거리 보정·구성)은 [blocks/](blocks/README_KO.md)에 있다.

**대응 방법.** Office pose를 앵커 기준 수평거리 ρ와 앵커 좌우로 Corridor 복도축 위의 점(x = 10 ± ρ, y = 0)에 대응시켰다. 두 공간의 앵커와 태그 높이가 같아 앙각이 같다. ψ는 그대로 쓰고, Jacobian은 연쇄법칙으로 구한다. 분산 표는 Corridor 완전 열 제외 표를 쓴다.
- **SWB-C:** 거리 보정은 Office sweep T1
- **SWB-C0:** 거리 보정도 Corridor sweep T0
- Corridor sweep에는 복도축 방위(β ≈ 0°, 180°) 자료만 있어, Office의 방위 의존은 무시된다
- → [code/corr2office.py](code/corr2office.py), [code/run_c2o.py](code/run_c2o.py)

**정적 (LoS 궤적 pose, s_full 잔차 RMS / heading 등가)**

| 거리 | FFD만 | SWB-O (Office sweep) | SWB-C (Corridor sweep) |
|---|---|---|---|
| < 3 m | 0.0125 / −0.04° | 0.0185 / +0.36° | 0.1347 / +2.34° |
| 3–6 m | 0.0606 / +1.22° | 0.0205 / +0.06° | 0.1201 / −1.75° |
| ≥ 6 m | 0.1317 / +7.60° | 0.0237 / −0.26° | 0.4632 / +24.3° |

방위별 SWB-C 잔차는 복도축과 같은 방위(±30°)에서 0.093, 수직 방위(30–150°)에서 0.389(heading 등가 +21°), 반대 축(150–210°)에서 0.109다 → [C2O_STATIC.csv](C2O_STATIC.csv)

**필터 (dev seed 10–29, B0)**

| arm | N_I | gross | XY (cm) | heading (°) | Pose95 | NEES | O01 / O02 / O03L XY (cm) |
|---|---|---|---|---|---|---|---|
| H2 | 0 | 20 | 45.4 | 5.33 | 0.36 | 63.3 | 7.4 / 71.8 / 12.5 |
| F2T1V | 0 | 1 | 15.8 | 2.54 | 0.65 | 12.9 | 4.6 / 22.0 / 9.6 |
| SWB-O | 0 | 0 | 9.2 | 1.37 | 0.73 | 5.7 | 5.9 / 11.7 / 7.6 |
| SWB-C | 0 | 13 | 52.4 | 5.65 | 0.40 | 68.7 | 9.1 / 82.1 / 13.8 |
| SWB-C0 | 0 | 25 | 80.4 | 8.83 | 0.39 | 121.7 | 11.4 / 127.6 / 18.3 |

L2도 같은 양상이다(SWB-C 50.4 cm, SWB-C0 74.8 cm) → [C2O_JUDGE.csv](C2O_JUDGE.csv), [C2O_PERSEED.csv](C2O_PERSEED.csv)

**해석.** Corridor에서 학습한 SWB는 Office로 옮겨가지 않는다. 보정 없는 H2(45.4 cm)보다도 나쁘다.
- **β 의존이 빠졌다.** Corridor sweep은 앵커 주위 방위가 복도축뿐이다. Office 궤적은 모든 방위를 지나고, LoS 편파각 자체가 방위에 따라 크게 달라진다. Stage 0에서 β 의존이 크다고 확인한 것과 같다.
- **블록에 그 공간의 다중경로가 들어 있다.** 복도축 방위(±30°)에서도 잔차가 0.09로 Office sweep 블록(0.02)보다 훨씬 크다. Corridor의 천장·벽 반사가 블록 안에 들어 있기 때문이다.
- **결론.** sweep 블록은 공간마다 그 공간의 sweep으로 다시 만들어야 한다. Corridor에서 만든 블록을 다른 공간의 사전값으로 쓰는 것은 근거가 없다.
