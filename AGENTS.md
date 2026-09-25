# AGENTS.md

## Project Identity

This repository organizes the CP-aware UWB q-clean research project.

Treat this workspace as a research deliverable, reproducibility, and report-packaging repository. Do not treat cleanup as a generic code refactor. Scientific evidence, raw/support files, result packages, reports, manifests, and claim boundaries are first-class artifacts.

This file adds project-specific rules for `D:\codex\raytracing_modules\rt_cp_uwb`. Higher-level `D:\codex\AGENTS.md` guidance remains in force unless a rule here is more specific for this repository.

## Research Structure

The project has two papers and four experimental axes:

1. Paper 1 Simulation:
   CP feature identifies reflection-dominant channel states missed by CIR-only features.

2. Paper 2 Simulation:
   Frozen OOF q-clean score is used for UWB-derived prior gating, weighting, rejection, scheduling, scan/control, and operational reliability checks.

3. Paper 1 Measurement:
   Controlled real measurements confirm that CP score moves in the same direction as simulation under controlled physical conditions.

4. Paper 2 Measurement:
   q-clean measurement work can validate operational consistency and AMR/backend utility only when measured data and proxy/trajectory evidence are present.

## Claim Boundaries

Never change these scientific boundaries without explicit user approval:

- `q_clean` is a clean-session / session-quality confidence score.
- `q_clean` is not a guarantee of small range error.
- Paper 1 must not claim that CP directly reduces range error.
- Paper 1 claims CP helps identify RD-LoS / HB-prior reflection-dominant channel states.
- Paper 2 claims q-clean can gate, weight, reject, schedule, map, or trigger local scan for UWB-derived priors.
- NoLoS is the main range / ToA error branch and is CIR-dominant.
- RD-LoS is not a range-error label; it is a reflection-dominant session-quality state.
- HB-prior is the concentrated CP-sensitive prior/session-quality branch.
- HB-ToA must be written as HB-near-delay or near-delay high-bounce candidate unless LP-vs-CP detector evidence is added.
- 2H is the main structure.
- 3H is a mechanism refinement, not the main breakthrough.
- Unlabeled measurement data must not be described as supervised classification accuracy.
- Real measurement must not be described as reconstructing RT path labels unless explicit label evidence exists.
- Current Paper 2 role-matched package wording must not be promoted beyond `STARVATION_CONSTRAINED_LEVEL2_PARTIAL` without new evidence.

## Data Invariants

Never overwrite files under these protected locations when they exist:

- `data/raw/`
- `results/frozen/`
- `reports/release/`
- `_archive/pre_cleanup_snapshot/`

Also protect current raw/support and package evidence until manifests prove otherwise:

- root `CP_SCENARIO_*.csv`
- root `S Parameter Table*.csv`
- root `*.ffd`
- root `*.aedt`
- `archive/`
- `_Standardized_Backup/`
- `review_packages/`
- `deliverables/`
- `results/PAPER2_OPERATIONAL_RELIABILITY_DATA_REPORTS_20260603/`
- `results/PAPER2_ROLE_MATCHED_QCLEAN_VALIDATION_PACKAGE_20260604/`

Before moving, renaming, or deleting anything, produce a dry-run plan first. Only apply cleanup after the user explicitly asks to apply the plan.

Never delete research files directly. Move uncertain files only through a reviewed archive plan into:

- `_archive/deprecated/`
- `_archive/duplicates/`
- `_archive/pre_cleanup_snapshot/`

## Required Canonical Artifacts

The final repository must preserve or generate:

- raw path list
- LP CIR
- CP co/cross channel
- feature table
- label table
- split manifest
- OOF score table
- calibration table/model
- q-clean decile table
- gating policy table
- figure manifest
- report manifest

If an artifact is unavailable, mark it as `MISSING` with a required action. Do not fabricate data.

## Label Conventions

PATH-2H labels:

- NoLoS
- RD-LoS

PATH-3H labels:

- NoLoS
- HB-near-delay
- HB-prior

q-clean definitions:

```text
2H:
q_clean = (1 - p_NoLoS) * (1 - p_RD)

3H:
q_clean = (1 - p_NoLoS) * (1 - p_HB_near) * (1 - p_HB_prior)
```

## Feature Conventions

Core feature groups:

- CIR5
- CIR12
- LP-CIR12
- CP6
- CP11_mech
- CP15 upper-bound
- DW1000-like proxy
- detector proxy
- backend residual / innovation

## Coding Standards

- Prefer pure, testable Python functions.
- Keep the current `rt_cp_uwb_py/` package stable until a dedicated compatibility migration plan exists.
- Do not move MATLAB `+*` package folders without a dedicated MATLAB import-compatibility plan.
- Put new reusable Python logic under the existing package or a planned `src/qclean_uwb/` migration layer.
- Put command-line entry scripts under `scripts/`.
- Do not leave analysis-only code as the only implementation.
- Convert stable notebook logic into scripts or modules before relying on it for release claims.
- Every generated table and figure must have a provenance record.
- Every experiment run must write a manifest with config hash or config snapshot, input files, output files, timestamp, and command line.
- This root is currently not a git repository; do not claim git provenance unless a git repository is initialized later.

## Verification

After code changes, run the most relevant checks:

```powershell
python scripts\00_inventory.py --check
python scripts\01_build_manifest.py --check
python scripts\02_validate_dataset.py
pytest -q
```

For report changes, also run:

```powershell
python scripts\06_build_reports.py --check-links
```

For release packaging, also run:

```powershell
python scripts\07_package_release.py --dry-run
python scripts\07_package_release.py --check
```

If MATLAB package surfaces are changed, run the relevant MATLAB sanity checks or explain why MATLAB verification was not run.

## Done Definition

A task is complete only when Codex reports:

1. Files changed
2. Files moved
3. Files intentionally left untouched
4. Tests/checks run
5. Generated artifacts
6. Remaining risks
7. Next recommended command

For staged cleanup/reorganization work, stop before the next stage and give a short status brief. Wait for explicit user approval before moving to the next stage.
