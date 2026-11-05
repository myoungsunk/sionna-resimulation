# VAB Evidence bridge R1

[결과 및 제한](RESULTS_KO.md) · [실행 계약](CONTRACT_KO.md) · [자체 검산](CHECK_001/CHECK.json)

Connection implementation and nonrecursive diagnostics complete. Selection adoption HOLD. E2 not started.

`OriginalAdapter(repo, revision_evidence=RevisionEvidenceAdapter('VAB', 'TWO_PORT_UNION'))` provides the explicit evidence delegation interface. Loading OriginalAdapter still requires its original outer authorization and pinned model inputs. Do not instantiate it merely to inspect archived logs. The returned revision Evidence deliberately refuses select/history execution until a separate safety contract is implemented and validated.

Archived diagnostics are reproducible using `scripts/diagnose_fp_sc_bridge.py` with `--source` pointing to the E1 R1 RUN_001, a new `--output` directory and this CONTRACT_KO.md as `--contract`. Restore the original E1 R1 trace parts with its existing restore helper if necessary. This command reads archived candidates and never generates RF or runs E2.

The input recipe, exact implementation commit, source/config/pool hashes and run environment are recorded in RUN_001/EXECUTION_LOCK.json and INPUT_HASHES.json. Existing runs refuse overwrite.
