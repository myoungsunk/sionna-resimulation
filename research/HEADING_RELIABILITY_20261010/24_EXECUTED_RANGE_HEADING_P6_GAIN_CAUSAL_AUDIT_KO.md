# 24 — Range-only EKF: 실제 전체 P6의 Range→Heading gain 개입 실험

작성일 2026-10-11. **실제 실행 성공**: [GitHub Actions 38116168650](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38116168650), 7개 기존 RF 케이스 × 3drift × 8seed × 6조건 = 1008개의 동작 중 EKF run. 기존 H와 원 센서-v2 소스 유지, 새 Sionna RF 없음. 각 실험은 same original Tnone progress 30s 이후 RMSE/poseNEES 계산. 서로 다른 7케이스는 하나의 물리복도이다.

## 1. 전체 P6 수식과 실제 개입

x6=(x,y,psi,b_g,SF_g,eps_wheel).
single-anchor range z=d(p)+b_off+e, Jacobian H_r=[hx,hy,0,0,0,0].
원 최적 range gain K_full=P6 H_r^T/(H_r P6 H_r^T +R); yaw gain Kpsi=(Ppsix hx+Ppsiy hy)/S, yaw increment=Kpsi×innovation.

대조군:
A_ODOM: no range;
B_FULL_P6: source native sensor-v2 range-only scalar Joseph full K6;
C_KPSI_ZERO: same measured RF range, same P6, same initial, same sensor seed, same rejection; only direct range Kpsi=0, remaining K gain retained, Joseph update;
D_KXY_ONLY: Range update K[2:6]=0; updates XY only, preserves all P6 correlations through Joseph. In original v2 this leaves heading exactly equal odom-only trajectory (because range then does not modify gyro calibration states).
E_CAL_FULL_P6: training OTHER TWO ROUTES mean range bias/conditional variance/AR1 redundancy scalar R inflation; full K6.
F_CAL_KPSI_ZERO: same E model but zero direct range heading gain. In all interventions the nonoptimal gain Joseph covariance is PSD; these controls are **not approved production filters** and preserving full P6 does not mean missing biases are modeled.

## 2. 실측 run-average RMSE, NEES (168×6 filter trials)

| Arm | Heading RMSE ° | Pos RMSE m | Pose NEES | Heading NEES | Conditional XY NEES | Heading sigma median ° | Pose95 coverage |
|---|---:|---:|---:|---:|---:|---:|---:|
| A_ODOM | 8.93467 | 1.00736 | 8.87003 | .78462 | 8.08541 | 11.183 | .83379 |
| B_FULL_P6 | 9.79224 | 1.28536 | 1285.374 | 43.5830 | 1241.791 | 2.262 | .14973 |
| C_KPSI_ZERO | 8.49065 | 1.12411 | 467.712 | 2.10156 | 465.610 | 6.836 | .22274 |
| D_KXY_ONLY | 8.93467 | 1.23772 | 344.630 | .78462 | 343.845 | 11.183 | .20844 |
| E_CAL_FULL_P6 | 6.95167 | .80415 | 146.519 | 11.9552 | 134.564 | 3.707 | .51321 |
| F_CAL_KPSI_ZERO | 6.95863 | .84019 | 68.6852 | 1.19964 | 67.486 | 7.730 | .59197 |

Matched B−C direct yaw-gain effect: heading RMSE +1.30160°, position RMSE+.16125m, poseNEES+817.66 averaged over same168 runs. This shows direct range→heading path CAN harm badly under source RF bias and nominal fixed R. But not universally: fraction B better than C for heading ~34.5%; R2A-m0 heading B 9.12° vs C8.15°, R5B-m0 B10.13° vs C13.29° (B better). **Do not blanket-disable Kpsi**.

Matched E−F corrected range: heading RMSE −.00696° (essentially equal), position RMSE −.03604m (full P6 better), poseNEES+77.83 (full P6 inconsistent vs constrained). The benefit-cost changed after conditional bias and R model were corrected. P6 position–yaw gain is not intrinsically bad; its source calibration was inadequate.

Representative pre-range direct Kpsi absolute median .0236rad/m in full-B (note A hypothetical Kpsi without updates is larger and NOT an applied gain). Abs(range-triggered direct yaw correction) mean per evaluated normal tick .1008°, 90th percentile 0.267° among every-tenth accepted measurement sample. Full-B median posterior heading sigma2.26° while actual heading RMSE9.79°, explaining heading NEES43.58. Full-E sigma3.71° and RMSE6.95°, heading NEES11.96. In B accepted range packets per full T10 physical trace about1001 times; repeated coherent biases can accumulate.

## 3. Why Range can change heading when Hpsi=0; and heading affects next Range

Range directly: z_r independent psi given fixed p, ∂d/∂psi=0. Nevertheless P6 has cross Ppsix/Ppsiy and calibration cross with psi, so Kpsi and Kbg/Ksf are nonzero. Range update changes x/y/psi/calibration and the later gyro wheel motion estimate.

If Kpsi=0 only, remaining range-to-calibration K[3:6] changes later propagation, so heading RMSE can still differ from A. If K[2:6]=0, same gyro/wheel input yields original heading trajectory, as observed.

Conversely dynamics F_xy,psi~ds[-sinpsi,+cospsi], so earlier heading error drives future xy drift. Predicted later range sees this via Hr F_xy,psi and innovations. This is dynamic bidirectional coupling, NOT a direct instantaneous range measurement of heading.

## 4. Exact Schur NEES decomposition

For pose covariance P3=[Pxy A; A^T Ppsipsi], error vector [e_xy,e_psi],

NEES_pose= e_psi²/Ppsipsi+
  [e_xy − A e_psi/Ppsipsi]^T
  [Pxy−AA^T/Ppsipsi]^{-1}
  [e_xy−A e_psi/Ppsipsi].

This equation was checked EVERY evaluated step in replay (numerical tolerance). B's 1285 PoseNEES has heading43.58 and conditional XY1241.79: the main statistical overconfidence is radial/XY even though erroneous range-to-heading also contributes. Turning off direct Kpsi decreases total NEES but alone leaves conditional XY465.61 — far from consistent (expected 2 for conditional XY, 1 heading when ideal posterior).

## 5. What this does/doesn't establish

- **Established:** existing bias-corrupted UWB range changes heading via measured full P6, and biases both heading estimate and Pψ. Full gain corrected model improves position relative to forcing zero heading gain. This is a controlled intervening nonoptimal Kalman gain experiment.
- **Not established:** optimality of constrained gain in a new scene, or whether single-anchor localization itself must be inconsistent. Single absolute range has radial geometry only and unknown site bias poorly identifiable; adequate Q/R and priors could yield consistent uncertainty.
- **Not established:** unobserved noise-state cross covariance is calibrated. Range E improvement remains NEES146.5/coverage51.3%, not PASS.
- **Limitation:** truth is used only in evaluation error metrics; location/heading truth never used to choose intervention gains, update or range model. same corridor 7cases and original t-sequence; no new antenna 45 pairs.

Original paper framing: single range-aided navigation's observability depends on motion and known priors; UWB NLOS biased KF and Schmidt nuisance-state processing are known alternatives. See 22 design plan; now augmented with measured P6 mechanism.

**Execution artifact:** range-heading-full-P6-7case-causality-audit, original Actions full run38116168650; original scripts run_range_heading_gain_causal_ablation.py and run_range_bias_consistency_ablation.py in this branch.
