# POWER_JOINT: 원본 유효 RF 기반 통합 PRE/P0–P7/E1–E6 검증 결과 (2026-10-19)

**상태:** 기존 데이터 한정 TECHNICAL_PASS / SCIENTIFIC_GENERALIZATION_NOT_PROVEN. **독립 신규 Sionna RF 생성 없음.** R2 Mount45는 사용, R4/R5 Mount45는 생성계통 동등성 FAIL(V01B)로 최종 재귀 비교에서 제외.

## 동결 자료 및 provenance
- Sionna 유효 Full/Native-LoS RF: R2_aA_m0, R2_aA_m45, R2_aB_m0, R4_aA_m0, R4_aB_m0, R5_aA_m0, R5_aB_m0 총 7 조건. 원본 ZIP 9개·소스 120개 SHA 검수.
- FFD bank LP_plus45 SHA256 `b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b`, LP_minus45 `39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9`. SourceFFD 모델 및 19,038개 레이블 route-out P1 학습 기반 기존 동결 `research/ffd-source-p0p3-20261016` commit `4b82e9801a1e065593fdd67a0f3ebd721ba29848`.
- R4 742시점/R5 1,415시점 × 4 Gyro Bias Sensor-v2: **GT 궤적 기반 합성**(원본 센서 로그 복구 아님), A/B 동기 및 결정론적 재생성 확인.
- Recurrent source model: `[x,y,psi,b_g]`, natural Gate, same initial prior/controls, R4 held route from R2+R5 train, R5 held route from R2+R4 train, R2 held train R4+R5. R2 이미 반복 사용했으므로 hidden generalization 아님.

## 새 실행 내용
- **P0:** SourceFFD 물리 s Native LoS 9519점 RMSE ≈6.59e-7(기존 동결 결과), Range `d+B_OLD` 후 LoS 잔차 7조건 RMSE ≈0.0438–0.0475m: Range source model 검증 미완.
- **E1:** R2 A M0/M45×B0/L2, four observed hybrid (r_0,s_0), (r_full,s_0), (r_0,s_full), (r_full,s_full), total 16 recursive runs, Full/LoS frozen parity EXACT. Hybrid는 오프라인 oracle negative control.
- **E3:** 7,251 paired packet signed RF residuals: R2 A M45 Pearson corr(e_r,e_s) 접근 +.279, 이탈 −.220. 다른 방향/앵커에서 일관 부호 법칙 아님; 시간상관 통계 결함.
- **E4:** 17 low-turn contiguous GT kinematics segments, R2 B0 Source POWER M0/M45 Heading RMSE 1.799/1.008° for 656 low-turn frames; 정확한 직선-leg 연구 기준보다 넓음; R4/R5 M45 없음.
- **E5:** accepted Kalman K_b,r nu_r + K_b,s nu_s exact integral, R5 A M0 B0 POWER Range +0.045633, s −0.042704 → terminal +0.002929°/s. 대수적 기여이지 변수를 제거한 인과효과는 아님.
- **E6:** R2 M0 A/B/A+B all 4 bias, block-diag optimistic C_AB=0 vs R4/R5 train-only shrunk C_AB. B0 POWER A: Heading1.799° XY0.1500m, B:1.516° XY0.0743m, A+B block:0.996° XY0.0609m. Narrow-axis nominal95 time coverage A54.2% B73.7% AB61.6%; consistent Bayesian generalization NOT PROVEN.
- **P4:** R4/R5-only train of 17 observable CIR features, R2 M0/M45×4 biases×Full/LoS×6 arms=96 recursive arms. Hard-safe LoS returns to R0 but fails Full-RF ≤10% non-degradation for all metric combinations across cases; candidate NO-GO. Same-packet q conditional score is NOT normalized p(q,r,s|x).
- **P6:** R4/R5 A/B M0 × Full/Native LoS × B0/L0/L1/L2 =32 recursive cases×9 policies=288 arms. Full POWER better than R0 in Heading12/16, XY16/16, bias16/16; R5 A Heading remains 4.556° (B0). Independent original core numerical Gaussian update recomputation 576 steps; state max diff 2.71e-20, covariance 8.67e-19, Gate mismatch0. **Not external RF repetition.**
- **P7 physics-only:** pre-existing GitHub office 35 stationary positions ×19 yaw complex Full H SHA audited (office source workflow `39197275879`); 25 LoS geometrically clear, 10 obstructed. Full RF stationary not time-recursive EKF; no independent-office trajectory RMSE.
- **P5:** R2 A M45 Source POWER B0 conditional narrow-axis NEES16.61, nominal 95% time coverage16.77%; stays overconfident. RF error ACF single deterministic moving route not enough to identify stochastic AR process.
- **PRE-2 BLOCKED:** R4/R5 M45 legacy/Native mismatch, no defensible H source parity. Existing archival inventory workflow `39195547305` contained no newly verified target paired H. Do not substitute 35×19 office static grid or fake Mount45.
- New six route simulation request for corridor/office remains [Issue #2](https://github.com/myoungsunk/sionna-resimulation/issues/2) OPEN/NOT_RUN; geometry PASS only.

## Status / Claim
`TECHNICAL_PASS`: PRE-3, source SHA, P1 corrected refit reference, E1 and P6 numerical replay. `SUPPORTED_BUT_LIMITED`: P0, P2/P3, E1–E6, P6, stationary office. `FALSIFIED (tested candidates)`: P4 clean-LoS AND Full safety together. `BLOCKED_INPUT`: R4/R5 M45 (PRE-2), P5 independent RF repeat, P7 dynamic office generalization. Original POWER baseline retained.

## Binary artifacts and delivery evidence
- Detailed 169-file SHA-verified analysis package from this execution: `POWERJOINT_INTEGRATED_EXISTING_RF_EXECUTION_20261019.zip` SHA256 `234020eba3dbae01a1e346c049354517a873923cd1e1cdf01bca91d6cf7bc3d7`. **Not committed as Git blob**: contains scientific numerical traces; download through the ChatGPT session delivery.
- The archive includes `00_RESULTS_KO.md`, `01_P6_PAIRED_MASTER.csv`, `02_P4_LOS_SAFE_RECURSIVE.csv`, `03_E3_DIRECTION_CRS.csv`, `04_E6_TWO_ANCHOR.csv`, `11_STAGE_DECISIONS.csv`, 6 figures, 131 raw numerical files, scripts and `99_SHA256_MANIFEST.json`.
- Input hashes are pinned; **output PASS means computation and provenance checks only**, never scientific claim adoption.
