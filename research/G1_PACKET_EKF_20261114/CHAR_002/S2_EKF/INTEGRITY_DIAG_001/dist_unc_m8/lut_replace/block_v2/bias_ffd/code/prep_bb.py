"""Static prep: blocks and tables for BV0, BV, BVK (parity) and P0, P1, P2. Writes BB_TABLES.json, ES_*.npy, BB_STATIC.json"""
import sys, json, numpy as np, pandas as pd
sys.path[:0] = ["/home/claude/m8", "/home/claude/lut0", "/home/claude/lut3", "/home/claude/bb"]
from common import env
import h_ref as HR, bv_block as BVM, bb_block as BB
e0 = env(); base, spec = e0["model"], e0["spec"]; ffd = HR.ffd_s_fn(base)
SW = pd.read_csv("/home/claude/m8cal/SWEEP_FEATURES.csv.gz")
KP = json.load(open("/home/claude/m8cal/KRIGE_PARAMS.json")); prm0 = KP["e_s|0"]["params"]
blocks = {"BV0": BB.BB(ffd, spec, SW, field="zero"), "BV": BB.BB(ffd, spec, SW, field="smooth"),
          "P0": BB.BB(ffd, spec, SW, field="zero", off="bin"), "P1": BB.BB(ffd, spec, SW, field="bin", off="bin")}
T = {a: blocks[a].table(SW) for a in blocks}
T["BVK"], es_bv, iv = BB.near_kriging_table(blocks["BV"], SW, spec, prm0)
T["P2"], es_p1, ip = BB.near_kriging_table(blocks["P1"], SW, spec, prm0)
np.save("ES_BV.npy", es_bv); np.save("ES_P1.npy", es_p1)
ref = json.load(open("/home/claude/lut3/TABLE_BVK.json"))
par = {k: float(np.max(np.abs(np.array(T["BVK"][k]) - np.array(ref[k])))) for k in ("c1", "c0")}
X = np.c_[SW.x_eval, SW.y_eval, np.radians(SW.yaw_deg), np.zeros(len(SW))]; b = np.clip(np.searchsorted(BVM.EDG, SW.rho, side="right") - 1, 0, 2)
st = {}
for a, blk in blocks.items():
    m, J = blk.s_fn()(X, spec); r = SW.s_fp.values - m; aa = J[:, 2]
    st[a] = {f"bin{i}": dict(mean=float(r[b == i].mean()), rms=float(np.sqrt(np.mean(r[b == i] ** 2))),
                             head_eq_deg=float(np.degrees(np.sum(aa[b == i] * r[b == i]) / np.sum(aa[b == i] ** 2)))) for i in range(3)}
json.dump(T, open("BB_TABLES.json", "w"), indent=1)
json.dump(dict(parity_BVK_table_maxabs=par, near_kriging=dict(BV=iv, P1=ip), binmeans={a: {str(k): v for k, v in blocks[a].binmeans.items()} for a in blocks},
               station_static=st), open("BB_STATIC.json", "w"), indent=1)
print(json.dumps(par)); print(json.dumps(dict(BV=iv, P1=ip)))
for a in T: print(a, {k: np.round(T[a][k], 6).tolist() for k in ("c1", "c0")})
for a in st: print(a, {k: (round(v["rms"], 4), round(v["head_eq_deg"], 2)) for k, v in st[a].items()})
print(json.dumps({a: {str(k): v for k, v in blocks[a].binmeans.items()} for a in ("P0", "P1")}))
