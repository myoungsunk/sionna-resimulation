"""V1 (Paper 1): SWB + G0 white. Frozen inputs: SWB block (fullco, coef sha fbbd6430), R_ss = V0-2 simple rho-bin mean-square,
mu_r = U3 (HGB EXIST, uniform weights; V0-1b), R_rr = U3 x-column-out CV mean-square by rho_hat bin (rho_hat from measured range)."""
import sys, json, numpy as np, pandas as pd
sys.path[:0] = ["/home/claude/m8", "/home/claude/lut0", "/home/claude/v0"]
from sklearn.ensemble import HistGradientBoostingRegressor
FZ = "/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/MOUNT45_VALIDATION_20261116/frozen_inputs/OFFICE_CORRIDOR_TRANSFER_FIX_20261026"
EXIST = ['log_fp_power','abs_s_fp','early4','early8','early16','delay_rms_ns','peak_diff_ns','eta_fp_win80','s_diff4','s_diff8','s_diff16','tap_pol_var80','jones_diversity','freq_s_var','detector_s_span','detector_delay_span_ns']
E3 = np.array([0, 3, 6, 10.]); bin3 = lambda r: np.clip(np.searchsorted(E3, r, side="right") - 1, 0, 2)
B_OLD = -0.5316; DH = 2.2
rho_hat = lambda rng: np.sqrt(np.maximum((np.asarray(rng) - B_OLD)**2 - DH**2, 0.))
def build_cal():
    SW = pd.read_csv("/home/claude/m8cal/SWEEP_FEATURES.csv.gz"); col = SW.x_eval.round(3)
    hp = dict(max_iter=200, learning_rate=0.05, max_leaf_nodes=15, l2_regularization=1.0, random_state=0)
    cv = np.zeros(len(SW))
    for c in np.sort(col.unique()):
        te = (col == c).values; cv[te] = HistGradientBoostingRegressor(**hp).fit(SW.loc[~te, EXIST], SW.e_r[~te]).predict(SW.loc[te, EXIST])
    res = SW.e_r.values - cv; bh = bin3(rho_hat(SW.range_m))
    Rrr = [float(np.mean(res[bh == q]**2)) for q in range(3)]
    g = HistGradientBoostingRegressor(**hp).fit(SW[EXIST], SW.e_r)
    V = json.load(open("/home/claude/v0/V0_BLOCK_RSS.json"))["simple"]
    Rss = [v["var"] + v["mean"]**2 for v in V]
    return g, Rrr, Rss
