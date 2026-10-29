# Role-specific task handoff examples (copy after installing governance)

These examples are **not actions already completed**. Replace exact SHA placeholders ONLY after governance freeze. If a field is missing, actor should return BLOCKED rather than guessing.

## Task 1: proposer

```
ROLE=PROPOSER
REPOSITORY=myoungsunk/sionna-resimulation
BASE_GIT_SHA=<FULL_40_HEX_SHA_FROM_DESIGN_BRANCH>
GOVERNANCE_GIT_SHA=<FULL_40_HEX_FROZEN_COMMIT>
CONTRACT_ID=MBVAR-INFO-001
TASK=Review SCIENCE_SPEC.md and PLAN_P0_P6.md, then freeze the experiment contract after resolving every P0_TO_RESOLVE field.
MANDATORY_READ=AGENTS.md;docs/research-governance/COMMON_CONTRACT.md;docs/research-governance/ROLE_PROPOSER.md;research/DS_MASK_CAUSAL_X1_X2_20261026/MBVAR_CONTROLLED_INFO_20261029/contracts/EXPERIMENT_CONTRACT_MBVAR-INFO-001.md
OUTPUT=Frozen SHA256 experiment contract + split manifests + math design + auditor pre-run signoff; NO RF/estimation results.
STOP_ON=Missing governance or input SHA, unresolved model definitions, invalid independence assumptions, missing scientific negative controls.
```

## Task 2: implementer — P0 only

```
ROLE=IMPLEMENTER
REPOSITORY=myoungsunk/sionna-resimulation
BASE_GIT_SHA=<FULL_40_HEX_SHA>
GOVERNANCE_GIT_SHA=<FULL_40_HEX_FROZEN_COMMIT>
CONTRACT_ID=MBVAR-INFO-001
DRAFT_CONTRACT_SHA256=<DRAFT_64_HEX_SHA>
PHASE=P0_PREFLIGHT
TASK=Materialize pinned existing sources under DRAFT contract; perform only P0 source/math/geometry audit, baseline X/P parity, repeated-pose H/z/h/mu/epsilon identity, scene/robot collision checks, correct information normalization and analytic gate checks. DO NOT run experimental performance comparison, bulk RT or claim causal result.
MANDATORY_READ=AGENTS.md;COMMON_CONTRACT.md;ROLE_IMPLEMENTER.md;frozen experiment contract;SCIENCE_SPEC.md
OUTPUT=P0_PREMISE.json;P0_POSE_LEDGER.csv;P0_PARITY.json;P0_SOURCES.json;P0_GEOMETRY.csv;MANIFEST.json;error logs.
STOP_ON=Any failed input hash/parity/math/pose or unresolved parameter; preserve failed artifacts.
```

## Task 3: independent auditor — design and execution

```
ROLE=AUDITOR
REPOSITORY=myoungsunk/sionna-resimulation
BASE_GIT_SHA=<FULL_40_HEX_SHA>
GOVERNANCE_GIT_SHA=<FULL_40_HEX_FROZEN_COMMIT>
CONTRACT_ID=MBVAR-INFO-001
CONTRACT_SHA256=<FROZEN_64_HEX_SHA>
TARGET_RUN_ID=<EXACT_RUN_ID_OR_P0_PENDING>
TASK=Independently recompute analytic information controls, inspect process-Q batch info and GP repeat-pose identity; check unmodified source/scene hashes and split leakage. Review whether evidence justifies proposed statements. Never rely on implementer screenshots alone.
MANDATORY_READ=AGENTS.md;COMMON_CONTRACT.md;ROLE_AUDITOR.md;frozen contract;raw results
OUTPUT=Full audit-report.md with independent calculation, source IDs, PASS/FAIL and verdict.
STOP_ON=Missing independent source access, math discrepancy, train/test leakage, unjustified causal claim; no scientific ACCEPT merely due to green CI.
```

## Task transition rule

`P0_PREFLIGHT (DRAFT) → proposer/auditor freeze of contract → S0 → S1 → R canary (signed RF amendment) → R paired pilot → R reserved confirm → release`. Each science gate requires a recorded `PASS` plus pre-run reviewer signoff for the next phase; expensive RT also requires numerical user-approved compute budget. A stage's result cannot modify its own preregistration without downgrade to exploratory.
