# P4 Full fixed R scaling diagnostic (exploratory)

After the frozen original-source forensic run 41442514650, compare AB and ABC 4-state range EKFs at four fixed observation variance multipliers: 1, 4, 16, 64. Include an additional gamma 16 replay using the frozen original gate acceptance mask. Use the exact prior, controls, RF packets and model from original P4 Full. Gamma 1 must match all original 12 source traces to within 1e-9 in state and covariance; otherwise stop.

This is retrospective within the single known C0 scene and seed, not a held-out noise estimate. Report all improvements and worsening, NIS accept/reject fractions, XY and heading RMSE, pose NEES and coverage. Never replace frozen original results or report optimality from these exploratory comparisons.
