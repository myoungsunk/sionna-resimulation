# CUT_ODO frozen protocol
Primary: R2_aA_m45, R4_aA_m0, R4_aB_m0 x B0/L2 (paired).
Order: unit Jacobian check; all six OFF controls alpha0/1 exact E1 parity <=1e-10; only then CUT_ODO alpha0/1.
At interval k-1 -> k replace starting psi only in position displacement by GT psi[k-1]. Keep ds, gyro, estimated gyro bias, sinc curvature and heading propagation unchanged. This cuts estimated starting heading -> position; it does NOT cut gyro-bias -> position.
Use original core.transition on a copy with GT psi to obtain position/F/G; set F[position,psi]=0. Heading mean uses original estimated state transition. Heading F/G unchanged. Q unchanged; covariance uses modified F/G and original covariance validator. Measurements use estimated state and original SourceFFD. mask A_B, mu_s and R unchanged; range alpha0/1.
GT is scoring trajectory column2, previous packet, no future interpolation. Initial posterior unchanged. All-time mask and same-packet alignment checked.
Report posterior/prior beta and et; t>=30 all packets. G=alpha1 bias-alpha0 bias. f_magnitude=1-|Gcut|/|GE1| and f_signed=1-Gcut/GE1, sign flip. Angle denominator threshold .01deg; >=.7 supports starting-heading propagation path necessity under oracle, .3-.7 partial, <.3 insufficient. Not statistical significance; no causal uniqueness. NEES under oracle descriptive only.
Preserve original artifacts. No CUT_RT or other experiments in this run.
