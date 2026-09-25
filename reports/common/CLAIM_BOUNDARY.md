
# Claim Boundary

## Frozen Claim Status

- Current Paper 2 role-matched status: `STARVATION_CONSTRAINED_LEVEL2_PARTIAL`.
- Strongest supported wording: CP q-clean / branch-aware operational gates reduce accepted unsafe UWB updates under starvation-constrained replay for key baselines.
- This is simulation/proxy replay evidence, not physical AMR trajectory evidence.

## Allowed Claims

- `q_clean` is a clean-session / session-quality confidence score.
- Paper 1 Simulation may claim CP feature usefulness for RD-LoS / HB-prior reflection-dominant channel-state identification when compared against frozen CIR baselines.
- Paper 2 Simulation may claim q-clean gating, weighting, rejection, scheduling, map, local scan, and control utility only within the validated replay/proxy regimes.

## Blocked Claims

- `q_clean` guarantees small range error.
- CP directly reduces range error.
- Full Level 2 localization reliability.
- Odometry-only improvement claims after failed gates.
- Physical AMR-operation validation without measured trajectory/action-log evidence.
- Cross-regime localization-accuracy generalization.
- Measurement supervised classification accuracy without labels.
- Real measurement reconstruction of RT path labels without explicit label evidence.

## Boundary Notes

- NoLoS is the main range / ToA error branch and is CIR-dominant.
- RD-LoS is not a range-error label.
- Use HB-near-delay wording unless LP-vs-CP detector evidence is added.
