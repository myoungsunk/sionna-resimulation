# PALO C/D — frozen mechanism experiment

This branch contains the exact source bundle `pinned_source.tar.bz2` (SHA-256 `1d36b10925c6289b356df284ec52b34f203de04a6c2462182629f961a8990423`), based on the prevalidated 2026-11-08 C/D execution package. The workflow extracts and verifies all seven files, then runs C0 frozen parity, C1–C4 factorial mechanisms, D1–D3 causal rollouts, stored-output verification and fail-closed publication.

Only PASS-verified outputs are committed to `research/PALO_MECHANISM_CD_EXEC_20261108/runs/<run_id>/`; the resulting run folder includes plain-text executed source files. Source dataset `4c43020`, oracle baseline `eaf9a386`, and mechanism design `657af33d` are frozen. No scientific result is claimed until its exact workflow run succeeds.

Source archive SHA-256 is checked before extraction. Do not treat synthetic tests as RF mechanism validation. Independent scientific audit and new-environment generalization are outside this execution.
