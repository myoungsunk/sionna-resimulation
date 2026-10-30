# RA5 ONLINE P0 — implementation receipt and execution-blocker status

Date 2026-10-30 (KST). **This is an implemented engineering package, NOT a passed experiment.**

## 1. Roles / governance actually read
- Root AGENTS.md, docs/research-governance/COMMON_CONTRACT.md, ROLE_PROPOSER.md, ROLE_IMPLEMENTER.md, ROLE_AUDITOR.md, CI_REQUIREMENTS.md, PROPOSER_FREEZE_CHECKLIST.md.
- Original frozen MBVAR-INFO-001 experiment contract and SCIENCE_SPEC inspected, and source RA4 replay + SourceFFD full spectrum/prediction code.
- Separate **RA5-ONLINE-P0-20261030 DRAFT engineering contract**; baseline SHA bfff111357ffd54baa2627dfda01df99548a6cd9; governance SHA 250d617ad89a4105fa1af546cc83ceed9de98f42.
- Science FROZEN and independent AUDITOR approval: NOT PROVIDED. No old MBVAR-INFO contract/holdout/scene amended, no physical RT.

## 2. Files added or changed

- RA5_ONLINE_P0_DRAFT_CONTRACT.md: P0-specific estimands, same-observation comparisons, chi-square DOF, source/metric QA and stop conditions.
- online_observer.py: the exact native 30%-strongest-port observer, fractional tap-crossing from SourceFFD at prior x, continuous FD H_r, analytic fixed-tap J_s0,J_ds1, fitted prior-based range model and derivative, observed edge-quality grouping, train-only categorical delta-tap, full 2×2 / 3×3 covariance with exact structural duplicate check **before shrinkage**.
- run_prior_joint_canary.py: seven original H/SAMPLES teacher loading with SHA; 2 other-route train folds, held R4-B and R5-A B0; full BB_ORIG state/P/mask parity vs exp_pb; 2D/3D paired BASE_FIXED and SELF_NIS; Joseph P, proper NIS rank thresholds; detailed first-flip log rho, K, R, innovation, x/P; performance after source score window. New filter receives no scoring GT input.
- p0_mechanical_fixtures.py: source fractional/J parity, deliberate singular triple observation, basis information invariance, prior-only function and categorical normalization.
- tap_switch_conditional_mc.py: physically distinct source-conditioned **noise-induced detector flip** (noisy Full tap vs clean Full tap) vs Full−LoS systematic delta; fit/train first pose, report Brier/logloss on held second pose, no teacher clean tap at inference.
- .github/workflows/ra5-online-p0-unit.yml; ra5-online-p0-recursive-canaries.yml; ra5-online-p0-tap-noise-switch.yml. All are NO-RT, artifacts even on failure; original SHA and role inputs locked.

Files moved/deleted: NONE. Protected old H, traces, original BB/MB_VAR, MBVAR-INFO, POL-XCORR, RT contracts, saved scores: UNCHANGED.

## 3. Execution request vs verified outcome (do not conflate)

At report creation, GitHub Actions jobs are **QUEUED, not started**; no source/P/R/K parity verdict has been returned.

| Phase | Workflow | Job status when last checked | If successful |
|---|---|---|---|
| P0 maths/source observer negative fixtures | [40994216940](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40994216940) | QUEUED | QA.json, FFD/J/source and deliberate rank failure |
| Original BB parity and R4-B/R5-A new recursive 2/3D | [40994444606](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40994444606) | QUEUED | trace, first divergence, train models, source manifest, performance |
| Noisy tap-switch categorical conditional distribution | [40993838476](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40993838476) | QUEUED | held-pose switch distribution, Brier/NLL, failure strata |

The GitHub Actions repository has an unrelated 23-job MBVAR-INFO S1V3 workflow [40992589158](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40992589158) with many shards IN_PROGRESS concurrently; other jobs are queued. Do not cancel or preempt its running source without authorization. A queued run must not be labelled PASS, FAIL or completed execution.

Unit workflow now uses a concurrency group to cancel newer-revision superseded checks; queued older attempts remain visible. Latest canary is SHA-locked to its queued triggering commit and includes full first-flip K/R receipt.

## 4. Source and methodological limits

- Original data are static single Corridor scene, multiple correlated routes and anchors; training on two other routes is retrospective development, not independent new RF scene.
- R_eff learned from deterministic Full−LoS RF modelling residuals is not physical calibrated receiver noise. The categorical Full−LoS mismatch model is not the same as the simulated receiver-noise flip model.
- First-edge and measured adjacent tap share nonlinear detector decisions and port timing; target sensor may not provide two coherent raw ports.
- Regularisation of an exact duplicate is explicitly rejected, and conditional 3D R is required full-rank. No forced Gaussian inverse when r/s/tap degeneracy is known.
- No deployed sensor, independent physical noise, moving-scene process, 5-state information claim or new physical RT generalisation supported.
- If model source J crosses tap/port boundary, the new filter stops that packet and reports exclusions; missing rows must remain in the denominator.

## 5. Next exact gate

Check action runs above. Once source unit, original BB full state/P/mask canaries and categorical holdout each return actual logs, verify detailed output hashes, initial and first-flip x/P, joint R, Jacobian/switching strata, 30s scoring and valid-denominator counts. At the first failure preserve it and repair on a new commit/run, never overwrite an earlier result. Only after all actual technical QA is PASS should a separate independent auditor undertake science-level examination; P0 DRAFT never authorizes new RT or blind TEST.

STATUS: CODE_AND_WORKFLOWS_COMMITTED / CI_EXECUTION_QUEUED / SCIENCE_RELEASE_BLOCKED.
