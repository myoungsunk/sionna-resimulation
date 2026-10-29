# A4 정의·효과 분리 감사 — 실행 상태와 추가 계약 (2026-10-29)

## 1. 동결할 네 arm
- BB_ORIG: `mu_B`, `R0`
- MB_ORIG: `mu_M`, `R0`
- BB_VAR_LEGACY: `mu_B`, `R0+diag(0,sigma(rho_previous_posterior)^2)`
- MB_VAR_LEGACY: `mu_M`, `R0+diag(0,sigma(rho_previous_posterior)^2)`
- `*_VAR_PRIOR`: `rho_current_prior` (predict 이후)의 sigma 조회. 역사적 MB_VAR와 소급 혼용 금지.
- `BASE_FIXED`: BB_ORIG NIS mask를 모든 arm에 고정. `SELF_NIS`: 해당 arm의 own R,mu,x,P로 NIS/수용 갱신.
- Original accepted-mask source: original `exp_pb.gated_mask`, threshold `9.210340371976184`.

## 2. 실제 완료된 QA
- [RA4 336-arm workflow #40859507594](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40859507594): TECHNICAL_RETROSPECTIVE_COMPLETE. 336 arm / interaction 224 rows / gate pairs 168 / legacy full state covariance parity 112 rows.
- Historic 392-row independent-logic 2x2 source audit: [#40859618029](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40859618029).
- MB_VAR relative BB_ORIG fixed gate: Heading 23/28, XY 20/28, both 19/28. Self NIS: 12/28,12/28,8/28.
- PRIOR and LEGACY improved-counts same but not necessarily numerical RMSE same. Gyro levels are repeated on the same RF cases and are not independent experiments.

## 3. NOT_RUN diagnostic gates (must not be marked PASS)
A4-I1: `sigma_b(rho) = 0` injection for each mean, gate, case, bias. Check VAR_LEGACY/PRIOR states, P, mask, scores against respective ORIG; max absolute X/P <=1e-10; mask exactly equal.
A4-I2: force `mu_M = mu_B`; compare corresponding BB/MB arms under each gate and sigma timing; X/P <=1e-10 and mask exact.
A4-I3: sigma timing intervention invariance. At every packet log `rho_post_prev,rho_prior_current,sigma_legacy,sigma_prior,R_ss,NIS,K,x-,P-,x+,P+,mask`. All other input bytes must be equal (z,mu,R0,controls,Q,x0,P0,H,spec,packet keys). First difference must arise at sigma lookup, then R, K and state.
A4-I4: pair BASE_FIXED and SELF_NIS with same mu/variance and initial state. Locate first changed accept decision; require same `x-,P-,R,mu` before this packet (<=1e-10), record NIS/innovation and current update. Follow all subsequent recursive deviations to RMSE, NEES and coverage; separate number accepted, rejected and swapped.
A4-I5: initial XY, heading, gyro bias, wheel+gyro noise separate controlled factors. Original `build_controls` uses seed=0, initial std [0.1m,0.1m,5deg], gyro levels B0=0,L0=.01,L1=.05,L2=.20deg/s; zero wheel/gyro noise and independent noise/initial seeds are distinct experiments and must be frozen in advance. Explicitly verify changing bias leaves wheel controls and stochastic noise fixed.
A4-I6: score and policy. Baseline and VAR use SAME scoring window `t>=30 s`, same route/pose denominator; report heading/XY, normalized heading and XY NEES, 95% coverage, n_accepted, first flip and all masks. Both improvement and deterioration are valid if the intervention QA passes.

## 4. Interpretation and gates
- Inflating `R_ss` weakly decreases the NIS *at a fixed prior and innovation*, potentially admitting packets that baseline would reject. Once gate masks differ, x/P trajectories diverge; packet-dependent NIS can then change in either direction. First-flip and matched-prior tests are required before attributing final RMSE worsening to newly accepted samples.
- Fixed gate gives a controlled set-of-updates comparison, NOT an online policy performance claim. Self gate changes both weights and selection policy, so it must remain a separate estimand.
- Archived `mu_M` is packet-keyed; self gate with archived mu does not itself establish deployability of an online learned prediction.
- A4 full-factorial metrics are source-conditional and retrospective. The independent physical H gate and separate auditor remain outstanding.
- Fail-close: missing checksum, nonparity, any unreported changed input, bad solver physics claim, case omission -> BLOCKED; do not tune threshold post hoc.

## 5. Needed output
`A4_IDENTITY_FIXTURES.csv`, `A4_FIRST_GATE_FLIPS.csv`, `A4_SIGMA_LOOKUP_FIRST_DIFF.csv`, `A4_SENSOR_FACTORIAL.csv`, `A4_INPUT_SHA_MANIFEST.json`, `A4_QA.json`.
`A4_QA` may PASS technical intervention even when RMSE worsens; science release requires independent review and source/physics qualifications.
