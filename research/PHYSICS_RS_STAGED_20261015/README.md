# Audited physical-feature R_s experiment

Read RESULTS_KO.md for actual A/B/C results, the successful Heading improvement and failed covariance/mount45 outcomes. The experiment was run in the conversation execution container; GitHub Actions provided the unchanged hash-audited input bundle.

code/ contains the exact 11 inference/diagnostic/test Python files used. The attached physics_rs_source.zip additionally includes the report/packaging helper release.py. The complete physics_rs_full_results.zip contains failed tests, source snapshots, re-audits, heldout models/predictions and raw state/covariance arrays. ZIP hashes are in RESULTS_KO.md. The 250MB original H input is not duplicated in the results ZIP.

Download Actions artifact 11948391783 (run38681443033) and unzip into input/ alongside code/. Place original artifact11782748118 and11940333419 ZIPs in the parent of this experiment folder, named ekf3_frozen_rf_original.zip and r2_bias_results.zip. Source audit verifies exact input hashes; never bypass it or loosen thresholds to produce PASS.

Use Python3.13.5 and requirements.txt. Set OPENBLAS_NUM_THREADS=1 and OMP_NUM_THREADS=1. From code/:

```bash
python audit.py A
python stage_a.py
python audit.py B
python stage_b.py R2
python stage_b.py R4
python stage_b.py R5
python stage_b.py
python audit.py C
python stage_c.py one
python stage_c.py recursive --part 0
python stage_c.py recursive --part 1
python stage_c.py recursive --part 2
python stage_c.py recursive --part 3
python audit.py POST
python post_validate.py
python audit.py DIAG
python diagnose_gate.py
```

First create audit/ and results/ in the experiment root when extracting only Git source. Repeated runs overwrite their designated stage outputs, so use a fresh experiment directory to preserve original evidence. Models are trusted outputs from this execution; do not unpickle arbitrary files. A model-cache read checks feature/source/split/hyperparameter identity. The audit is a same-assistant review with independent formula and negative controls, not third-party certification. Original H/LUT/Q/Rr/core remained unchanged. No claim of physical hardware validation or independent-scene generalization is made.
