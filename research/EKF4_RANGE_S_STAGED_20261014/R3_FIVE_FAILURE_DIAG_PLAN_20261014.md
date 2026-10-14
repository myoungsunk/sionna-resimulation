# Five-case R3 P2 independent fixed-input diagnosis: pre-execution plan

Source: https://github.com/myoungsunk/sionna-resimulation/actions/runs/38562146793
Immutable artifact 11892566974, SHA256 931ee7cd8552820f3b6311877bb6ccc4ecc910669231290efb82e5868756c9b4.
Original commit 2547f147ea347563a186a886bd25a543871825f3.

This branch adds only read-only forensic scripts and a GitHub-hosted audit-first
workflow. The original core.py, solver_r3.py, stable_descent.py, synthetic.py,
P2_SPEC.json, and all original outcomes remain untouched.

Evidence admission:
- Verify original ZIP SHA256 and CRC, source commit, run id, preflight exit 3,
  five invalid model cases, five unique identifiers, snapshot file hashes.
- Replay each original recorded FAILED_STEP.npz from range-first using exact
  80 iteration / 1e-8 frozen settings and verify final state/gradient/status.
- Trace original production cost acceptance and integrated descent on all
  halvings; do not replace the algorithm.
- Compute independent mpmath 80-digit objective/gradient and true Hessian,
  compare float GN, R3 exact fallback, mp exact Newton; evaluate all j=0..24.
- Report objective delta sign, rejected credible descent, existence/distance
  of a stationary point and floating-gradient floor separately.
- Interpret positive curvature and a nearby root as LOCAL evidence only; do
  not equate tiny cost/gradient with validated P2 bias effect or P3-P6 success.

STOP: Any source mismatch or nonreproducible status/gradient/terminal delta
must produce a nonzero diagnostic and preserve outputs. No auto replacement of
failed cases, no RF/DR prioritization change, no science claim.
