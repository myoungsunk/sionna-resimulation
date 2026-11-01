# P1 candidate configuration interpretation errata (additive; no source mutation)

A descriptive string in `P1_CONFIG_LOCK.json` calls the Hann window "periodic-endpoint", while the **binding formula** given there and in the signed proposer contract is the symmetric **N-1 denominator** window

`w_k = 0.5 - 0.5*cos(2*pi*k/(N-1))`, `k=0,...,N-1`, `N=257`.

The formula and the existing `SourceFFD` / original `observation.py` source are normative. There is **no ambiguity about the numeric implementation** and no change to any value or source hash. An independent reviewer must check the H->CIR calculation using this actual formula. This erratum is appended before independent review, not a post-result change.

Status: `PROPOSER_LOCKED_AUDIT_PENDING`; no science run; no `FROZEN` label.
