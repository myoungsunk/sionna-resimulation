# Controlled RF-heading chain hypotheses

Scope: POWER1 and Joint4 remain primary baselines. Mount comparison is restricted to valid R2 A M0/M45. R2 B and R4/R5 A/B M0 are route/anchor transfer tests. All datasets already belong to this repository. No new Sionna scene is claimed.

A: Recover source and score original baselines before interpreting new arms. Archive metadata differences are logged; only numerical/semantic changes invalidate paired conclusions.
B: Test remaining serial error after train-only mean and covariance correction; compare static conditional correction to temporal residual modeling.
C: Compare equal-marginal-variance memoryless and Gauss-Markov RF-bias states, s-only/r-only/both, maintaining state-bias cross covariance. No GT state reset is an operational method. GT is used only for training labels, offline matching and scoring.
D: Isolate mean, covariance, temporal memory, natural/fixed gating, iterated observation update and gyro-bias absorption. Keep fixed-Gate interventions explicitly offline.
E: Use physical relative-angle and distance conditions for localized interventions; preserve the exact pre-intervention prefix and evaluate subsequent errors. Distinguish retained RF-bias memory from marginalizing it away after the episode.
F: New corridor/office RF is not available in this run; no independent-scene generalization claim.

Scores: signed Heading error, RMSE, 95% angle coverage, interval width, NEES and negative log score, false confidence and bias absorption. Higher coverage alone is not success. Parameter fitting uses held-route train sequences only, with adjacent train/test spatial overlap disclosed. All exploratory models and failed arms are retained.

Reference source: 4b82e9801a1e065593fdd67a0f3ebd721ba29848. No frozen source is edited.
