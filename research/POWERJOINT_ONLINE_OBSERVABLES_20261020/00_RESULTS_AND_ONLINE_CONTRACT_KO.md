# POWER_JOINT: 온라인 측정 가능 지표로의 전환 및 기존 유해/유익 구간 대조

2026-10-20 · 현재 목표: Full RF Heading 편향과 신뢰도 오판 감소. Strong coherent interference / weak Heading identifiability를 주제로 유지. CIR 고배율 처리는 보조 진단.

## 0. 실제 실행 범위와 근거
- 실행 [GitHub Actions 39354151551](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39354151551): **PASS**, 실제 Full-only feature extraction 6 routes C01/C02/C03/O01/O02/O03, 9 route-anchor cases, **2647 packets**.
- 입력 원본: Actions 39277485012의 six original Full/DirectLoS route archives. 각 Full/LoS/pose 파일의 SHA를 output receipt에 기록.
- [전체 수치·코드 artifact 12233874874](https://github.com/myoungsunk/sionna-resimulation/actions/runs/39354151551/artifacts/12233874874), 34 files, 311287 bytes, ZIP SHA256 `0bfb61fed10380913b4407a72de79e01af5e1fbece7ba412bc0d2a006ddfa816`. 30일 보존, published source scripts로 재계산 가능.
- 추정기에 쓸 feature 함수 `online_features(h)`에는 **현재 Full 두 수신 포트 H만** 입력. LoS/GT/current true heading/true arrival/true pose/future packet/cross-port coherent phase 입력 없음.
- 지표는 IFFT로 얻은 포트별 CIR **전력**에서 계산. 두 포트에 독립적인 일정 phase rotation과 공통 gain 변경에 불변인지 자동 시험 PASS. 실제 receiver 포트 상대이득·샘플시각·CIR time origin·noise는 여전히 보정 필요.
- 새로운 EKF/정책/노이즈 모델 학습 및 새로운 RF Sionna simulation: **0회**. 과거 12개 RF-skip episode 후속 Heading 영향값을 그대로 참조. 이 선택 사건의 event-median은 오프라인 집계이며 episode 진입 시 이용 가능한 값으로 주장하지 않는다.
- 첫 실행은 C01 계산 후 JSON log의 numpy-int 직렬화 문제로 중단. V2에서 `n=int(end-start)` 한 곳만 고친 뒤 전 route 다시 수행. 과학적 수식·임계치 수정 없음. Runtime 패치된 실제 소스는 artifact에 보존.

## 1. 기존 문제유형의 의미를 정정/분리
1. **강한 복소 간섭**: 이전 지표는 known direct CIR c_L와 M=c_F-c_L를 이용하여 `s_F(t_L)-s(|c_L|²+|c_M|²)`를 계산한 oracle 기여분해. C01 A worst RMS .433 등은 실제 온라인 추출 불가. 물리 원인 라벨로만 사용한다.
2. **약한 local Heading sensitivity**: 기존은 참 XY/yaw에서 SourceFFD의 `|∂h_s/∂ψ|<0.2 rad^-1`라는 진단 기준. `|s_LoS|>.95`는 LoS 전력비의 극값 인접 대리 지표이지 민감도 자체의 동치 아님. 온라인은 추정 prior와 그 불확실성 구간에서 모델 기울기를 계산하거나, gyro로 측정한 작은 제자리 yaw scan에서 Full s의 변화량을 추정해야 한다. 이 온라인 Jacobian/scan 정보량은 이번 artifact에서 계산하지 않았음.
3. **다중해**: 이전은 참 위치를 고정하고 참 Heading±45° 내의 조건부 관측식 roots를 계산. 실제 posterior multimodality나 online search 범위가 아니다. 온라인에서는 GT 기준 범위를 제거하고 추정 가능한 Heading 후보·위치불확실성·시간 정보를 사용한 다중 likelihood를 조사해야 한다. 이번 신규6 route artifact는 그런 posterior를 실행하지 않음.
4. **FP 변화**: 이전 Full vs DirectLoS detector index mismatch는 두 검출기의 차이이며 실제 경로 τ_min과의 오차가 아니다. NLoS에서는 τ_min(earliest surviving path)과 d/c(virtual unobstructed geometry)도 다르다.

## 2. 실제 계산한 Full-only online-candidate definitions
Current measured port CIR powers p+(τ),p−(τ). `s_FP` at current detected firstpath; `s_E(T)`는 그 뒤 T ns 창의 두 포트 energy ratio.
- **D_pol4 = |s_FP − s_E(4ns)|**: 선택 tap의 편파비와 초기 파형 전체 비율의 불일치.
- **σ_pol16**: firstpath 이후 16ns 창에서 per-tap s의 energy-weighted 표준편차.
- **D_scale = |s_E(4ns) − s_E(16ns)|**: 적분 시간창을 바꿀 때 편파비 안정성.
- **late_E40 = 1 − E(0–4ns)/E(0–40ns)**: 검출 이후 늦은 에너지 비율 (직접파 비율이라고 부르지 않음).
- **detector_s_span**: 같은 현재 파형에 amplitude threshold .2/.3/.4를 적용했을 때 선택되는 s의 범위.
- **envelope mismatch**: 16ns 두 포트 power profile의 cosine similarity에 대한 1−similarity (Jones phase alignment 아님).
- **|s_Full|, saturation fraction |s_Full|>.95**: 수신 포트 우세도. 이것만으로 weak gradient나 multipath 종류를 확정하지 않음.
전력비/시간창은 모두 threshold와 window를 고정한 신규 정의. Noise floor 미만 weak port, AGC gain/relative port calibration, sequential-port measurements의 위치/yaw 변화는 하드웨어 단계에서 검증해야 한다. 과거 feature 이름이 유사해도 definition/window가 다른 수치를 임의 혼합하지 않는다.

## 3. 동일 observable pattern에서 RF-skip의 기존 효과는 어떠한가?
모든 feature 값은 각 사전등록 episode의 packet median. Gain은 과거 후속 Heading RMSE(original POWER)−RMSE(local RF skipped); positive means skip beneficial. No new recursive experiment.

| event | n | skip gain deg | D_pol4 | σ_pol16 | late_E40 | detector_s_span | abs(s_Full) |
|--|--:|--:|--:|--:|--:|--:|--:|
| C01 A x16–21 V1 |51|+5.393|.3178|.3653|.4568|.1009|.5223|
| C01 A x10–16 V1 |30|−3.079|.2206|.3127|.2719|.0650|.1030|
| C01 B x16–21 V1 |51|+4.340|.1594|.2977|.2889|.0824|.5863|
| C02 A x4–10 V1 |30|+1.775|.1836|.2051|.1038|.0635|.1229|
| C03 A x1–4 V1 |15|+.767|.0344|.1244|.0508|.0057|.1189|
| C03 A x4–10 V1 |30|−3.115|.0804|.1992|.1970|.0158|.0982|
| C03 B x10–16 V1 |78|+.610|.0490|.1702|.0844|.0087|.3206|
| C03 B x10–16 V2 |78|+.537|.0490|.1702|.0844|.0087|.3206|
| O02 O0 y4–8 V1 |20|−4.330|.0830|.1475|.1662|.0595|.1048|
| O03 O0 y4–8 V1 |20|+1.798|.2161|.3344|.6143|.0476|.5623|
| O03 O0 y4–8 V2 |20|−15.347|.1606|.3294|.5389|.0355|.5403|
| O03 O0 y0–4 V2 |130|−14.462|.1357|.2323|.2068|.0400|.3757|

### 판정
- C01 A worst는 online 편파 파형 불일치도 큼. 그러나 같은 C01 A의 beneficial 구간 역시 작지 않다.
- O03 동일 y4–8 V1/V2에서 **σ_pol16=.334/.329, late=.614/.539, |s|=.562/.540로 비슷한 파형지표**지만 skip 이득은 +1.798 vs −15.347로 반대. 이는 '불안정한 파형이면 모두 RF 무시'의 반례.
- C03 A 처음 x1–4에서는 파형 불일치가 작은데 skip helpful. 다만 0–5초 초기화 사건으로 다른 구간과 진입조건이 다름.
- Full-only 지표는 O03 blocked frame에도 계산된다. 예전 oracle Full−LoS 물리표는 그 구간의 valid-direct 2/20와 3/20에만 값이 있었으므로, **이번 Full-only 전체20 packet 지표와 예전2/3 packet interference RMS를 같은 모집단처럼 비교하면 안 됨**.

### 12 selected correlated events exploratory AUC
'scalar가 클수록 skip 이득>0.2deg'를 사전 suspect 방향으로 지정. 7 positive / 5 nonpositive, no fitted classifier.
D_pol4=.4571; σ_pol16=.4857; D_scale=.3714; late_E40=.3714; delay spread=.4286; peak−FP=.5000; envelope mismatch=.4857; detector_time_span=.4143; detector_s_span=.4857; |s_Full|=.7429; saturation fraction=.7000.
**|s_Full|은 추가 검증 후보일 뿐 승인된 판별기가 아니다.** 11개 후보 중 하나가 높게 나온 소수 사건 탐색, 반복 방문/scene 상관과 selection bias가 있어 일반화나 online gate 성능이라고 쓰지 않는다. 30초 이전 시작사건을 제외한 민감도 표도 CSV에 별도 보존. 개입은 r+s 전체 RF 생략이므로 이 label이 곧 s-only 처리의 utility는 아니다.

## 4. Firstpath 과샘플링 보조점검 — 실제 실행된 4x vs16x
동일 257 CFR/Hann, 30% leading edge, amplitude normalization 동일. Grid dt 4x=.49885264 ns,16x=.12471316 ns. 이것은 같은 CFR의 interpolation이지 새로운 측정이나 실제 bandwidth 증가가 아님.

비교1: `estimated_FP_Full−estimated_FP_DirectLoS`, 비교2: `estimated_FP_Full−d/c`, 비교3: `estimated_FP_DirectLoS−d/c`. 2/3은 안테나/receiver/filter 지연보정 전의 **기하학적 참조**이며 실제 earliest ray/group delay를 전부 비교한 결과가 아니다. Blocked DirectLoS frame은 비교1에서 배제한다.

| episode | Full−LoS FP RMS ns 4x→16x | oracle delta_s RMS 4x→16x |
|--|--|--|
| C01 A x16–21 |.6440→.6014|.5061→.5230|
| C01 B x16–21 |.5675→.5586|.1611→.1379|
| C01 A x10–16 |.6754→.7081|.1891→.1684|
| O02 y4–8 |.1578→.1502|.1808→.1866|
| C03 B x10–16 V1 |.07988→.03459|.02185→.02038|

더 촘촘한 CIR로 일부 격자차/편파왜곡은 감소하지만 다른 조건은 증가. C01 B의 FP 차이는 대부분 남음. Heading EKF 재실행은 하지 않았으므로 'Heading이 개선됐다/안됐다'는 판정은 안 함.

**검출 기준 자체의 offset:** 이상적인 단일 지연18.23ns 경로, 같은 30% leading-edge에서는 (estimated−known delay)가 4x −2.2667ns, 16x −2.5161ns,64x −2.5473ns. 다중경로가 없는 synthetic unit test에서도 0으로 수렴하지 않는다. 대역제한 파형의 앞쪽 threshold 위치와 실제 delay/피크 중심은 다르므로 oversampling 전에 **어떤 arrival reference와 calibration을 평가하는지 정의해야 한다**. 이 수치를 실제 장비 offset으로 바로 사용하지 않는다. Full source에서도 LoS detector−d/c 평균은 대략 −1.6~−2ns로 0이 아니며 원본 Range 보정 규약과 구별했다.

CIR 여러 번 중첩은 이번에 실행하지 않았다. 알려진 sub-sample alignment와 동일한 물리 채널 반복이 있으면 별도 평균/재구성 시험이 가능하지만, moving pose·yaw가 달라지는 파형을 동일 채널 반복처럼 합칠 수 없다.

## 5. 약한/모호한 방향 정보를 online으로 다루기 위한 다음 계약 (제안, 이번 계산 아님)
- 현재 추정 prior x_hat_minus와 covariance가 정의하는 plausible 영역에서 SourceFFD/LUT의 |h_s,psi|와 noise-normalized sensitivity를 계산. 한 점 derivative만 보고 확정하지 않음; 과신 prior가 wrong site를 좁게 고정하면 결과도 틀릴 수 있다.
- 단순 Full |s| 포화와 '모델이 예측하는 낮은 heading gradient'를 분리. 수신 한 포트가 강한 것만으로 정상 LoS의 기울기를 알 수 없음.
- 복수 Heading 해 탐색은 true position, true yaw±45를 없애고 online 추정 불확실성과 관측/센서 motion에 기반. 모델 단독 다중해와 prior 포함 posterior 다중모드를 따로 보고한다.
- 충분한 gyro 회전이 있는 정지/저이동 scan에서 delta_s/delta_yaw를 측정, nuisance common amplitude/offset을 제거한 국소 shape-fit와 왕복 scan 반복성을 비교. 이것은 **Full 응답의 gradient**이며 LoS truth gradient가 아님. 실제 robust heading 식별성과 bias 구분에 새 검증 필요.
- 현재 waveform inconsistency + predicted heading ambiguity + pre-update innovation/prior를 공동 입력으로 평가하되, single harmful-skip label을 모든 RF의 원천진실로 학습하지 않음.
- R5 M0/M45의 prior-aware online gradient/ambiguity 수치 재계산과 R4/R5 전체 recursive 정책은 이번 자료에서 실행하지 않았음. 지난 true-pose weak-slope는 offline reference로만 보존.

## 6. 최종 결론
**물리 원인 label과 deployable feature를 분리했다.** 신규6 route actual Full-only 후보를 계산했고, 유사한 파형지표에서 RF-skip 효과가 반대인 사례를 확인했다. 스칼라 online 신호품질 하나로 모든 RF를 거절하는 규칙은 아직 근거 부족. 주요 해결방향은 강한 간섭 자체를 마치 직접 측정한 것처럼 쓰는 것이 아니라 **측정 가능한 편파 파형 불안정성과 현재 모델의 방향 식별성·prior 신뢰도를 결합**하는 것이다. 이 결합 정책의 정확도·confidence 개선은 이후 별도 자연 재귀 검증 대상이며, 현 보고서는 그 성공을 주장하지 않는다.
