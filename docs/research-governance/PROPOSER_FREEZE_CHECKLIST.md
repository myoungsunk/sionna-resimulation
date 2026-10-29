# MBVAR-INFO-001 — contract freeze checklist

Each row requires a source/commit link + recorded independent reviewer. A tick without evidence is invalid.

| Gate | Required proof | Current draft status |
|---|---|---|
| F-01 | Existing root AGENTS preserved, routing appended only, docs path present | PENDING |
| F-02 | Full governance SHA, base commit SHA, contract hash (not branch labels) | PENDING |
| F-03 | Source extractor/FFD bank/solver version materialized hashes and exact observation chain | PENDING |
| F-04 | Confirm `noise_var=None` on reference trace, raw H/z/h/µ/ε separately at duplicate poses | PENDING |
| F-05 | Baseline MB_VAR full state/P parity vs pinned source | PENDING |
| F-06 | S0 1-state/4-state Q-aware math independently verified, correct D^T I D | PENDING |
| F-07 | S1 GP covariance positive semidefinite and exact repeated pose field | PENDING |
| F-08 | FFD-only geometry candidate scores and matched LOW/HIGH pair locked | PENDING |
| F-09 | 12x12 scene/collision/LOS/correct anchor orientation, C00/C01 distinct | PENDING |
| F-10 | Plate material/thickness and tap/complex H parity tolerances set before canary | PENDING |
| F-11 | Seeds/fold allocation: CAL/DEV/HOLDOUT, independent scene units | PENDING |
| F-12 | Pilot effect-size/power plan and no per-realization oracle superiority claim | PENDING |
| F-13 | Separate RT budget receipt and explicit user approval for bulk RF | PENDING |
| F-14 | Independent pre-run auditor accepted math/splits, not self-review | PENDING |
| F-15 | CI negative fixtures fail closed and workflow actually exists | PENDING |

**P0_PREFLIGHT is permitted with DRAFT contract hash to resolve F-03–F-10.** Science contract freeze cannot be signed while required preflight F-01–F-12/F-14/F-15 remain PENDING. F-13 must be signed before RT canary or bulk costs (separate phase RF amendment permitted); log every amendment and do not confuse provisional material selection with a verified RT configuration.
