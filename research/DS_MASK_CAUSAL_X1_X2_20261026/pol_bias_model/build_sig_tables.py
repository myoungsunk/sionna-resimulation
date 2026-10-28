"""Polarization-error variance tables from the packets (truth used ONLY here, to build priors; the filter looks them up with
its own predicted state).  e_s = z_s - h_s(truth) - mu_s  for every packet of every route at every mount.

Tables (RMS of e_s per bin):
  1D_m0 / 1D_m45 : by horizontal anchor distance rho, separately per mount      ('mount-specific' table)
  2D             : by rho  x  |s_hat| (LOS-model s at the state = effective polarization operating point), both mounts pooled
  *_LORO_<R>     : same, built without route family R (R2 / R4 / R5) -> used for that route (leave-one-route-out)
"""
import json, sys
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "reflect_model"))
import common as C
RHO_EDGES = [0, 0.75, 1.5, 2.25, 3, 4.5, 6, 8, 10, 99]
RHO2 = [0, 1.5, 3, 6, 10, 99]; SHAT = [0, 0.3, 0.7, 1.01]
CASES = [f"{r}_{m}" for r in ("R2_aA", "R2_aB", "R4_aA", "R4_aB", "R5_aA", "R5_aB") for m in ("m0", "m45")]


def collect():
    model = C.base_model(); out = []
    for cid in CASES:
        pk = np.load(HERE / "packets" / f"PACKETS_{cid}.npz"); spec = dict(anchor=tuple(pk["anchor"]), robot_z_m=0.45, mount_deg=float(pk["mount_deg"]))
        gt = pk["truth_scoring_only"]; hg, _ = model.batch(np.c_[gt[:, :3], np.zeros(len(gt))], spec)
        e = pk["z"][:, 1] - hg[:, 1] - pk["mu_B"][:, 1]; a = np.array(spec["anchor"][:2]); rho = np.hypot(gt[:, 0] - a[0], gt[:, 1] - a[1])
        out.append(dict(case=cid, route=cid[:2], mount=cid.split("_")[-1], e=e, rho=rho, shat=np.abs(hg[:, 1])))
    return out


def table1d(D):
    e = np.concatenate([d["e"] for d in D]); r = np.concatenate([d["rho"] for d in D]); mids, vals = [], []
    for lo, hi in zip(RHO_EDGES[:-1], RHO_EDGES[1:]):
        s = (r >= lo) & (r < hi)
        if s.sum() >= 20:
            mids.append(0.5 * (lo + min(hi, 14.0))); vals.append(float(np.sqrt(np.mean(e[s] ** 2))))
    return dict(r=[0.0] + mids, sig=[vals[0]] + vals)


def table2d(D):
    e = np.concatenate([d["e"] for d in D]); r = np.concatenate([d["rho"] for d in D]); sh = np.concatenate([d["shat"] for d in D])
    g = np.sqrt(np.mean(e ** 2)); T = []
    for lo, hi in zip(RHO2[:-1], RHO2[1:]):
        row = []
        for a, b in zip(SHAT[:-1], SHAT[1:]):
            s = (r >= lo) & (r < hi) & (sh >= a) & (sh < b)
            row.append(float(np.sqrt(np.mean(e[s] ** 2))) if s.sum() >= 20 else None)
        T.append(row)
    # fill empty cells with the same-rho row mean (or global)
    for row in T:
        vals = [v for v in row if v is not None]
        for j, v in enumerate(row):
            if v is None:
                row[j] = float(np.mean(vals)) if vals else float(g)
    return dict(rho_edges=RHO2, shat_edges=SHAT, sig=T)


def main():
    D = collect(); out = {}
    for m in ("m0", "m45"):
        out[f"1D_{m}"] = table1d([d for d in D if d["mount"] == m])
        for R in ("R2", "R4", "R5"):
            out[f"1D_{m}_LORO_{R}"] = table1d([d for d in D if d["mount"] == m and d["route"] != R])
    out["2D"] = table2d(D)
    for R in ("R2", "R4", "R5"):
        out[f"2D_LORO_{R}"] = table2d([d for d in D if d["route"] != R])
    (HERE / "sig_tables.json").write_text(json.dumps(out, indent=1))
    for k in ("1D_m0", "1D_m45", "2D"):
        print(k, json.dumps(out[k]))


if __name__ == "__main__":
    main()
