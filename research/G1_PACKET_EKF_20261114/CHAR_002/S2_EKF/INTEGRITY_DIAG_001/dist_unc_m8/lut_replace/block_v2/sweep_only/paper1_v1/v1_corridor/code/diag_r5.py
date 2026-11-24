import sys, json, pickle, numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/v1"); from v1_common import *
from common import packet, TRUTH, env; import h_ref as HR, sw_block_fullco as SB, m8_replay as M
from run_m8s3 import sweep_packet, ZERO_SB
g, Rrr, Rss = pickle.load(open("CAL_V1.pkl", "rb")); Rrr, Rss = np.array(Rrr), np.array(Rss)
F = pd.read_csv(f"{FZ}/6a69a36ad0f5_OBSERVATION_FEATURES_LABELS.csv.gz"); F = F[F.channel == "full"]
e = env(); eS = HR.swap_env(e, SB.SWB().s_fn()); r = "R5"; seed = int(sys.argv[1])
p = packet("B0", seed, r); T = F[F.case == f"{r}_aB_m0"].set_index("pose_id").loc[p["pose_id"]].reset_index()
bh = bin3(rho_hat(p["z"][:, 0])); mu = g.predict(T[EXIST]); z0 = np.zeros(len(mu)); tab = dict(edges=E3.tolist(), c1=[0., 0., 0.], c0=Rss.tolist())
truth = TRUTH[r]["truth"]; t = p["t"]; er = T.e_r.values
print("x0", np.round(p["x0"], 3), "truth0", np.round(truth[0], 3), "rho0", round(float(np.hypot(truth[0,0]-10, truth[0,1])), 2))
for name, m in (("U0", z0), ("U3", mu)):
    tr = M.replay_m8(sweep_packet(p, m, z0, Rrr[bh], Rss[bh]), eS, "F0", table=tab, sigma_b=ZERO_SB, condition="B0", **M.ARM_MODES["F0"])
    k = [0, 25, 50, 100, 150, 200]
    print(name, "| t", np.round(t[k], 1), "| y_est", np.round(tr["x"][k, 1], 2), "| y_true", np.round(truth[k, 1], 2), "| psi err deg", np.round(np.degrees((tr["x"][k, 2]-truth[k, 2]+np.pi)%(2*np.pi)-np.pi), 1),
          "| range res (e_r - mu) cm first 50:", round(100*float(np.mean(er[:50]-m[:50])), 2), "| accept first 50", round(float(np.mean(tr["mask"][:50])), 2))
