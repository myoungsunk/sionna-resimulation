# MBVAR-PRR-001 A0 independent design audit

Decision: REDIRECT. Seven blocked items, three design checks passed. No science run.

1. BLOCKED — Actual MB means, BASE mask and Joseph update identified in ctl_core.py 65-83,134-163. Raw mu/R arrays and Rrs unverified.
2. BLOCKED — Reference blobs match. Execution SHA and complete immutable inputs absent.
3. BLOCKED — Development and sensor seeds distinguished. Prior use of seeds 10-29 unverified.
4. BLOCKED — Draft only. tau_ds and numerical and operational choices unresolved.
5. PASS — Factorial arms consistent. Historical reweighting defined for C_CP.
6. PASS — Same prior, damaged snapshot, causal replay and revised historical scores separated.
7. BLOCKED — F64 parity absent and normalized PSD tolerance undefined.
8. BLOCKED — Singular nuisance rank/pseudoinverse rule not frozen. Other failure policies described.
9. PASS — Technical, scientific and operational decisions separated. NULL cannot become PASS from exit status.
10. BLOCKED — A0 assigned. Stage code/result runners and independent reference implementations unregistered.

Before re-audit: lock raw inputs, verify mu/R and Rrs, document R2-B Tnone tau_ds and seed lineage, define epsilon, singular rank handling, PSD tolerance, test caps and timing measurement hardware. Freeze roles, environment and contract, then provide authorized F64 parity evidence.
Governance: local common a5cca7d8a8d5f20f4a89ea9b6509da0b8d7506626aac4a47fa1d27891ff5ebdb; auditor e1bdc2f231c71cdc27201c688e041b078576a6adf6c0290acc16ce4d8218291a. Repository INFO-specific policy scoped to another campaign.
