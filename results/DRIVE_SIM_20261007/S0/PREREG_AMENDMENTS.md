# PREREG 수정 기록 (S0)

원본 `PREREG.json`(커밋 `02009ca`)은 수정하지 않는다. 변경은 이 파일에만 추가한다.

## A1 — G1은 production 설정(`--threads 1`)에서 판정한다 (명확화, 완화 아님)

- 원 문구: G1 "H 상대 오차 ≤ 1e-6". thread 수는 명시하지 않았다.
- 관측(`REFERENCE_CHECK.json`, 같은 position x7.0_y0.0, yaw 0/50°):
  - `--threads 1`: 저장 H와 **오차 0.0**(비트 동일, 65 bin × 2 yaw).
  - `--threads 4`: pose별 상대 오차 3.2e-6, bin별 최대 1.2e-5 → **원 임계값 1e-6 미달(FAIL)**. 원인 추정: 병렬 reduction 순서(float32 비결합성).
- 조치: production A안은 기존 scan 방식대로 단일 thread 프로세스 4개 병렬(`corridor_scan2_run.sh`)이므로 G1은 `--threads 1`에서 판정한다. 임계값 1e-6은 그대로 두고, `--threads 4`는 production에서 쓰지 않으며 FAIL 결과를 그대로 기록한다.

## A2 — S1 설계 결정 (RF/필터 결과를 보기 전에 확정)

원 PREREG에서 모호했던 부분을 구현 전에 고정한다. 모두 `assumption`.

1. **Probe 주기 T는 "주행 시간(drive time)" 기준.** probe 시간(7.2 s)은 주행 시간에 포함하지 않는다. 따라서 위치·주행 heading은 T와 무관하고, T∈{10,20,60}의 probe 위치는 T=10의 부분집합이다 → RF 계산 집합은 T=10 기준 상위집합 하나로 충분하다.
2. **Truth는 kinematic으로 일관.** 위치는 heading을 따라 적분한 unicycle 경로다(`p_{g+1}=p_g+0.04·(cosψ_g, sinψ_g)`). heading 흔들림 때문에 y가 y₀에서 ±수 cm 벗어난다. (직선 경로 + heading 흔들림은 odom 모델과 모순이므로 쓰지 않는다.)
3. **Heading 흔들림은 주행 시간의 함수**: `w(τ)=A·sin(2πτ/T_w+φ)`, A=4°, T_w=12 s, φ는 고정 seed(20261007)에서 한 번 뽑는다(truth는 Monte Carlo seed와 무관). 제자리 회전(probe, 끝 지점 180° 회전) 동안은 흔들림을 고정(hold)한다.
4. **경로 길이**: x₀=1.2 m, 편도 440 step(17.6 m), step 0.04 m. 흔들림에 의한 x 이동 감소와 허용영역 [1,19] 경계 여유(약 0.2 m)를 확보하기 위해 18 m 대신 17.6 m로 한다.
5. **끝 지점 180° 회전**: 25°/s(probe와 동일), 5 Hz 표본당 5° → 36 표본, `turn_phase` flag.
6. **Probe 표본열(36 표본 = 7.2 s)**: 현재 heading 기준 상대 yaw `[−5…−45](9) + [−40…+45](18) + [+40…0](9)`. 한 probe에서 서로 다른 yaw는 19개(−45…+45, 5° 간격).
7. **y₀∈{0, 0.35}**: y₀는 적분의 초기값. 안테나 world yaw = 몸체 yaw + 장착 offset. Lever arm 0이므로 안테나 위치 = 몸체 위치.

## A3 — 앵커 수직축 정확히 위에서는 B안이 퇴화한다 (S2 개발 중 발견, parity 결과 집계 전)

- 관측: 위치 (4.0, 0.0)(앵커 바로 아래, 수평거리 0)에서 B안(trace/pattern 분리)이 A안과 H 상대 오차 1.5e-2로 어긋난다(경로 수 51, 정상 63). 수평거리가 y=1e-4 m이면 1.2e-3, 1e-3 m이면 1.1e-4, 5e-3 m 이상이면 ≤1.8e-5로 사전 등록 G2 기준을 만족한다. LoS 단독은 정상(1.9e-5), 반사 경로가 수직 입사로 퇴화하는 것이 원인으로 추정(미확정).
- 조치(결과를 보기 전의 규칙): (a) 궤적 생성기가 수직축까지 수평거리 ≥0.01 m를 강제한다(`check_anchor_axis_clearance`; 현재 궤적 최소 0.0266 m / 0.3764 m). (b) parity gate의 기준 위치 중 수직축 위(수평거리 <0.01 m, 즉 (4.0, 0.0))는 G2 집계에서 제외하고 보고서에 `excluded_on_anchor_axis`로 남긴다. (c) G4 위치를 (5.5,0.35), (11,−0.5), (15,0)으로 바꾼다((4,0) 제외).
- G2 임계값은 변경하지 않는다.

## A4 — S4 (h_s LUT) gates, fixed before the real-bank LUT is built

- LUT grid: θ 2° over [0°, 90°], φ_tx and φ_rx 2° over [−180°, 180°) (the plan's φ 5° is replaced by 2°: with 5° ideal-dipole banks gave a max interpolation error of 3.5e-2, with 2° 5.4e-3).
- Gate L1 (interpolation): over 500 random points with θ∈[5°, 85°], \|s_LUT − s_direct\| max ≤ 1e-2 and median ≤ 1e-3.
- Gate L2 (LUT vs Sionna `max_depth=0`, 8 random corridor poses, 257 bins): \|Δs\| max ≤ 5e-3. The LUT uses a 10 m reference link, so a sub-tap position difference is part of this number.
- Reported (no pass/fail): LUT-vs-full-simulation mismatch σ_s along the trajectories, overall and by \|ds/dyaw\| bin (feeds the filter's R_s; the earlier branch value was about 0.09).

## A5 — Filter design decisions (S5), fixed before any filter run on RF data

1. **Non-identifiability.** During straight driving at constant speed the gyro bias `b` (proportional to time) and the wheel diameter-ratio error `ε` (proportional to distance) enter the odometry-vs-gyro heading difference identically; they are separated only by absolute heading (`s`) or by stationary rotation. Tests on model-consistent synthetic data showed that with prior σ_b = 0.3 dps the odom/gyro fusion alone gives 10–30° heading RMS even at the *lowest* drift level, whereas gyro-only heading gives 0.4–1.7°.
2. **Priors** are taken from the sweep populations (RMS over the three levels), identical for all conditions and baselines: σ_b = 0.12 dps, σ_SF = 1.04 %, σ_ε = 0.64 %, initial pose σ_θ = 5°, σ_xy = 0.1 m. No per-condition tuning.
3. **Extra baseline "gyro-only"** (`use_odom_heading=False`: heading from the gyro increments only, odometry used for distance): added next to the fused "odom+IMU" baseline, because the fused baseline is weak by construction (point 1). H1 is evaluated against both; the fused one is the pre-registered primary comparison, the gyro-only one is reported as the stronger-baseline sensitivity.
4. **Measurement noise the filter is told:** range R = σ_r² + quantisation (tap spacing 0.149 m, uniform) + (0.05 m)²; s R = delta-method thermal variance from the *measured* tap powers + σ_mismatch²; σ_mismatch = 0.09 until S4 reports the measured value (then the measured value is used for all conditions at once). Gate: χ²₁ 99 % for range and s, 99.9 % for the odometry heading pseudo-measurement (slip).
5. **Range model offset:** the first-path range is quantised (taps 0.149 m) and biased by the 30 % leading edge; the filter uses a constant offset computed from a flat-spectrum LoS channel passed through the same chain, averaged over distance (no trajectory data).

## A6 — S4 gate L1 result (real FFD banks, 2° grid; local development run, deterministic so the Snowball build must reproduce it)

- 500 random points, θ∈[5°, 85°]: **max |Δs| = 0.0240 (threshold 1e-2: FAIL)**, median 5.3e-4 (threshold 1e-3: pass); 5/500 points exceed 1e-2, 14/500 exceed 3e-3.
- All five exceedances sit near |s| ≈ 0 – 0.2 at specific (φ_tx, φ_rx); the cause is not smooth interpolation error but jumps of the first-path chain (the 30 % leading-edge tap changes between neighbouring grid cells), which a trilinear table cannot follow.
- The threshold is **not** changed. The effect is far below the filter's mismatch component (σ_mismatch ≈ 0.09), so it is carried as a known limitation of the LUT; a finer grid would reduce the width of the affected cells but not remove the jumps. The measured trajectory-level mismatch σ (S4 report) is the number the filter uses.
