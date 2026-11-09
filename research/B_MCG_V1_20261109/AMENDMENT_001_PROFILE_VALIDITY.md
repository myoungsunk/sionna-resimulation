# B-MCG v1 — finite profile validity amendment

This is a numerical/validity correction made **before the final policy lock**.
The score thresholds, good-update-loss budget, main Q, detector, source observer,
legacy shadow, initial state and historical observation calibration are unchanged.

## Demonstrated defect

In the first finite profile implementation, three affine charts and individual
SVD probes missed a feasible joint nuisance direction. A SourceFFD diagnostic
at R5 k707 returned s-score 3.46066 and damped a beneficial ideal-current update.
An evaluator-only constrained search found a candidate within the same history
cost slack and bounds with s-score about 2.757. Thus absence of a candidate in
the sampled set was not evidence of absence in the admissible set.

## Correction

- Refine the best initial chart using up to three bounded, exact-model
  Gauss-Newton steps with exact-cost backtracking.
- Require normalized projected gradient per history sample <= 0.05.
- Add positive/negative target-prediction directions for each observation
  channel using the historical curvature. The current observation is not used
  to construct these directions.
- Require at least three retained finite candidates. Detect a newly proposed
  candidate with lower cost than the supposedly converged centre and abstain.
- Keep best-fit bound saturation and nonlinear-check failures as UNKNOWN.
- Keep a physical-boundary-support flag, but use the **existing 2-sigma target
  spread cap per channel** to decide whether uncertainty in that nuisance
  matters. A blanket veto on any boundary support was independently rejected
  because it contradicted blueprint section 6.4. That interim version and its
  all-UNKNOWN diagnostics are retained as superseded evidence.

The minimum finite candidate count and gradient tolerance are numerical
validity controls, not confidence probabilities or proof of global coverage.
The nonlinear finite search still cannot certify all feasible nuisance modes.
This limitation remains an adoption risk even after the particular R5 k707
regression no longer damps at tau=3. A later final-source recovery diagnostic at
R4 k212 found another bounded, history-cost-feasible tau=3-compatible witness
that the runtime candidates missed. The numerical repair therefore does not
pass a claim of sufficient feasible-set coverage; see SOURCE_STRESS_AUDIT.md
section 8. Failure to find a tau=2 witness is not a global infeasibility proof.

## Evidence handling

The original finite-profile outputs and the interim blanket-boundary outputs
are not inputs to the final policy calibration. Final profiles are recomputed
in a separate output directory with code hashes recorded before execution and
checked again before completion. The same SourceFFD counterexamples, unit
tests and recovery episodes are rerun with the final implementation.

No threshold was increased to make the counterexample disappear. The prior
wrong-reference and steady coherent-distortion hypotheses remain separately
testable; correcting search does not identify a coherent absolute RF bias.
