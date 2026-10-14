# R3 pre-execution code audit and controlled implementation contract

Research purpose: repair four frozen P2 failures due to numerical cancellation of direct J(y+d)-J(y), NOT modify inference model. Only then execute original P2 (3 routes × 2 biases × 100 trials, 4 methods), with relevant tests and input integrity checked BEFORE running. Never conflate real RF and synthetic.

**Audit of prior implementation**:
1. In original core.py direct acceptance `J_candidate <= J_current + 1e-4 t g·d + 4 eps max(1,|J|)` cannot resolve ∆J~1e-16 when J~1: sign may invert even when actual ∆J<0. D3 80-digit calculations establish four failures with valid full GN steps attaining norm(gradient)<1e-8. Therefore direct-cost acceptance must not be authoritative near machine resolution.
2. Original R2 integrated_descent is conditional on DIRECT gate failure, plus `64eps`/tiny-step/strong-Wolfe safeguards. It can reject real descent or accept vanishing backtracked fractions. This was not mandated by user's mathematical goal.
3. Audit must verify original J, g, GN matrix, prior, s/r observations and local covariance are unchanged; full step is accepted only when *stable ∆J* certifies descent; otherwise backtrack or explicit numerical status. No fake CONVERGED and no silent fallback.
4. For residual `r(y)=[y, L_R^-1(z-h(mu+L_P y))]`, use stable algebraic identity
`J(y+d)-J(y) = r(y)·(r(y+d)-r(y)) + 0.5||r(y+d)-r(y)||²`.
This avoids subtracting two O(1) objective values; if direct model difference near floating resolution, compute the line integral of true gradient as a secondary consistency diagnostic (not a branch/curvature heuristic). The *same* exact Gaussian posterior objective is optimized.
5. Stable residual algebra in double can still have finite precision in h(x+d)-h(x); if its reliability is inconclusive report NUMERICALLY_STALLED. Never relax 1e-8 or alter Q,R,seed,truth.
6. Audit of diagnostic tests: optional history metadata must not block core model; pre-run static audit of script/integrity/sha before all test/experiment calls. R3 benchmark is four original frozen failure prior/observation snapshots, both saved-iterate and range-first. P0/P1/R1/R2 for affected code must be checked.
7. Original P2's all-route-support primary science hypothesis remains a claim about all routes, not a blanket technical execution gate. A result contradicting it triggers causal decomposition and user review of a changed scientific direction. Source validity and independent RF adapter research may proceed separately.
8. P3–P6 remain specified high-level research tasks, NOT already implemented; they require their own audited code and matching frozen RF data. Never mark PASS without execution or resolve G3 numerical divergence by threshold relaxation.

Source branch: research/ekf4-r3-p2-p6-20261014. Historical audit, R2/D3/D3B, old FAIL artifacts remain immutable.
