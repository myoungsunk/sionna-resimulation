# 논의 요청: FG-V1 시간 상관 적용 방식과 검증 arm

## 0. 요청

single-anchor 편파 heading 시스템을 EKF에서 factor graph(FG)로 옮기는 1차 테스트를 마쳤고, R5 초반 이탈이 s 관측 오차의 시간 상관 때문이라는 진단을 얻었다. 다음 단계로 시간 상관을 어떤 방식으로 넣고 어떤 arm으로 검증할지 정하려 한다. 아래 자료와 링크를 검토하고 다음 네 가지를 제시해 달라.

1. 우리 조건에 가장 적절한 시간 상관 적용 방식과 근거 (6절 후보 A–E 중, 또는 조합)
2. 검증 arm 확정안: 유효/보류/기각과 이유, 비교 질문, 통제 변수 (8절 초안 기준)
3. 실행 전에 사전 고정해야 할 항목과 제안값 (9절)
4. 이 계획이 틀릴 수 있는 지점과 그것을 먼저 확인할 진단

데이터로 확인된 사실과 가설을 구분해 달라. 아래 수치는 모두 저장소 결과 파일에 있다.

자료: https://github.com/myoungsunk/sionna-resimulation/tree/research/fg-v1-test-20261128/research/FG_V1_20261128
(README.md, results/*.json, results/MANIFEST.json, code/)

## 1. 연구 맥락

- 천장 anchor 1개 (10.0, 0.0, 2.65 m), 로봇(TurtleBot3) tag에 dual-LP ±45° 안테나. 관측은 UWB range r과 편파 지표 s(절대 heading 정보). DR은 wheel 거리 + gyro yaw.
- 데이터는 Sionna RT corridor(R2/R4/R5 평가 궤적, N1–N6 학습 궤적, station sweep 200 station × 36 yaw).
- 기존 추정기는 packet 단위 EKF (M7 H2). FG-V1은 같은 모델로 FG를 만들어 estimator 효과와 모델 효과를 분리하는 것이 목적이다.
- 판정은 integrity(NEES, 95% 포함률)를 정확도보다 먼저 본다. 확인 case를 묶은 pooled 판정 + case별 심각한 실패 규칙.
- Goal 1 경계 (이번 논의 범위):
  - 허용: range 평균 보정, 편파 bias(평균) 보정, 불확도 표현(상관 상태, Schmidt/consider, 분산, 꼬리), ranging 자체의 다중경로 완화, 온라인으로 얻는 CIR·기하 특징
  - 제외(Goal 2): 오염 감지 기반 s 가중·기각, 반사 경로 명시 편파 모델
- EKF 쪽에서는 시간 상관을 R_ss inflation 계열(C1 누적항 → C2 앵커 기하 kernel → C3 split CI)로 진행하는 계획이 있었고, kernel 길이는 N1–N6으로 학습하고 R2/R4/R5로 판정하는 안(K-b)을 채택했었다. FG 쪽 방식은 이번에 정한다.

## 2. 현재 FG 기본 구조 (v1a, e_s 없음)

- 변수: X_k = (x, y, ψ), world-frame, packet마다 1개. gyro bias 상태 없음.
  - 이유: 평가 조건 N0/N2(L0)는 실제 bias 0이고 heading 오차의 주원인은 gyro ARW다. M7의 b_g prior(σ 0.1°/s)는 R2 길이(196 s)에서 heading 1σ ≈ 19.6°에 해당해 ARW(0.21°, 0.84°)보다 불확도를 지배하고, e_s를 흡수하는 통로가 된다. 비교 기준 EKF도 3-state로 맞췄다.
- factor: prior(X_0), odom(X_k−1, X_k; M7 transition, Q = GQGᵀ + 1e-10·I), 관측 [r, s] 2D 하나(X_k).
  - R = EKF Reff (packet R + diag(0, σ_b²)), EKF의 2D NIS gate mask를 그대로 사용.
  - R의 비대각 항은 125,440 packet 전부 0이라 [r, s]를 1D 두 개로 나눠도 결과가 같다(확인됨). 분리하면 gate 규칙은 따로 정해야 한다.
- h: FFD 원본, 또는 surrogate(x 0.025 m × y 0.05 m × ψ 4° trilinear, s 오차 p95 ≤ 0.08σ_s, 최대 0.55σ 고립점, 호출 18배 빠름).
- solver: iSAM2(QR, relinearizeThreshold 1e-3, skip 1). causal 출력 = 매 step 최신 node의 추정값과 marginal.
- 조건: B0(gyro ARW 0.015°/√s), L2_GYRO_ARW(0.060°/√s), seed 10, R2/R4/R5.

## 3. 확인된 결과

- EKF 재구현이 저장소 M7 H2와 1e-14로 일치. 3-state EKF를 surrogate로 돌려도 FFD 대비 1.8 cm, 0.21° 이내.
- G0 등가성 gate(FG lag=1, GN 1회 vs EKF3): 위치 4.4e-5 m, yaw 1.1e-5 rad 이내.
- lag=∞ causal FG vs EKF3 (surrogate, seed 10):

| cell | 위치 RMSE EKF / FG (m) | yaw RMSE EKF / FG (°) | ANEES(3-dof) EKF / FG |
|---|---|---|---|
| B0 R2 | 0.082 / 0.084 | 0.69 / 0.71 | 4.44 / 4.36 |
| B0 R4 | 0.032 / 0.032 | 0.75 / 0.76 | 7.91 / 8.14 |
| B0 R5 | 0.039 / 0.112 | 0.62 / 1.08 | 3.57 / 4.49 |
| L2 R2 | 0.091 / 0.093 | 1.09 / 1.10 | 6.76 / 6.81 |
| L2 R4 | 0.049 / 0.047 | 0.92 / 0.92 | 10.11 / 10.23 |
| L2 R5 | 0.065 / 0.129 | 0.88 / 1.28 | 5.14 / 6.12 |

- 실행 시간: cell당 24–96 s. 이전 b_g 포함 4-state + FFD 구성에서는 R2 1회 약 13분.
- 두 추정기 모두 R4에서 ANEES 8–10으로 과신한다(seed 하나라 판정 불가).

## 4. R5 초반 이탈 진단 (B0/seed10/R5, k = 0–156까지의 graph)

FG 오차 증가는 k ≈ 120–200(x ≈ 5–7 m, anchor로 접근하는 초반)에만 있고, 최대 0.78 m이다. k > 200에서는 EKF와 같다.

| 진단 | k=156 위치 오차 |
|---|---|
| batch LM을 참값 / EKF / iSAM2 해에서 시작 | 모두 0.78 m, cost 26.78 → solver 문제 아님 |
| odom 잡음을 참값 잔차 수준으로 | 0.78 m → odom 아님 (참값 odom 잔차 / 모델 σ = 1.01, 0.98) |
| s만 white synthetic | 0.013 m |
| range만 white synthetic | 0.379 m |
| range·s 모두 white synthetic | 0.081 m |
| R_ss ×5 / ×20 | 0.080 / 0.026 m |
| FFD 원본 (surrogate 대신) | 0.248 m |

- 참값 위치에서 계산한 s 잔차의 lag-1 자기상관은 0.68 / 0.90 / 0.96 / 0.74 (k 0–100 / 100–160 / 160–260 / 260–500)이고, 구간 whitened 평균은 +0.20 / −0.26 / −0.07 / +0.16이다.
- 이탈 형태는 구간 전체의 거의 일정한 heading offset(surrogate −6.9°, FFD −1.6°)이다. anchor 축 rigid 회전으로 설명되는 몫은 일부(위치 RMSE 0.46 → 0.33 m)뿐이다.
- range와 odom은 anchor 축 rigid 회전에 불변(range 민감도 1.8e-11)이라 이 방향은 s만 결정한다. white 가정의 정보량은 rigid 회전 σ 1.6°, heading σ 1.3°에 해당한다.
- MAP가 h의 작은 계통 차이에 민감하다. 참값 궤적에서 surrogate와 FFD의 s 차이는 whitened 평균 0.008–0.024인데, MAP는 0.25 m에서 0.78 m로 이동한다. FFD 원본으로 lag=∞를 돌려도 k=161에서 0.241 m (EKF 0.117 m).
- 해석: s의 시간 상관 오차를 white로 가정한 모델 mismatch를 FG가 과거 전체를 다시 풀며 키운다. "smoothing은 상관 mismatch를 증폭한다"는 예측과 일치한다.
- 미해결: 같은 white 가정의 EKF가 이 구간에서 덜 벗어나는 이유.

## 5. 활용 가능한 데이터

- station sweep: 7,200행, s·range·CIR 특징·RT 라벨 e_s, e_r. CIR 특징 학습(GBM, station 묶음 5-fold)으로 |e_s|를 예측하면 Spearman 0.76(같은 거리 bin 안에서는 0.60), 5분위 평균은 0.010 → 0.187로 단조 증가한다. 2배 이상 차이 나는 쌍의 순서 정확도는 85%. 다만 s 가중에 쓰면 Goal 2다.
- N1–N6: 6,389 pose의 truth와 관측(s_fp, range, CIR 특징). 학습용.
- R2/R4/R5 입력: B0와 L2_GYRO_ARW, seed 10–29 (120 cell). N2-L2(고정 bias) 입력은 아직 없다.
- 실측 RF 데이터는 아직 없다. σ_v(white 성분)는 RT에서는 주입 설정값이다.

## 6. 시간 상관 적용 후보 (FG 기준)

| 방식 | 구조 | 우리 조건에서의 장점 | 우리 조건에서의 약점 |
|---|---|---|---|
| A. GM 상태 augment | packet마다 e_s node, e_k+1 = φe_k + w, f_s가 X_k와 e_k에 연결 | AR(1) 정확. φ = exp(−Δ)에 기하 index(Δs, Δψ) 적용 가능, 재방문 kernel 연결 가능 | node 2배. R5의 일정 heading offset은 e_s 평균과 ψ가 구분되지 않는 방향이라 σ_es, φ 설정에 민감 |
| B. 구간 bias node | 이동 거리 구간마다 b 하나를 공유, 구간 간 RW | node 적음. 구간 평균이 치우친 R5형 오차를 직접 흡수 | 구간 내 상수 근사, 경계 의존 |
| C. 관측 차분 | s_k − φs_k−1 factor가 X_k−1, X_k에 연결 | 변수 추가 없음 | white 성분 σ_v가 있으면 MA(1) 근사. gate 결손에서 사슬이 끊김. 가변 φ와 맞추기 번거로움 |
| D. 블록 factor | M개 packet의 s를 하나로, Σ_ij = σ_es²ρ(Δ_ij) + σ_v²δ_ij | 임의 kernel, 블록 안 정확 | M개 pose를 묶는 조밀한 factor. φ ≈ 0.9이면 M이 커야 함 |
| E. 분산 inflation | 구조 그대로, R_ss × κ, κ ≈ (1+φ)/(1−φ) | 가장 단순, EKF(C1)와 같은 계열. φ=0.9 → κ≈19이고 R5에서 ×20이 0.026 m로 효과 확인 | s의 실제 정보까지 버림 → heading 정확도 손실 가능. 상수 κ는 상관 약한 구간에서 과보수 |

현재 제안: E를 기준선, A를 본 방법, B를 A의 저비용 대안, C·D는 후순위.

## 7. 논의 주제

1. **방식 선택:** 우리 조건(white 성분 존재, gate 결손, 기하 index 필요, heading offset 모드)에서 A, B, E 중 무엇을 주 방법으로 할지. A와 E의 조합(예: A + 잔여 inflation)이 필요한지.
2. **index:** 시간 vs 기하(Δs, Δψ). L_ψ는 station yaw sweep, L_s는 N1–N6 직선 구간으로 추정하는 안. 정지 구간 φ_max. 거리에 따라 상관 길이가 달라질 가능성.
3. **파라미터 식별:** α = σ_v²/R_ss, σ_es, L_s, L_ψ를 RT 라벨 없이(측정 − 기준 모델 잔차, GT pose 필요) 얻는 절차. station sweep은 leave-one-station-out. 희석 보정 1/(1−α)의 상한.
4. **e_s–ψ 분리:** A에서 e_s가 heading offset을 흡수하거나 반대로 heading이 e_s를 흡수하는 위험. z posterior/prior 비율로 진단하는 것이 충분한지. consider(Schmidt)형으로 e_s를 추정하지 않고 공분산만 반영하는 대안이 FG에서 의미가 있는지.
5. **EKF와 FG의 비대칭:** 같은 white 모델에서 EKF가 R5 구간에서 덜 벗어나는 이유에 대한 가설과 확인 진단.
6. **surrogate 기준:** MAP가 작은 h 차이에 민감하므로 h 오차 p95가 아닌 "FFD FG 대비 MAP 이동"을 기준으로 할지, 실데이터 arm은 FFD 원본으로 돌릴지 (FFD 3-state lag=∞는 260 step에 54 s).
7. **판정 통계와 규모:** seed 10–29 × 2 조건 × 3 경로(120 cell), paired, log ANEES, block bootstrap, 등가 margin. arm당 2코어로 약 1.5시간.
8. **R5형 구간 평가:** 특정 구간 지표를 쓸지, 쓴다면 cherry-pick이 되지 않도록 어떻게 사전 정의할지.

## 8. 검증 arm 초안 (검토 대상)

| arm | 추정기 | s 오차 모델 | 질문 |
|---|---|---|---|
| T0-E | EKF3 | white (현재) | 기준 |
| T0-F | FG lag=∞ | white (현재) | 기준 |
| T1-E / T1-F | EKF3 / FG | E: R_ss × κ (κ는 학습 데이터 φ에서) | inflation 효과 |
| T2-E / T2-F | EKF3 augment / FG | A: GM, 시간 index | 상관 상태 효과 |
| T3-E / T3-F | EKF3 augment / FG | A: GM, 기하 index (Δs, Δψ) | index 효과 |
| T4-F | FG | B: 이동 거리 구간 bias | A의 저비용 대안 |
| T5-F (선택) | FG | D: 블록 kernel | kernel 정확 표현 |
| S-W | 위 전부 | 관측을 모델대로 white 생성 | 구현 확인, mismatch 없는 estimator 효과 |
| S-GM | A, B, E | 알려진 α, φ로 e_s 주입 | 파라미터 복원, z 관측성 |
| SEN | T0-F, T2-F | FFD 원본 vs surrogate | surrogate 민감도 |

읽는 법: T1 − T0 (inflation), T2 − T1 (상관 상태 대 inflation), T3 − T2 (index), 같은 모델 안의 F − E (estimator 효과), (T2-F − T2-E) − (T0-F − T0-E) (교호작용).

## 9. 사전 고정이 필요한 항목

- 파라미터 학습 데이터와 평가 데이터 분리 (station sweep, N1–N6 → R2/R4/R5). 평가 NEES를 보고 조정하지 않음
- α, σ_es, L_s, L_ψ, κ, φ_max, 희석 보정 상한
- surrogate 허용 기준 또는 FFD 원본 사용 범위
- gate 규칙 (EKF mask 공유 여부, 분리 factor 시 규칙)
- 판정 통계: seed 수, block bootstrap 길이, log ANEES 등가 margin δ, 포함률 기준
- iSAM2 설정 (threshold, skip)과 causal 출력 정의

## 10. 출력 형식

1. 추천 방식 (한 문단) + 근거 (확인된 사실과 가설 구분)
2. arm 표: 유효/보류/기각, 이유, 비교 질문, 통제 변수
3. 사전 고정 항목과 제안값
4. 먼저 돌려야 할 진단 1–3개와 각각의 판정 기준
5. 위험과 대안
