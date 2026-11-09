# Q-NONLINEAR-S-GYRO-20261110

Role: IMPLEMENTER and self-check; no independent audit. Offline feasibility analysis only.
Source repository: myoungsunk/sionna-resimulation, pinned e3ddc9fa4371d899a08a2a873d2ee5cf32074a01; original Actions 42600632209. Local folder is an analysis workspace, not a Git checkout.

Question: replacing the local linear S approximation by original nonlinear SourceFFD at the SAME frozen B OFF prior, does interval overlap better protect normal/useful observations and detect harmful S updates?

Frozen contract:
- All 3,136 rows evaluated; efficacy labels on 3,125 rows accepted by original gate. The original 11 gate-rejected rows are excluded from incremental-update labels, not the unrelated 11 P false alarms.
- Position fixed to OFF prior in both linear/nonlinear comparisons; mu and R remain frozen. No changed measurement, filter state, covariance, policy, or recursive execution.
- Gyro-supported interval G = prior_heading +/- 1.95996398454 sqrt(Pprior_heading_heading). This is the RF-conditioned EKF motion prior, NOT an independent gyro-only absolute-heading confidence set. Its calibration is not established by this diagnostic.
- Nonlinear S support = {psi: |h_s(prior_xy,psi) - (raw_B_s - mu_s)| <= width}. Width = 1.95996398454 sqrt(Rss) times frozen sweep scale; no_base/no_extra remove the respective original variance term. Compare S support intersect G to empty. All disconnected support sets retained conceptually; only intersection is required for all-row classification.
- Truth excluded from support construction. Harmful S label is (joint update Heading SE - range-only Heading SE)>1e-10 deg^2 at identical prior; useful label opposite. RF near-normal label is abs(Full S - LoS-only S at same B tap)<=0.03; threshold inherited from prior diagnostic, not a universal correctness criterion.
- 129 nodes within G; validated actual-model roots/local minima; 513 nodes for decision-sensitive rows. Numerical search is not a continuous global inverse proof. Width zero is an idealized sensitivity endpoint; roots within 1e-9 S residual treated as numerical zero.
- Circular 0.25-degree support visualizations for three previously discussed failure times use OFF priors, not previous ACTIVE priors; sampled endpoints have grid uncertainty and wrap-around pieces are retained separately.

Verification: SHA of original banks; all-row h/H parity to archived traces; exact time/row joins; linear result reproduction against old fixed-position table; refinement decision changes; finite values/counts; rendered figures. Record inputs/outputs, governance hashes and runtime exit status.

Allowed claims: observed sample comparison and feasibility limits. Not independent gyro corroboration, improved recursive RMSE, real-time safety, calibrated 95% coverage, new environment generalization, or adoption.
