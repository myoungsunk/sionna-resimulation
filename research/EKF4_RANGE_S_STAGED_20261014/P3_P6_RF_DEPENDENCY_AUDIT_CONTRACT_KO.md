# P3/P4 staged RF reuse contract — 2026-10-14

Purpose: bridge original EKF3 frozen RF one-step evidence to the new EKF4 line of work **without claiming four-state RF recursive performance**.

Original independent one-step run 38331588521, immutable input/output artifact 11782748118, ZIP SHA256 88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63. Seven case IDs x two RF modes; seed0, same prior per arm. Frozen original RF H and LUT and archived Sensor-v2 were validated in the original source's P0; no new sensor realization here.

P3: before running any Python numerical code, audit source, expected zip/source manifests and workflow, validate raw artifact SHA, output ZIP CRC. Then read each NPZ and verify all 14 case×channels carry time, pose ID, prior x/P, z_s/z_r, H, R, innovation, NIS and frozen arm states; valid dimensions/time alignment and absence of truth in estimator inputs. This is an **artifact-reuse input eligibility check**, not a new live H reprocessing experiment.

P4 limited scope: use frozen per-time original same prior and original Jacobian/measurement at accepted one-step to reconstruct the fixed-linearization Kalman update, compare joint vs exact sequential whitened Range then s when noise is independent; preserve original gate mask, posterior covariance and no duplicate RF likelihood. A single named output must not be interpreted as position-RF accuracy improvement or 4-state bias tracking. If original outputs are incompatible, block only this P4 parity claim and report.

P5: wide prior/heading multimodal reference needs full forward nonlinear LUT and accurate position integral; archived G3 high-order TV 0.387065>0.001 remains NOT_VALIDATED. Do NOT falsely pass P5 from linearized P4.
P6: four-state full recursive RF field claim needs 4-state adapter, new actual RF trajectory and independent scene; not available merely from the current one-step artifact. Do NOT declare P6 PASS.

Every future numerical /diagnostic run must follow source+archived-input audit. No P3/P4 science execution before preaudit. Do not change previously frozen raw H, P0, Q/R, reference outcomes, gate decisions or event SHA. A lack of P2 all-route improvement cannot prevent independent P3 data eligibility. This contract scopes each decision to relevant evidence.
