# R2 Anchor A Mount 0°/45° — B0/L0/L1/L2 Gyro Bias, S-only vs Joint vs R→s 재선형화 3/4state

## 결과 범위와 증거

- 본 분석은 **P4 기존 one-step source와 독립적인 새 R2 원시 입력 재생**. Original Sionna/FFD frozen RF [EKF3 artifact 11782748118](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38331588521/artifacts/11782748118), archive SHA256 `88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63`.
- 최종 source commit `81cdffbdedf43b318ebf8eddb4fcbac1fd30d878`; [GitHub Actions Run 38664617622](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38664617622), [artifact 11940333419](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38664617622/artifacts/11940333419), artifact ZIP SHA256 `ac98c5b50077484f10bb3898138c46115d4921ac099753c5f935db33521da399`. Full input/observer SHA audit GO, six sensor/model math regression tests PASS, seed0 B0 DR-only **frozen reference x/P maximum parity exactly zero** for both mounts/LoS/Full. 16 scenario records × two modes × eight methods = 256 complete metrics rows; sample count 979 per scenario, evaluation t≥30 (829 frames). Source ZIP CRC PASS and 49 evidence files preserved.
- **Important erratum:** The initial run [38664174582](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38664174582) accepted SR3/SR4 through `if alg.startswith("S")` and therefore silently treated SR as s-only. That earlier SR result is INVALID despite workflow success. New source replaced dispatch with `if alg in ("S3","S4")`, added a nonzero-Range-innovation SR regression and mandatory static branch check. **Only final run 38664617622 comparisons below are adopted.**
- 原 Sensor-v2 `DRIFT_LEVELS`: L0 +0.01°/s, L1 +0.05°/s, L2 +0.20°/s. Added **B0=0** control. This is **positive fixed bias + original paired Gyro/Wheel white noise**, all other systematic gyro_sf/wheel_asymmetry/wheelbase/common_scale forced zero; slip off, bias random walk zero. Sensor seed0 held identical across levels/mounts, shared initial perturbation. This isolates Gyro Bias; `condition='all'` stress (with other drifts/slip) is a different experiment and is NOT measured here.
- Both R2 Anchor A fixed conditions `R2_aA_m0`, `R2_aA_m45`; full/LoS frozen observation paired from 979 original frames. This **one RF corridor and one sensor noise seed** is not a generalization/independent scene study.
- **One-step**: DR3/DR4 independently propagate their *own DR-only* priors (4state develops pose–bias covariance), each RF arm uses corresponding prior and discards RF posterior before the next frame. **Recursive**: each DR/S/J/SR posterior moves to the next motion prediction. No truth is supplied to the filter, and original trace truth is used only once for approved Sensor-v2 simulation then offline scoring.
- `DR3, DR4, S3, S4, J3, J4, SR3, SR4` all implemented, with scalar χ²(1) 99% gate for S, χ²(2) 99% pre-gate for J/SR; each method evaluates its own prediction and gate, does not use truth-based common mask. SR is Range update ONCE → fresh LUT s update ONCE on the same original R0. Observation R0 and frozen LUT unchanged.

## Key recursive Heading RMSE (deg), each 829 evaluation frames

| Bias | Mount | RF | DR3/4 | S3 | S4 | J3 | J4 | SR3 | SR4 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| L0 .01 | 0° | LoS | 1.69 | 0.76 | 0.53 | 0.73 | 0.50 | 0.73 | 0.50 |
| L1 .05 | 0° | LoS | 6.59 | 3.53 | 0.51 | 3.45 | 0.40 | 3.45 | 0.41 |
| L2 .20 | 0° | LoS | 24.97 | 17.78 | 0.67 | 17.94 | 0.24 | 17.95 | 0.24 |
| L0 .01 | 45° | LoS | 1.69 | 0.82 | 0.18 | 0.76 | 0.11 | 0.75 | 0.11 |
| L1 .05 | 45° | LoS | 6.59 | 3.61 | 0.19 | 3.29 | 0.12 | 3.29 | 0.12 |
| L2 .20 | 45° | LoS | 24.97 | 20.64 | 0.26 | 17.37 | 0.16 | 17.35 | 0.16 |
| L0 .01 | 0° | Full | 1.69 | 1.20 | 15.36 | 1.24 | 7.50 | 1.23 | 7.50 |
| L1 .05 | 0° | Full | 6.59 | 5.83 | 15.43 | 5.57 | 7.54 | 5.57 | 7.55 |
| L2 .20 | 0° | Full | 24.97 | 19.90 | 15.67 | 19.89 | 7.52 | 19.89 | 7.50 |
| L0 .01 | 45° | Full | 1.69 | 0.70 | 1.69 | 0.72 | 0.84 | 0.72 | 0.84 |
| L1 .05 | 45° | Full | 6.59 | 4.10 | 1.69 | 4.24 | 0.84 | 4.24 | 0.85 |
| L2 .20 | 45° | Full | 24.97 | 21.41 | 1.67 | 20.34 | 0.85 | 20.34 | 0.85 |

B0 control additionally: LoS Mount0 DR 0.48°, S3 0.24°, S4 0.54°, J3 0.23°, J4 0.52°; LoS Mount45 DR 0.48°, S3 0.12°, S4 0.17°, J3/J4 0.11°. Full Mount0 DR0.48°, S4 **15.36°**, J4 **7.49°**; Full Mount45 S4 1.71°, J4 0.84°. **An unnecessary bias state can absorb biased Full RF evidence even with true gyro bias=0.**

## One-step vs recursive L2 +0.20deg/s Heading RMSE

| RF/Mount | DR3/4 | One-step S4 | One-step J4 | One-step SR4 | Recursive S4 | Recursive J4 | Recursive SR4 |
|---|---:|---:|---:|---:|---:|---:|---:|
| LoS / 0° | 24.97 | 17.42 | 13.24 | 8.86 | 0.67 | 0.24 | 0.24 |
| LoS / 45° | 24.97 | 17.00 | 16.77 | 16.17 | 0.26 | 0.16 | 0.16 |
| Full / 0° | 24.97 | 19.73 | 15.36 | 12.48 | 15.67 | 7.52 | 7.50 |
| Full / 45° | 24.97 | 19.22 | 18.88 | 18.48 | 1.67 | 0.85 | 0.85 |

One-step prior already includes **propagated DR4 pose–bias cross-covariance**, so one instantaneous RF update can update bias. However the RF-updated posterior is DISCARDED before next frame, unlike recursive. Therefore one-step cannot demonstrate accumulated Bias correction in future motion.

## Why S-only needs a 4-state comparator

`H_s=[∂s/∂x,∂s/∂y,∂s/∂ψ,0]`; this does not imply no bias information. During DR4 prediction `F_{ψ,b}=-dt` produces nonzero `P_{ψ,b}` and `K_b=P_{b,pose}H_s^T/S`. S4 can thus estimate b from correlated pose history even though `∂h_s/∂b=0`.

At L2 final recursive Bias estimate ±reported posterior 1σ, units deg/s:

| Mount/channel | S4 b_hat ± σ_b | J4 b_hat ± σ_b | True |
|---|---:|---:|---:|
| 0° / LoS | +0.1953 ± 0.0039 | +0.1996 ± 0.0022 | +0.2000 |
| 45° / LoS | +0.1989 ± 0.0033 | +0.2017 ± 0.0019 | +0.2000 |
| 0° / Full | +0.1041 ± 0.0050 | +0.2087 ± 0.0026 | +0.2000 |
| 45° / Full | +0.2065 ± 0.0036 | +0.1993 ± 0.0019 | +0.2000 |

Full R2 mount0 **S4 underestimates b by ~0.096deg/s yet reports ±0.005deg/s**. Full J4 b is near true +0.20, but Heading RMSE remains **7.52°**. Bias-state estimation alone does not repair Full multipath heading/position distortion.

## Overconfidence: actual 95% coverage / NEES under L2

| Channel/Mount/Model | Heading RMSE | Heading NEES mean | Heading 95% | Pose NEES mean | Pose 95% |
|---|---:|---:|---:|---:|---:|
| LoS / 0° / J4 | 0.243° | 0.312 | 100% | 2.46 | 96.6% |
| LoS / 45° / J4 | 0.158° | 0.148 | 100% | 6.37 | **65.0%** |
| Full / 0° / J4 | 7.521° | **86.37** | **16.3%** | **297.85** | **16.8%** |
| Full / 45° / J4 | 0.848° | **3.86** | **60.0%** | **86.84** | **0.0%** |
| Full / 0° / S4 | 15.666° | **402.14** | **17.9%** | **521.56** | **18.8%** |

A correct final b estimate is insufficient for calibration. **Full mount45 J4 has relatively small Heading RMSE 0.85°, but pose95 0%, meaning position covariance is grossly optimistic.** Correlated timepoints mean these are diagnostic rather than independent ensemble confidence intervals.

## Interpretation / unresolved science

- **LoS:** high Bias L1/L2 4-state (both S4 and J4) strongly improves recursive Heading versus 3-state. Range can improve LoS under some conditions; SR4 vs J4 recursive almost equal.
- **Full:** model mismatch strongly mount dependent. Mount0 bias0 S4/J4 spurious b and Heading errors; mount45 improves RMSE but Position NEES can be huge. Do not infer calibrated posterior from low RMSE or copied R0 covariance.
- **Gyro bias level sign positive only**; no negative sign, no independent sensor seeds, no Sionna new scene. Other drift terms disabled by construction, so results isolate gyro bias; do not label them Sensor-v2 `all` L0/L1/L2 stress outcomes.
- Original P4 R4 MAP smoother solver was not modified. P4 separate nonsmooth pilot on 20 frozen failures is reported in its own branch; not merged into these EKF-only inference results.
- `scientific_PASS=false`; no generalized claim or calibrated RF advantage. Pending: multi-seed + negative-sign paired confirmation, L0/L1/L2 `all` sensitivity, Full RF R covariance/signed-bias calibration, multimodal/P5 and P6 physical reference.

**Frozen comparison outputs:** all raw `estimate,covariance,status,NIS` per case, channel, bias level, mode. Every RMSE/NEES was computed by a separate scorer after replay; source, frozen RF, and output SHA recorded.