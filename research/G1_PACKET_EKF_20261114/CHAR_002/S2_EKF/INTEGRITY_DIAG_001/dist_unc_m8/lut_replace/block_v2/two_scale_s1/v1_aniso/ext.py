import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001/dist_unc_m8/step3_sweep/dev_02/code")
import feats as FT
U = "/mnt/user-data/uploads/SLAM_bot/BLOCK_C_M7_NEAR_20261119_2ujQQZVt/results"
Hf = np.load(f"{U}/H/BLOCKC_B/H_full.npy"); Hl = np.load(f"{U}/H/BLOCKC_B/H_LoS.npy"); P = pd.DataFrame(json.load(open(f"{U}/poses/BLOCKC_B/rf_poses.json")))
Ff = FT.features(Hf); Fl = FT.features(Hl)
P["s_full"] = Ff.s_fp.values; P["s_los"] = Fl.s_fp.values; P["valid"] = Ff.valid.values; P["range_m"] = Ff.range_m.values
P.to_csv("NEAR4CM_S.csv", index=False); print(P.head()); print(P.valid.mean())
