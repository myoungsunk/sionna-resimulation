# FP-SC-001 E0 original controls recovery investigation

Status: **EXACT_HISTORICAL_CONTROLS_NOT_RECOVERED**. Control generation and archived-array diagnostics only. No selector, new RF, EKF replay, or scientific comparison was run during this investigation. The frozen E0 code and `RUN_E0_001` remain unchanged.

## Exact requirement and failure

`A0_R3_REFIT/BASE_INPUTS.json` requires the following SHA256 of contiguous float64 `ds` array bytes. The hashes are equal for B0 and L2 within each route because those arms share the wheel realization.

| Route | Required historical ds SHA256 | Linux regenerated ds SHA256 |
|---|---|---|
| R4 | `d366d1d3fcd447cba0a357d0b6cced801f04c687e323df553527852c43953b5a` | `3997268152be79329a4e7adcce82ea2edcf12dbfbaad10049ed748a75288ced3` |
| R5 | `e71729173c521fc5a90421b7b33e6195bd9a0038f8955f82392f43f2005dea73` | `d67b1945dbb20d7be32d4c0309b99478661bd1ad594d6d541133d7e934199e65` |

For all four route/bias pairs, `gy`, `dt`, and `x0` hashes match exactly. The first run correctly reports `BLOCKED_DATA` rather than executing with a mismatched `ds` stream.

## Original payload search

1. `C1/C1B_001/INPUT_LOCK.json` identifies R4/R5 controls only by an external Windows cache path under `D:\codex\MBVAR_PRR_001_20261103_inputs\S1_INPUTS\algorithm_input`. R2 controls additionally have an actual Git path. No equivalent R4/R5 Git path is registered.
2. The complete HEAD tree has 29,665 entries. A filename search found no R4/R5 seed10 control NPZ in an input/control directory. The tree contains 29 unsplit archive roots; the only MBVAR archive is `NEW_RT_DATA/SM0/delivery/SM0_R4B_194_STOP_RAW.zip`, a later raw RF capture. Older drive archives predate the S1 materialization and are not evidence of these exact payloads. No claim is made that every old split archive was downloaded or unpacked.
3. C2 `run.py` saves verification filter arrays and baseline scores, not the control arrays it reads from an external cache.
4. A read-only Git LFS batch download lookup used the four exact NPZ SHA256 OIDs in the C1B lock. The server returned HTTP 200 with **object-level 404 / Object does not exist on the server** for all four. This rules out retrieval of those exact NPZ objects from that public LFS object store at lookup time; it does not prove that no alternate archive or private cache exists.

| Payload | Registered SHA256 | Bytes | LFS result |
|---|---|---:|---|
| R4 B0 seed10 | `dcc5fd333ac5e42b75f8abc9d1c972f9f7920c2730917e6590093f3fcf6be75a` | 10,559 | object 404 |
| R4 L2 seed10 | `86152973ce138e464681c8549369e394f548ae19cb2b7b240255cc9929378cc8` | 10,553 | object 404 |
| R5 B0 seed10 | `c021d4212fa51f708a98a59e2f57ac18ab472098a0df49a8c9521ddc2e319a61` | 21,441 | object 404 |
| R5 L2 seed10 | `0cb4458ef33339a492ccf1d8ae599a0bf9b11245497bc3df7b20b005f678902c` | 21,461 | object 404 |

## Source and runtime diagnostics

The original producer `S1/materialize.py` calls `A0_R3_REFIT/check_base.py`'s pinned `exp_pb.build_controls`, compares every generated array hash to `BASE_INPUTS.json`, and then writes the controls NPZ. `check_base.py` imports sensor code from the frozen `results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src` tree.

- Git comparison of the frozen sensor_v2 file and current `src/qclean_uwb/drivesim/sensor_v2.py`: no differences.
- Git comparison of `exp_pb.py` at its original `7e2855314de867e0481f8eb5ed1a07c48710f364` source revision and current HEAD: no differences.
- Isolated NumPy 2.2.4 on the current Linux Python 3.12 runtime produces the same incorrect historical `ds` hashes as NumPy 2.3.5. Installing this diagnostic package did not modify the primary runtime.
- NumPy scalar trig, contiguous/strided vector trig, Python `math` trig, explicit 2×2 products, row dot products, and FMA/unfused multiplication variants did not recover an exact historical hash.
- Disabling AVX512 or the optional NumPy SIMD features did not recover a historical hash.
- OpenBLAS Haswell, Nehalem, and Sandybridge modes did not recover a historical hash. Some R5 variants differ by only 6.94e-18 m from the default generated stream, demonstrating that arithmetic dispatch can affect byte identity without establishing the source of the historical mismatch.

### Independent evidence from R2's actual archived payload

Regenerating R2 using the same published recipe and comparing with its actual archived seed10 B0 controls differs at only rows **55, 85, 205**, by 1, 2, and 1 ULP respectively; the maximum absolute difference is **1.3877787807814457e-17 m**. All three rows have the same absolute previous truth heading, **0.06654080926624306 rad**. Their wheel random values are ordinary non-tail normal draws. This rules out the initially considered rare normal-tail explanation for these R2 rows and makes platform math/trig rounding a plausible explanation. It is **not proof** of the precise Windows implementation or a bound on unknown R4/R5 control arrays.

As a second diagnostic, inverse projection of the archived R4/R5 W0 posterior-to-next-prior displacement, using the recorded state and the hash-matched gyro/timestamp arrays, differs from the current generated `ds` by at most **1.77e-15 m** across the eight archived cells. This includes inversion/subtraction/trigonometric rounding, cannot recover unique original floating point bytes, and is not a full recursive parity test. It must not be substituted for the required input hash.

## Two explicit possible next steps

### Preferred exact recovery

Obtain the four original payloads from the original Windows cache or rerun only the original control materializer on a matching Windows Python/NumPy/BLAS environment. Accept recovered arrays only when all four historical array hashes match, and register new payload/transport hashes separately. The first failed run remains preserved. A Windows-hosted control-only workflow could test this without launching RF or EKF science, if that execution surface is available.

### Separate materialization amendment if exact recovery remains unavailable

This is a proposed amendment, not an executed change:

1. Preserve `RUN_E0_001` with its original `BLOCKED_DATA` result and original hashes. Record exact-historical-control-byte recovery as unresolved.
2. Give the new stream an explicit identity such as `LINUX_REMATERIALIZED_ORIGINAL_RECIPE`, with all source/runtime/input hashes and no claim that it is the archived Windows payload.
3. Materialize and freeze the four new controls NPZ and each array's hash **before** any replay under the amended contract. Keep the gyro/dt/x0 exact equality checks and original numerical replay tolerances unchanged.
4. Revalidate the same-prior transition equations using recorded states as a diagnostic of rematerialization; do not relabel this a recursive replay.
5. In a distinct run ID, execute the original W0 recursion with the newly frozen controls. Report exact mask agreement and all original state/P/prior/h/H/K/S/etc. tolerances separately from historical input-byte identity.
6. Even if numerical replay passes, label the result `NUMERICAL_REPRODUCTION_WITH_REMATERIALIZED_CONTROLS`; do not mark the original exact-byte materialization requirement PASS. The result supports reproducibility at the declared tolerance and runtime, not literal recovery of absent original inputs.

The existing contract may need this distinction explicitly approved/frozen through its normal amendment path. No hash, numerical tolerance, metric target, or past verdict should be changed silently.

## Inspectable scratch evidence

- `controls_recovery_evidence.json`: source/input hashes, historical control references, diagnostic artifact hashes.
- `original_controls_lfs_lookup.json`: four object-level 404 responses.
- `diagnose_controls.py`: control-only diagnostic script.
- `controls_runtime_235.json`, `controls_runtime_224.json`: scalar/vector/product comparisons and archived-prior inversion diagnostic.
- `controls_noavx512.json`, `controls_nopy_simd.json`, `controls_blas_haswell.json`, `controls_blas_nehalem.json`, `controls_blas_sandybridge.json`: CPU/BLAS checks.
- `R2_control_generation_diagnostic.npz`: actual archived and regenerated R2 ds, with source pose/time arrays for inspection.
- `controls_search_tree.txt`: 29 archive-root names from the bounded HEAD tree search.

All paths above are under `/workspace/scratch/dd87dad66e0c/`; they are investigation artifacts, not frozen E0 results.
