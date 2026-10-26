# Office -> Corridor POWER / PWIDE / polarization gate transfer — code V1

**Status: CODE IMPLEMENTED / SYNTHETIC UNIT QA PASSED / REAL RF FIT & REPLAY NOT EXECUTED.**

## What is implemented

- Pinned release names, archive SHA256, array SHA256, and audited RF row counts (O01=192, O02=207, O03=412).
- Explicit `fetch` verifies archive SHA256, and secure `prepare` extraction rejects tar links/path traversal. **Nothing downloads automatically**.
- Office source loader calls the original `research/POWERJOINT_AUDIT_RERUN_20261020/T2_NEW_ROUTE_BASELINE/prepare_inputs.py` at commit `034e57a...`: validates release receipts, reconstructs the entire `.25 s` motion with the original route generator, and requires public `RADIO_POSE.csv` **byte identity**. Never does timestamp-nearest joins or RF interpolation.
- `H_FULL.npy`/`H_DIRECT_LOS.npy`/`LOS_EXISTS.npy` hash checks. Blocked Office samples remain in the saved source table, but are excluded from supervised calibration (`valid_for_training=False`, GT labels NaN).
- Frozen Hann, 4× zero-padding, strongest-port 30% FP and shared two-port FP, offset `s(fp±1,2,4,8)` observer, first-path power and range. Uses original TX+ (`H[:,:,:,0]`).
- SourceFFD at **source GT only** supplies Office supervised errors `e_r`, `e_s`. `s_direct_los_audit_only` records direct-LoS parity separately. All target inference paths explicitly use only observable RF and prior state, not target LoS or GT labels.
- Source-only **POWER_BIN_JOINT**: one-dimensional power Ridge, source tertile-bin residual mean/covariance, shrinkage, covariance floors, diagonal `POWER_DIAG` inference.
- Office **LOO-route** POWER teacher for supervised residual label `delta=e_s-mu_power_inner`. Repeated physical `(x,y)` is spatially embargoed within teacher folds. Caution: 3 routes share one Office scene; not 3 independent environments.
- Frozen CIR-only PCIR and CIR+`d0` PWIDE: HistGradientBoostingRegressor matching P1R settings, 3×±20-degree source-only prior augmentation.
- Office-only gate `tau=quantile_95(|d0_GT_source|)` as a **preliminary proxy**, not independently calibrated to prior errors. D0 / state-aware gating supported.
- Target 4-state P2 recursive EKF replay at **R2/R4/R5 only**, frozen sensor-v2, SourceFFD and original P2 trace inputs. Arms: `C_POWER` (in-domain control), `O_POWER`, `O_PWIDE`, `O_POWER_G`, `O_PWIDE_G`, `O_PCIR`, `O_POWER_STATE_G`, `O_PWIDE_STATE_G`.
- True range-only 1D update when polarization is gated (99% chi2_1=6.635), otherwise joint 2D (99% chi2_2=9.210). Joseph covariance, per-arm own-prior PWIDE `d0`, normalized PSD audit.
- Existing training artifacts and target data never changed by import or `--help`.

## Two immutable checkouts

1. **AUDIT**: `myoungsunk/sionna-resimulation` commit `034e57a7209a3bd1bb8857b24fd85c64942e1258`. The exact T2 release receipt and full motion recovery must be found at `research/POWERJOINT_AUDIT_RERUN_20261020/T2_NEW_ROUTE_BASELINE/prepare_inputs.py`.
2. **P2**: `myoungsunk/sionna-resimulation` commit `0686b23ceeefb696bc158b32b39f8077c564ef5d`. The original R2/R4/R5 P2 paths and `V.one(...TRACE.npz)` data must be available at runtime. The frozen P2 checkout is not assumed to contain the AUDIT loader.

The checkouts are separate because the frozen P2 and T2 versions do not live together at those commits. Do not substitute `main` for either. The full historical RF assets / bank and T2 source dependencies must be mounted as in their existing workflows; this ZIP intentionally does not redistribute gigabytes of original sources.

## Explicit CLI — each command is a separate user-controlled step

```bash
python -m pip install -r requirements.txt
python office_transfer_cli.py --help
pytest -q tests/test_core.py
```

When the user authorizes fetching RF files, **explicitly** execute:

```bash
python office_transfer_cli.py fetch \
  --cache /mnt/transfer/release_cache
```

Next, explicitly **prepare source records, without training**:

```bash
python office_transfer_cli.py prepare \
  --audit-checkout /work/sionna-audit-034e57a \
  --cache /mnt/transfer/release_cache \
  --extracted /mnt/transfer/source_archives \
  --out /mnt/transfer/prepared_office
```

Next, explicitly train **Office only**:

```bash
python office_transfer_cli.py fit \
  --audit-checkout /work/sionna-audit-034e57a \
  --source-table /mnt/transfer/prepared_office/OFFICE_SOURCE_LABELS.csv.gz \
  --out /mnt/transfer/models
```

Last, **only after source frozen and separate approval**, target replay example:

```bash
python office_transfer_cli.py replay \
  --target-checkout /work/sionna-p2-0686b23 \
  --models /mnt/transfer/models/OFFICE_TRAINED_MODELS.joblib \
  --case R2_aA_m45 --bias B0 \
  --out /mnt/transfer/evaluation
```

This command requires original frozen P2 trace artifacts accessible to `V.one`, not supplied by this ZIP; it does not download or generate those target assets.

## Interpretation guards

- Only source `LOS_EXISTS=true` examples get ground-truth labels; O03 `false` is preserved and not silently synthesized.
- Source labels depend on source GT and SourceFFD. Target GT is allowed in the preexisting sensor builder (to reproduce synthetic motion) and **offline scoring only**, not prediction, fit, gate, or parameter decisions.
- POWER+PWIDE retains POWER's packet-wise `Vs`, as in frozen Ladder3, to isolate correction-mean impact. A new source-calibrated `R_s` and R-only/update-only ablation would require a separate pre-registered extension.
- Gate uses **raw** `d0=z_s-h_s(x^- )` consistently for POWER and PWIDE. Office source GT residual quantile is not proven to be a correct online prior gate threshold. Treat gated results exploratory until source-only prior calibration is performed.
- `O_POWER` trained on Office, `C_POWER` originally held-corridor Power from P2; the two have different training inputs. Do not train on Corridor to improve Office-transfer candidate.
- This code *has not been integration tested with downloaded O01/O02/O03 assets or P2 frozen traces*. Unit tests use synthetic arrays and exercise the math/API gates. The published release and original official receipt were verified using GitHub metadata, not re-downloaded in this turn.
- Report case-level paired Heading RMSE and NEES and route-level scorecards, not packet-based independent significance.

## Frozen upstream sources

- Office T2 manifest: https://github.com/myoungsunk/sionna-resimulation/blob/034e57a7209a3bd1bb8857b24fd85c64942e1258/research/POWERJOINT_AUDIT_RERUN_20261020/T2_NEW_ROUTE_BASELINE/MANIFEST.json
- Office T2 loader: https://github.com/myoungsunk/sionna-resimulation/blob/034e57a7209a3bd1bb8857b24fd85c64942e1258/research/POWERJOINT_AUDIT_RERUN_20261020/T2_NEW_ROUTE_BASELINE/prepare_inputs.py
- Frozen P2: https://github.com/myoungsunk/sionna-resimulation/tree/0686b23ceeefb696bc158b32b39f8077c564ef5d/research/PJ_D0_CIR_P2_RECURSIVE_20261022
- POWER: https://github.com/myoungsunk/sionna-resimulation/blob/0686b23ceeefb696bc158b32b39f8077c564ef5d/research/R5_N4B_20261015/n4b_rf_errors.py
