# R2 Full preflight correction

FULL_001 is preserved as FAILED. Its preflight compared the new MB_VAR W0 result against a stored OFF_MB trajectory. The original producer at commit 7e2855314de867e0481f8eb5ed1a07c48710f364, research/DS_MASK_CAUSAL_X1_X2_20261026/pol_bias_model/exp_pb.py, identifies that stored trajectory as MB_ORIG and validates it only with mode=orig. OFF_MB supplies the historical observation mean; it is not the MB_VAR trajectory reference.

FULL_002 fixes only the preflight reference. It first reproduces historical MB_ORIG from the locked inputs, then validates new W0 MB_VAR against the original pb.run mode=var and independent ctl.run MB/R_var, with exact gate-mask equality. All inputs, controls, interventions, scoring, and seeds remain fixed. The first failed attempt ran no seed10-29 natural or branching calculations.

B0 validation: historical state maximum absolute difference 3.552713678800501e-15; covariance 5.377642775528102e-17. W0 and both MB_VAR reference implementations agree exactly. L2 validation will be recorded in FULL_002/SELF_PARITY.json before its seed10-29 calculations.
