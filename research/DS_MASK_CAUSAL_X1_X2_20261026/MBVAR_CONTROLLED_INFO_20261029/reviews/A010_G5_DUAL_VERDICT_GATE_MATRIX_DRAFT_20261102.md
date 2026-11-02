# A010 prospective G5 gate matrix (DRAFT)

Gate definitions are prospective only; old G5 C3/C3V4 science FAIL cannot be relabeled.

| Gate | Numerically PASS iff | Failed/unknown behavior |
|---|---|---|
| RECEIPT_INTEGRITY | Source/contract SHA, ZIP and index manifest SHA, every dtype/shape/array byte SHA, optimizer input SHA and truth-only ledger all verified | FAIL |
| GENERATOR_LAW | Original generator full Sigma, time OU kernel, 180-pose factor law and frozen pose ledger all meet 1e-10 tolerance | FAIL; regenerated z bytes are diagnostic only |
| CROSS_FIELD_COV_EQUIVALENCE | All same (role, cell, arm) Sigma matrices SPD with delta_max and delta_F <=1e-10, exact field coverage | FAIL |
| SOLVER_REPRO | Distinct runners on one canonical input and immutable SHA, all state/cost/class/C10/mode comparisons pass | FAIL until independent two-runner artifact |
| STATE_COST_REPRO | Same E-prime numeric state/cost and baseline multistart key per registered tolerances | FAIL |
| FULL_C10_REPRO | Full 10 upper entries, SPD, NEES4, normalized condition log difference <=1e-3 | FAIL; not posterior calibration |
| STATUS_REPRO | class_v31 identical between source and replay | FAIL |
| NO_WRONG_BASIN / ITER_CAP / PROBE_POWER | Prospective pre-registered numeric gates | FAIL |
| LINEAR_EXACT / KINK_FIXTURES | Existing affine, piecewise controls pass | FAIL |
| rows | Full field/sensor/role/cell/arm coverage and exact key set | FAIL for reduced smoke by design |

**G5_NUMERIC_REPLAY** requires all explicit gates. No dynamic gate selection from suffix REPORTED.

**G5_MODE_IDENTIFIABILITY** is separate: keep full-row STATE_STABILITY_FIXED_LEGACY and its FAIL, count any truth-free near cost state alternative (|Δcost|<=1 chi-square, end dref>2); if alternatives exist result is MIXED and unique-map claim denied. Calculate within-non-ambiguous stability and field-paired effect sensitivity, preserving all valid rows for main H1/H2/H3/CAL/H4 science.

**SCIENCE_RELEASE** remains NO-GO unless independent scientific auditor confirms robust full results and boundaries. A hypothesis NOT_SUPPORTED can be a valid scientific result, not a technical failure.

**D6:** proposed full snapshot in contracts/AMENDMENT-010-D2D3D4D6-DRAFT.md is unapplied. No DEV3/HOLDOUT2/RT execution authorization.