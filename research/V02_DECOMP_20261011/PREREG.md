# V02 decomposition — pre-registration (written BEFORE any run). Exploratory Stage-A diagnostic, scratchpad only.
Date 2026-10-11. Source: origin/codex/abc-gated-resume-20261011 @9a6bc0cd (src + P0_FINISH V02_stress_repair_check.py unchanged).
Seeds: 1000..1255 (256), disjoint from all previously used (0-127, 256-383, 512-527, 640-767).
Fixed: trajectory, DT=.2, N=240, checkpoints 0/12/24/48 s, range sigma .08 at every step (no gate), original Q/R laws, original priors, original EKF.
No post-hoc Q/R changes, no removal of failing arms.

Question: does the ORIGINAL EKF fail LARGE_IDEAL_RANGE because of (a) EKF approximation error, or (b) generator-vs-filter model mismatch?
Arms (prior in {SMALL, LARGE=Config().p0_std}):
  GEN_EKF        : existing V.generate world (as in V02), original EKF.
  CONS_EKF       : model-consistent world (truth via filter transition(); measured inputs = true inputs + noise from the filter's own Q law; odometry o = odometry_model(x_true)+noise), original EKF.
  CONS_EKF_OFF   : same world, range disabled.
  CONS_CUBA      : same world, JointCubatureFilter (GH9 range) candidate.
Reading rule (declared now):
  CONS_EKF mean NEES inside chi2 95% bounds (n=256)  => EKF math is consistent; failure in GEN_EKF is a generator/model mismatch.
  CONS_EKF above upper bound => EKF approximation error (nonlinearity) is at least part of the failure.
Secondary: LARGE prior position std scaled x{.25,.5,1,2} in CONS_EKF, to show how NEES scales with prior size (approximation error should vanish as prior -> 0).
