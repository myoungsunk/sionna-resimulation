# CUT_RT protocol
Triggered by world-coordinate ledger: R2_m45 range-at-update tangent contribution is large; R4_aA mixed, R4_aB radial projection dominates descriptively.
Primary six conditions, alpha0/1. All OFF controls must reproduce original E1 x/P/prior/Pprior/h/H/K/mu/R/nu/acc within 1e-10 before intervention.
Use current packet GT horizontal outward radial unit vector ur=(p_true-a)/norm; ut=rotate90(ur). This matches ledger axis and is an oracle.
Compute original JOINT 4x2 Kalman gain. Change only range-column position entries: K[:2,0] <- (I-ut ut^T) K[:2,0]. Heading and gyro-bias range gain unchanged; polarization column unchanged at that step. Joint update with original innovations; Joseph covariance with modified gain; no sequential relinearization.
Recompute future x/P/H/K naturally. mask A_B; mu_s/R unchanged; original motion. Rejected packets no update. Assert actual accepted range tangent displacement <=1e-10. Same packet source mapping recorded.
All t>=30 including rejected packets. G=bias(alpha1)-bias(alpha0); report beta/heading/et gaps, f_magnitude and f_signed, sign flip. Angle denominator .01deg. >=.7 supports direct range-position-tangent path necessity under this intervention; .3-.7 partial; <.3 insufficient. Not causal uniqueness. B0/L2 paired. Preserve originals.
