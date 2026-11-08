# PALO single-metric closed-loop experiment

One scalar gate per policy, original NIS gate shared. Exact own-state X/P nonlinear replay.
R2 and seed0 only. Same-route development/test, all thresholds reported, not production validation.

## Important correction
Previous RF/CIR pairing used k-200 on a 979-frame RF array. Current analysis joins by absolute k and checks pose_id; previous CIR AUC and small-RF/large-harm claims are withdrawn. Motion-only and original Hpsi arrays were not shifted.

## Development-selected policy per family (thresholds NOT chosen on late test)
        family                     id  worst_h  worst_xy  total_accept  worst_joint
            DR                     DR 1.000000  1.000000             0     1.000000
   h_candidate       h_candidate_ge_3 1.000000  1.000000             0     1.000000
         h_fd1             h_fd1_ge_3 1.000000  1.000000             0     1.000000
       h_prior           h_prior_ge_3 1.000000  1.000000             0     1.000000
       h_sroot           h_sroot_ge_3 1.000000  1.000000             0     1.000000
    innovation     innovation_le_0.01 1.001837  1.001919           204     1.001919
           nis             nis_le_0.1 1.131362  1.214857           524     1.214857
correction_deg correction_deg_le_0.05 1.613243  1.005749           302     1.613243
       ds_tap2         ds_tap2_le_0.2 3.492286  0.603421          1364     3.492286
          fp13            fp13_le_2.2 3.790253  0.765593          1220     3.790253
          fp25              fp25_le_3 3.793518  0.629005           908     3.793518
       ds_time         ds_time_le_0.2 3.859682  1.060737          1480     3.859682
   root_exists            root_exists 4.544015  1.861277          1201     4.544015
            S4                     S4 4.813441  1.406002          1520     4.813441

## Full late test results for those fixed policies
level                     id  heading_rmse_deg  xy_rmse_m  accepted   head95     xy95  both_better_DR
   B0                     DR          0.543271   0.108080         0 1.000000 1.000000           False
   B0                     S4          0.580485   0.348426       271 0.727599 0.000000           False
   B0           h_prior_ge_3          0.543271   0.108080         0 1.000000 1.000000           False
   B0             h_fd1_ge_3          0.543271   0.108080         0 1.000000 1.000000           False
   B0       h_candidate_ge_3          0.543271   0.108080         0 1.000000 1.000000           False
   B0           h_sroot_ge_3          0.543271   0.108080         0 1.000000 1.000000           False
   B0            root_exists          0.461854   0.402347       271 0.863799 0.000000           False
   B0 correction_deg_le_0.05          1.937744   0.258933       133 0.849462 1.000000           False
   B0             nis_le_0.1          0.632388   0.072153       166 1.000000 1.000000           False
   B0     innovation_le_0.01          0.302712   0.109153        84 1.000000 1.000000           False
   B0            fp13_le_2.2          2.193349   0.411273       176 0.000000 0.000000           False
   B0              fp25_le_3          3.781654   0.573326        84 0.000000 0.000000           False
   B0         ds_tap2_le_0.2          3.784559   0.623917       224 0.000000 0.000000           False
   B0         ds_time_le_0.2          1.504147   0.378694       270 0.139785 0.000000           False
   L0                     DR          2.221173   0.153619         0 1.000000 1.000000           False
   L0                     S4          0.578097   0.346053       271 0.724014 0.000000           False
   L0           h_prior_ge_3          2.221173   0.153619         0 1.000000 1.000000           False
   L0             h_fd1_ge_3          2.221173   0.153619         0 1.000000 1.000000           False
   L0       h_candidate_ge_3          2.221173   0.153619         0 1.000000 1.000000           False
   L0           h_sroot_ge_3          2.221173   0.153619         0 1.000000 1.000000           False
   L0            root_exists          0.470387   0.391922       271 0.867384 0.000000           False
   L0 correction_deg_le_0.05          2.582258   0.337238       117 0.849462 1.000000           False
   L0             nis_le_0.1          0.884534   0.097128       161 1.000000 1.000000            True
   L0     innovation_le_0.01          1.952194   0.153864        86 1.000000 1.000000           False
   L0            fp13_le_2.2          2.176511   0.415867       176 0.000000 0.000000           False
   L0              fp25_le_3          3.777442   0.567564        84 0.000000 0.000000           False
   L0         ds_tap2_le_0.2          3.745700   0.623848       223 0.000000 0.000000           False
   L0         ds_time_le_0.2          1.475437   0.375382       270 0.161290 0.000000           False
   L1                     DR          8.962147   0.789215         0 1.000000 1.000000           False
   L1                     S4          0.639174   0.345433       271 0.706093 0.000000            True
   L1           h_prior_ge_3          8.962147   0.789215         0 1.000000 1.000000           False
   L1             h_fd1_ge_3          8.962147   0.789215         0 1.000000 1.000000           False
   L1       h_candidate_ge_3          8.962147   0.789215         0 1.000000 1.000000           False
   L1           h_sroot_ge_3          8.962147   0.789215         0 1.000000 1.000000           False
   L1            root_exists          0.493724   0.448310       268 0.978495 0.000000            True
   L1 correction_deg_le_0.05          8.539437   0.693864        29 1.000000 1.000000            True
   L1             nis_le_0.1          5.491976   0.313955        72 0.000000 0.637993            True
   L1     innovation_le_0.01          8.521481   0.771508        32 0.000000 1.000000            True
   L1            fp13_le_2.2          2.196237   0.417246       176 0.000000 0.000000            True
   L1              fp25_le_3          3.799758   0.572710        84 0.000000 0.000000            True
   L1         ds_tap2_le_0.2          3.624626   0.620886       222 0.000000 0.000000            True
   L1         ds_time_le_0.2          1.477118   0.372551       270 0.164875 0.000000            True
   L2                     DR         34.247396   3.313577         0 0.924731 0.605735           False
   L2                     S4          0.604037   0.346375       271 0.716846 0.000000            True
   L2           h_prior_ge_3         34.247396   3.313577         0 0.924731 0.605735           False
   L2             h_fd1_ge_3         34.247396   3.313577         0 0.924731 0.605735           False
   L2       h_candidate_ge_3         34.247396   3.313577         0 0.924731 0.605735           False
   L2           h_sroot_ge_3         34.247396   3.313577         0 0.924731 0.605735           False
   L2            root_exists          0.503025   0.493902       267 1.000000 0.000000            True
   L2 correction_deg_le_0.05         34.330110   3.312341         0 0.000000 0.000000           False
   L2             nis_le_0.1         33.336554   3.031463         0 0.000000 0.000000            True
   L2     innovation_le_0.01         34.399547   3.328308         0 0.000000 0.000000           False
   L2            fp13_le_2.2          2.199517   0.415515       176 0.000000 0.000000            True
   L2              fp25_le_3          3.793583   0.567939        84 0.000000 0.000000            True
   L2         ds_tap2_le_0.2          3.641235   0.618096       223 0.000000 0.000000            True
   L2         ds_time_le_0.2          1.438004   0.374489       270 0.164875 0.000000            True

See ALL_METRICS.csv and all trajectories for the full exploratory sweep.
