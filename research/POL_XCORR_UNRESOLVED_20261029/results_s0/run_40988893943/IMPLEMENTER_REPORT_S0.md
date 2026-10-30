# POL-XCORR-001 S0 implementer execution receipt

- Status: **S0_TECHNICAL_FAIL**; TECHNICAL_QA_ONLY / SELF_REVIEW_ONLY_FREEZE.
- Execution SHA: 3b145cd0894eae229c0d260a8a7df688b2776971
- Contract SHA256: c36c1c56d4db59d39ea85e1d87c1efe622325730a6b4fbc595fc95e583cde219
- Governance SHA: d5f84d9d04d28d465f3357e9299352eb184e6bfc
- Frozen inputs: synthetic H(257 bins) + hash-checked historical LoS FLOOR (7,251 TIMELINE); no Full H or labels.
- Mechanical checks: {"FROZEN_CONTRACT_SHA": "PASS", "FREQUENCY_AND_P0_LOS_LOCK": "PASS", "UNHANDLED": "FAIL"}
- Errors: [{"error": "", "traceback": "Traceback (most recent call last):\n  File \"/home/runner/work/sionna-resimulation/sionna-resimulation/research/POL_XCORR_UNRESOLVED_20261029/scripts/s0_synthetic_v1.py\", line 453, in run\n    fixtures=fixture_tests(freq,p0,params)\n             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n  File \"/home/runner/work/sionna-resimulation/sionna-resimulation/research/POL_XCORR_UNRESOLVED_20261029/scripts/s0_synthetic_v1.py\", line 365, in fixture_tests\n    assert err<=params[\"tolerances_fixed_before_run\"][\"gain_invariance_rel\"]\n           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\nAssertionError\n"}]
- All old raw H, P0/P0V3, proposer/auditor records, frozen contract/config left unchanged.
- No independent scientific verdict; R-10 missing; P1/P2 remain HOLD. S0 stops after reporting.
