# Scalar solver independent audit
Verdict: ACCEPT
Reviewer: /root/ablation_audit
The measurement-space stationary equation and reconstructed candidates match the fixed-prior MAP objective. Original gradient, Hessian, stationarity and objective guards are retained. Loss, scale, gate and trained parameters are unchanged. Only Cauchy and Student-t use the optional scalar solver; M0 and M-H are untouched.
100 tests passed. Maximum objective difference: 8.88e-16 for 100 benchmark comparisons; 2.22e-16 for 72 RF comparisons. Finite-precision root enumeration is not a proof of a global optimum.
Parent verification: SNOISE2/S02/S12/S22 completed 48 cells each with PASS baseline parity, zero maximum difference. Full execution admitted after these checks.
