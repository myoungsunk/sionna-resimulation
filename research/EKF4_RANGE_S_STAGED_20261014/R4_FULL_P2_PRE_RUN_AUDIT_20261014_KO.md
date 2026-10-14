# R4 full P2: execution-preceding code audit and immutable experiment contract

Source baseline: [a52bedcbbea2](https://github.com/myoungsunk/sionna-resimulation/commit/a52bedcbbea2b0619ac5e2f8efbe73bd5fd4c624).
Original failed five-case artifact: run 38562146793 / id 11892566974 / sha256 931ee7cd8552820f3b6311877bb6ccc4ecc910669231290efb82e5868756c9b4.
Original P2 science: frozen [P2_SPEC.json], sha256 548258a444c02a3a1d0c2d210b470489560b1bd56ad911cc9ee93d7631b36ce7; synthetic.py sha256 c3fc54d9726beab176971aa8652c0b6f61353f55f596613e4c8150351c4d9643.

## Pre-execution findings and repairs
1. Original R3 direct float64 objective cancellation and 64eps gradient-integral bypass invalidated five updates near 1e-8. Independent 80-digit run 38564525148 confirmed five have valid local descent. No claim that 1e-14 is a physically meaningful RF accuracy target.
2. Prior alternative solver commit a52bed (R3 stable residual-difference objective) already executed original full 600 paired conditions with zero invalid *in execution logs* (run 38561439520). This branch reuses EXACT numeric solver code from that run, so it is not a new scientific hypothesis or another tolerance adjustment. Its local-gradient consistency, correctness vs reference, and failure fixtures require fresh source-bound gate.
3. **Results-critical output defect:** prior full 600 trial workflow uploaded `p2_preflight/**` while full runner wrote into `p2_full/**`. Therefore most raw full-trial inputs, state traces, CI, and final receipts were NOT preserved in earlier artifact, despite successful workflow exit. The new workflow uploads entire `p2_full/**` and `r4_full_receipt/**`; reviewer validates all 600 INPUTS.npz, 2400 model traces, output SHA256, 6 paired groups and 18 contrasts before declaring archive eligible.
4. New five-case regression obtains original archive, verifies SHA256/CRC, each independent NPZ SHA, failure identity and step index. Each failure is re-solved in both original Range-first and saved-iterate modes; independent gradient, Gaussian objective, local covariance and negative-descent metadata are tested. No fake RMSE / prediction fallback.
5. New workflow order: static pre-run audit → P0/P1 → R1/R2 → four historical failures → five newly established failures → six representative P2 conditions → *fresh* full-stage pre-audit → original 600 pairs x four models → complete independent archival audit.
6. Main `core.py`, `stable_descent.py`, `P2_SPEC.json`, `synthetic.py`, scientific threshold 1e-8, iteration cap 80, Q/R and seed ranges remain exactly those used by run 38561439520. The only changed numeric-task code is NONE; modified files are audit + archival/fixture verification + workflow.
7. R4 FIVE PASS does not imply full success; stage receipts distinguish technical compliance, 95%-bootstrap pathwise MAP4-MAP3 evidence, actual RF validity, held-out independent scene. Full P2 full-pair group metrics must be inspected; `scientific_PASS=false` by default, until scientific decision separately reviewed.

## Known limits
No real-RF P3-P6 execution in this new workflow. The alternative stable residual step formula is a mathematically equivalent local objective representation, but not a formal floating-point error certificate; conditional failures remain possible. Previous full results are historical, not silently inherited as new-run data.
