# 시스템 수준 검증 — 구현 고정본 (2026-10-23)

근거 문서: "편파 heading 채널의 근본 재검토와 2차 검증 계획"(Claude 문서). 이 파일은 그 2차 계획을 코드에 어떻게 옮겼는지, 각 결과로 무엇을 판단하는지를 실행 전에 고정한다.

- 모든 항목은 진단이다. 운용 arm(BASE, CIR, WIDE_NOES, PWIDE_NOES, ORACLE)은 바꾸지 않는다.
- 판정 임계값은 두지 않고 크기로 보고한다.
- GT를 쓰는 출력에는 `uses_gt`, held 라벨을 쓰는 출력에는 `uses_held_labels`·`in_sample` 플래그를 붙인다.

## 실행

`.github/workflows/p2-sysdiag.yml`은 이 commit으로는 돌지 않는다. 실행하려면 `RUN_SYSDIAG.txt`를 만들거나 수정해 push하거나, `workflow_dispatch`로 단계를 골라 돌린다. 결과는 `results_sysdiag/`에 쌓인다.

| 단계 | 스크립트 | 입력 | job |
|---|---|---|---|
| 1 | `p2_sysdiag.py` | v3 배열 14개(run 39950207483, 39954439738), P4 곡선(run 39961254971 B0) | 1개, 4 worker |
| 2 | `p2_nopol.py` | 원 RF·trace, ladder-4 모델 | 7 case × seed 4묶음 |
| 3 | `p2_innerloro.py` | HP_PACKETS, P1R heading 격자(run 39752301964), ladder-4 모델 | held route 3개 |
| 집계 | `p2_sys_aggregate.py` | 위 산출물, MC_ALL.csv | 1개 |

## 항목별 구현과 판단

| 항목 | 구현 | 판단에 쓰는 결과 |
|---|---|---|
| V1 g 복조 | 평가 시점(t ≥ 60 s)마다 커널 W를 age 구간 × [g/R, g·S/R] 기저(변조형)와 [1/R, S/R] 기저(비변조형)로 적합. 공유 형태 w(age) + 시점별 척도 1개의 ALS 적합 | 변조형 공유 형태의 설명 에너지가 비변조형보다 큰가. c(t)를 b_ψ(T)가 얼마나 설명하는가(R²). ε 대역 몫과 u = gε/R 대역 몫의 차이 |
| V2 편파 단독 GLS | 참 위치·참 기울기 g_gt, 회귀자 [g, g·S](S는 저장된 F의 곱), Γ = 백색(V_s 비례) + AR + GM + 상수 + gyro random walk, bias prior. Γ 출처 3가지: cross-fit 매개변수형, in-sample 매개변수형, cross-fit 경험 ACF(Bartlett 테이퍼, PSD 투영) | 편파 정보만으로 가능한 heading 하한(기대·실현). EKF 편파 성분과의 비는 헤드룸이 아니다. 정보 집합이 달라 그 비교는 V2′가 맡는다 |
| V2′ 상관 모델 필터 | 저장된 F, G, H, accept로 증강 Riccati를 계산하고, 실현 입력(dm₀, w, r_pred, ε, r_meas)을 넣어 오차를 재귀한다. 변형: base, pol_ar, pol_slow, pol_full(+consider), rng_full, both_full(+consider, +xcorr), x2_eff(physgain, effgain) | 각 변형의 heading·tangential RMSE와 NEES를 base 대비 비로 본다. cross-fit과 in-sample의 방향이 같을 때만 "여유가 있다"로 쓴다 |
| V3 편파 순가치 | NOPOL(range 단독 갱신, χ²₁(0.99)), R_s ×3·×10·×30 스캔, 12 seed | 어느 case에서 NOPOL보다 나쁜가, 편파 가중을 줄이면 어떻게 변하는가 |
| V4 여기 | 60 s 창(10 s 간격)마다 g_gt의 평균·SD·부호 전환, η = gᵀΓ⁻¹g / gᵀdiag(R)⁻¹g, corr(MA30(ε), g) | η·부호 전환이 case 성패와 같은 순서인가 |
| V5 inner LORO | 학습 route 둘 사이 A → B: BASE(μ_inner), WD0, PX1, PD0, PA2(30 s 평활 target). d0는 GT. B 궤적의 b_ψ(10/30/60/120 s) | 학습 route만으로 낸 b_ψ 비(PD0/BASE)가 held 재귀 비와 같은 방향인가(C1). PA2가 b_ψ를 줄이는가(A2) |
| X1 held 진단 | 배치 모델, in-sample 모델, 시간 반분 2-fold 모델의 b_ψ | in-sample로도 b_ψ가 안 줄면 특징에 정보가 없다. in-sample에서만 줄면 일반화 문제다 |
| X2 d0 되먹임 | P4 곡선으로 κ = 1 − Δê/Δd0(±1°)를 구하고, 입력에서 c2를 빼고 편파 행을 κH_s로 바꾼다 | physgain 상태와 저장 상태의 차이 = 선형 β 모델의 설명 오차. effgain = 필터가 κ를 알 때의 반사실 |
| X3 교차 상관 | MA30(ε_r)과 MA30(ε_s)의 상관(cross-fit)을 b·c 쌍의 P₀·Q 교차항으로 | both_full과 xcorr 판의 차이 |
| V6′ 장착각 | R2_aA_m0 vs R2_aA_m45(같은 route·anchor), e = s_F − s_LoS의 원·느린·빠른 성분 상관 | 편향이 안테나 방향에 얼마나 묶이는가(δ = 45° 한 점) |
| V7 재방문 | \|Δp\| < 5 cm, \|Δψ\| < 5°, \|Δt\| > 20 s 쌍의 ε 상관(Δt 구간별) | 쌍이 있으면 공간장 여부. 없으면 "현재 데이터로 불가"로 기록 |

## QA (계산 무결성 확인용이며, 기전 증명이 아님)

- 1단계:
  - 커널 재계산 vs 저장 float32
  - bias 레버 S vs 전파
  - V2′ base의 이득·상태가 저장값과 1e-8 안에서 일치(assert)
  - 참 상태 h vs 저장 hgt
- 2단계: BASE/PWIDE/ORACLE이 12 seed 전부에서 MC_ALL과 1e-6 안에서 일치(assert)
- 3단계: P_D0를 같은 행·seed로 재학습한 예측이 저장 모델과 1e-12 안에서 일치(assert). P1R 격자 +1° 노드 vs 저장 LUT
- 각 단계에서 manifest(스크립트 SHA, git commit, argv, 입력 SHA, 출력)를 남긴다.

## 구현 후 감사에서 고친 것

- V2의 "EKF/GLS" 비가 헤드룸처럼 읽히는 문제: 열 이름을 `ekf_pol_part_over_polonly_gls`로 바꾸고 V2′를 헤드룸 지표로 지정했다.
- V1의 시점별 적합은 기저가 유연해 변조형·비변조형이 비슷하게 맞는다(합성 데이터 0.94 vs 0.94). 그래서 공유 형태 ALS 적합을 추가했다.
- V2 경험 ACF판, bias 레버 전파 QA, X2(κ 유효 기울기), X3(교차 상관), 채널별 커널 가중 합, uses_gt 플래그, manifest를 추가했다.
- 증강 필터의 백색 잡음 바닥을 γ(0)의 1e-6에서 1e-3으로 올렸다. 합성 시험에서 1e-6일 때 in-sample AR 적합이 거의 무잡음 측정을 만들어 발산했다(NEES 364).
- NOPOL은 joint χ²₂ 대신 range 단독 χ²₁(0.99) gate를 쓴다.

## 남는 한계

- V2′는 원 EKF의 선형화와 gate 결정을 고정한 1차 반사실이다. 새 필터는 다른 궤적을 갈 수 있다.
- Γ는 정상성 가정이다. 느린 편향은 공간장일 수 있다(V7).
- V6′는 δ = 45° 한 점뿐이다.
- route 3개, case 7개다. C1은 route 3점의 비교라서 규칙 검증이 아니다.
- V1의 g/R 기저는 실제 이득의 g/S를 근사한다(S = HPHᵀ + R).
