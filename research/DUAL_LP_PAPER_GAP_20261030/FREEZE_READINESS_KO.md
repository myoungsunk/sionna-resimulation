# Freeze readiness / decision blockers — DLP-EKF-GAPS-001
Status: DOCUMENTATION_READY; SCIENCE_CONTRACT_NOT_FROZEN.

| Key | Value/status | What proposer/auditor must resolve |
|---|---|---|
| F01 governance read | DONE_DOCUMENTARY | Roles/docs read; scoped MBVAR rules reference only; decide if new root router needed, do not modify silently |
| F02 base git SHA | 6c7200091028fd3f0e55aa83b777d0f10b7cf063 | Check same immutable source for P0 |
| F03 draft sha256 | PENDING | Compute actual complete draft file SHA after final edit |
| F04 frozen source bank hashes | PARTIAL | FFD bank receipt SHA known; materialized input H/GT/observer hashes need exact P0 lock |
| F05 4state baseline | PARTIAL | Full J4/DR4 executed; same-setting scalar Range-only full-recursion evidence search needed |
| F06 >=3anchor data provenance | BLOCKED_EVIDENCE | WLS≥3/2D EKF code found; corresponding C0 third anchor + synchronized range not verified |
| F07 SourceFFD/range bridge | PARTIAL | choose source h and separate Range physical detector calibration before any comparative replay |
| F08 sample+seed paired identity | PENDING | Exact per-arm key parity, sensor_seed and initial_seed independence/metadata |
| F09 >2 anchor geometry | NOT_SELECTED | Specify only if P0 proves C0 has no compatible third anchor; horizontal nondegeneracy and scene feasibility |
| F10 resource fairness | PENDING | Baseline update/packet resource policy, shared time clock, missing packet and anchor covariance treatment |
| F11 statistical independence | EXISTING_LIMITATION | Current C0 scene n=1, route/seed not independent scene |
| F12 pre-run numeric tolerance | PENDING | Define each physical/model/numerical parity tolerance from source independent of observed performance |
| F13 RT canary and budget | NOT_APPLICABLE_UNTIL_G3 | No cost approved; only after gap found and user explicit authorization |
| F14 independent audit identity | NOT_ASSIGNED | Distinct actual audit computation and signed verdict mandatory for later run |
| F15 study 3-D/M2 | RESERVED | Different science decision, no inadvertent algorithm choice or synthetic time-field run |
| F16 source-model comparison | PENDING | List which old LUT results need recomputation with SourceFFD but preserve original historical reports |

## Proposer handoff decision
Proposer package is prepared; implementation readiness = BLOCKED_CONTRACT_INCOMPLETE; auditor readiness = not yet independently reviewed. No contract sign-off. No new data/results. Future amendment requires explicit authorization and a new file; preserve draft and prior evidence.

## Reading checklist
- AGENTS.md
- docs/research-governance/COMMON_CONTRACT.md
- ROLE_PROPOSER.md / ROLE_IMPLEMENTER.md / ROLE_AUDITOR.md
- MBVAR E4 DECISIONS, E5 revalidation, MBVAR PLAN + SCIENCE_SPEC + DRAFT contract
- EKF3 P0 manifest, EKF4 replay, FFD source receipt/report, localization.py

## User sign-off awaiting future turn
The user may later approve a specific phase. Until then no build/replay/simulation/audit.
