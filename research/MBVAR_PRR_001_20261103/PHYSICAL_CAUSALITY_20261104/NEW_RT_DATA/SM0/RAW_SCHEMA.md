# SM0 native raw schema and execution gate

No scientific solve has occurred while preparing these files. `producer.py` imports the pinned original scene and FFD adapter from the external source directory. Inputs are read-only. One invocation captures exactly one authorized original pose. Existing output folders are refused. A failed canary cannot authorize another pose.

`--lock-only INPUT_LOCK.json --source SOURCE --bank BANK` hashes all 24 original source/input files, both FFD banks, the producer/math/diagnostics/postprocess modules, and RUNTIME_LOCK.json without importing or running a simulator. The GO JSON must have `schema: SM0_GO_V1`, `decision: GO`, `authorized: [{case: R4_aB_m0, pose_id: 194}]`, and exact copies of `code_sha256`, `source_sha256`, `bank_sha256`, `thresholds`, `primary_reference`, and `runtime_lock_sha256` from this lock. Before any simulator import the producer verifies actual exact Python version/executable, CPU/OS, all isolated distributions, LLVM file/hash and environment against the frozen runtime manifest; the native variant and actual DrJit thread count are checked before the solver is constructed. Receipt includes runtime lock SHA and the validated actual state. The authorized first canary is original R4 pose194 only. Other poses require a later explicit GO.

## Files

- `MANIFEST.json`: case, original pose ID/time/coordinates/yaw/phase, source/code/bank hashes, solver configuration, scene PLY bindings, actual object-ID map, environment, dtype/shape schema, numerical QA and PASS/STOP status.
- `bins/000.npz` through `256.npz`: untouched native path metadata and coefficients for each independent frequency solve. Source path indices restart at zero per bin. These retained files expose partial captures if a later error interrupts the pose.
- `RAW.npz`: the complete ragged arrays plus identifiable group spectra and archived references below.
- `ARTIFACT_HASHES.json`: hashes every retained file after success or failure. Scientific PASS requires the native reconstruction and both archive gates, independently of successful file creation.

## RAW.npz arrays

`offsets[258]` splits N total source paths by frequency. `frequencies_hz[257]` is the exact bank/archive grid. All spectra use frequency then RX(+45,-45); selected TX is +45, index0.

- `a[N,2,2]`: native complex passband coefficients, original native dtype, RX then TX axes. Both TX columns are retained.
- `tau[N]`: native absolute path delay in seconds, original dtype.
- `source_index[N]`: original path index within the originating frequency bin.
- `objects[N,depth]`, `interactions[N,depth]`, `primitives[N,depth]`: untouched source object, interaction-type and mesh primitive IDs. Sentinel IDs remain intact.
- `vertices[N,depth,3]`: native interaction coordinates, metres; unused entries remain as returned by native solver.
- `theta_t`, `phi_t`, `theta_r`, `phi_r`: native zenith/azimuth departure/arrival angles, radians. First axis is N; remaining width is the original native receiver/transmitter geometry dimension, retained rather than inferred.
- `valid[N,width]`: all native validity flags, including invalid/padded paths. Nonzero invalid coefficients stop the producer.
- `fields[N,2]`: vectorized complex128 propagation of each raw source path at that bin, using the selected TX.
- `original_field[N,2]`: exact original `compute.py` expression/precision path, preserved separately.
- `native_original32[257,2]`: original per-bin path reduction. Actual dtype is recorded; this is informational and does not select the reconstruction reference.
- `native_cfr32[257,2]`: native `Paths.cfr(frequencies=[0], normalize_delays=False, normalize=False)` from the same Paths object, kept independently and informationally.
- `native_f64[257,2]`: primary reconstruction reference, computed independently from ungrouped original a/tau using scalar Python `math.cos`, `math.sin`, and separate `math.fsum` real/imag sums in float64. It never reads grouped arrays.
- `group_fields[G,257,2]`, `group_count[G,257]`, `group_missing[G,257]`: vectorized complex128 per-ray fields accumulated by identifiable semantic chain. Missing group fields are zero with explicit missing flags. Counts retain within-bin multiplicity.
- `group_labels[G]`: `DIRECT`, `INVALID`, or the canonical JSON string of the ordered semantic object-name / integer interaction-type sequence. Example: `[["floor",1],["wall_y_neg",1]]`, with no spaces. Object names come directly from the scene object-ID lookup. Unknown active IDs stop capture. `INVALID` retains zero padded paths rather than treating them as a physical reflection.
- `group_ids[G]`: SHA256 of each exact group-label UTF8 string. `source_group[N]` maps every source ray to a group.
- `direct_group`: scalar DIRECT group index. `direct_source_index[257]`: confirmed per-bin direct path index. Exactly one valid empty-interaction chain must match the geometric direct delay within1e-12s.
- `direct_f64`, `archive_full`, `archive_los`: selected-TX reference spectra, shape[257,2]. Archive bytes and channel axes are fixed; no shift/scale alignment occurs.

Cross-frequency identity is **semantic group identity**, not an invented one-to-one matching of native ray indices. Several geometric paths sharing one ordered surface/type chain remain separate in ragged raw data, with explicit group multiplicity. No source path is silently removed. Native frequency-dependent geometry, angles and source IDs are retained for independent finer matching.

## Frozen reconstruction QA

Compare `sum(group_fields,axis=0)` with independent `native_f64`: both relative L2 and maximum absolute residual divided by the maximum absolute reference amplitude must be <=1e-8. Compare `native_f64` with archived Full: relative L2<=1e-3. Compare `direct_f64` with archived LoS: relative L2<=1e-5. All comparisons also report maximum absolute differences. Original32 and CFR32 differences are reported separately, never used to relax or select the primary reference after results.

Mother's postprocessing interface is `producer.load_diagnostics(RAW_path)`, returning exactly `freq, fields, labels, direct, native_full, archive_full, archive_los` for `diagnostics.evaluate(folder, **kwargs)`. No FFT, detector, Shapley or causal attribution computation is performed inside the native solver loop.

## Runtime

Isolated Linux site-packages: `/home/myoung-sun/.local/share/sm0_native_20261104/site-packages`. Interpreter: `/home/myoung-sun/.local/share/prr31117/bin/python3`, requiring `PYTHONHOME=/home/myoung-sun/.local/share/prr31117`, `LD_LIBRARY_PATH=/home/myoung-sun/.local/share/prr31117/lib`, the isolated site-packages in `PYTHONPATH`, and `DRJIT_LIBLLVM_PATH=/lib/x86_64-linux-gnu/libLLVM.so.20.1`. Set OPENBLAS_NUM_THREADS, OMP_NUM_THREADS and MKL_NUM_THREADS to1. Producer sets DrJit threads to1. Exact numpy1.26.4/scipy1.14.1/sionna-rt2.0.1/mitsuba3.8.0/drjit1.3.1 and `llvm_ad_mono_polarized` are enforced.

`paths_2_0_1_reference.txt` is read-only upstream API evidence downloaded from https://raw.githubusercontent.com/NVlabs/sionna-rt/v2.0.1/src/sionna/rt/path_solvers/paths.py; it is not an execution module. Original SPDX/license text is retained.
