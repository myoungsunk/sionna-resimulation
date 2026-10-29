# CLAIM_REGISTER — research claim constraints

**Draft ledger.** Facts refer to historic evidence, not new MBVAR-INFO-001 results. An independent auditor must sign any promotion.

| ID | Claim question | Current status | Permitted statement | Unsupported/forbidden statement | Existing reference | Required new evidence |
|---|---|---|---|---|---|---|
| CL-001 | Original RF polarization residual temporal ACF | OBSERVED_RETROSPECTIVE | Previous simulations found high ACF along moving pose sequence | ACF proves independent temporal sensor drift | `mbvar_premodel_diag_20261029/results/D3_EPS_TEMPORAL.csv` | P0 original H/z/µ repeat-pose identity |
| CL-002 | H_TC global mitigation | NOT_SUPPORTED_OLD_PROTOCOL | 40820579727 E4 `H_TC=REJECT` under prespecified joint criteria; R5-A improved but R5-B worsened | Temporal correlation physically absent; every correlated observation is harmful | `mbvar_control_correction_20261029/results/run_40820579727/DECISIONS.json` | S0/S1 and new R scenes |
| CL-003 | Time-only FOGM efficacy | NOT_SUPPORTED_IN_TESTED_MODEL | Tested LORO single-τ 5-state FOGM worsened average B0 Heading/XY vs MB_VAR | All FOGM models invalid or better than MB_VAR | workflow #40828341230 | S1 known-spatial-field vs time-only controlled comparison |
| CL-004 | Prior E5 information eigenvalues | NEEDS_CORRECTION | Earlier E5 had information scaling/dynamics limitations; corrected definitions must be checked | Prior E5's alleged 10–1000× tangent weakness proves current candidate geometry | `mbvar_e2_e5_revalidation_20261029/revalidate.py` | S0 analytic parity, full-process Q reference |
| CL-005 | Deterministic RF at old pose | SOURCE_REPORTED_PENDING_REPLICA | Older reflective-model protocol reports noise-free full first-path s matches filter input, so spatial sampling may explain time ACF | Every µ/ε is pose-only; new RT is white/noisy in time | `reflect_model/PROTOCOL_REFLECT.md` | P0 directly recompute raw H,z,h,µ,ε |
| CL-006 | S0 correlation×geometry information interaction | NOT_RUN | Proposed mathematical estimand; no numerical conclusion yet | Verified in new 4-state RF system | `SCIENCE_SPEC.md`, experiment contract | G2 tests, paired scenarios |
| CL-007 | S1 realistic synthetic pose/temporal noise | NOT_RUN | Proposed GP+OU+iid controls | Randomly permuted old RF exactly isolates real temporal colored noise | `SCIENCE_SPEC.md` | G3 repeat pose, PSD, kernel, paired trials |
| CL-008 | Sionna RT scene replication | NOT_RUN | New C00/C01/C10/C11 scene comparison proposed | Reflector location is a pure correlation-only intervention | scene contract | G4/G5 physical QA, scene-level aggregation |
| CL-009 | Generalizable method under unseen geometry | NOT_RUN | No independent confirmatory evaluation yet | Existing Corridor/Office is entirely unseen final test | split manifests | reserved new scene family/variant test, G6 auditor |

Ledger update must include timestamp, author, old/new status, evidence artifact IDs/sha256, independent audit ID. Never replace history in-place; append `CLAIM_CHANGES.md` events or version in commit.
