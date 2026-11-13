"""TB3 trackA per-station heading drift across TEACH and REPEAT runs.

Usage:
  python -I analyze_runs.py --teach teach.json --repeat R1=repeat_1004.json --repeat R2=repeat_1113.json \
      [--bag-arrays bag_arrays.npz] --out OUT_DIR

Definitions (station k = P001..P018):
- TEACH increment: odom yaw at station base (k) - (k-1). The TEACH robot is aligned to the wall at each base.
- REPEAT increment: (odom yaw - ICP yaw) at the last align capture of station k minus the same at k-1.
  REPEAT aligns to the TEACH scan, so the physical pose matches TEACH and the increment is the odom (IMU-fused) error.
- Sweep component: (odom yaw at base_after - odom yaw at last align) - (ICP yaw at base_after - ICP yaw at last align).
  Transit/align component = station increment mean - sweep component mean.
- Paired difference: REPEAT increment - TEACH increment for the same station.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def stats(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    return dict(mean=float(x.mean()), sd=float(x.std(ddof=1)), n=int(len(x)), se=float(x.std(ddof=1) / math.sqrt(len(x))),
                sum=float(x.sum()))


def teach_increments(t):
    y = np.array([math.degrees(s["base"]["odom"][2]) for s in t["stations"]])
    return np.diff(np.degrees(np.unwrap(np.radians(y))))


def repeat_quantities(r):
    oy, ic, sweep, ba_icp, status, tries = [], [], [], [], [], []
    for s in r["stations"]:
        al = s["align"][-1]
        oy.append(math.degrees(al["odom"][2]))
        ic.append(math.degrees(al["icp"]["pose"][2]) if al.get("icp") else np.nan)
        ba = s.get("base_after") or {}
        ok = (al.get("icp") or {}).get("usable") and (ba.get("icp") or {}).get("usable")
        if ok:
            d_odom = math.degrees(math.remainder(ba["odom"][2] - al["odom"][2], 2 * math.pi))
            d_icp = math.degrees(ba["icp"]["pose"][2] - al["icp"]["pose"][2])
            sweep.append(d_odom - d_icp)
            ba_icp.append(math.degrees(ba["icp"]["pose"][2]))
        else:
            sweep.append(np.nan)
            ba_icp.append(np.nan)
        status.append(s.get("align_status"))
        tries += [len(a["tries"]) for a in s["angles"]]
    oy = np.degrees(np.unwrap(np.radians(oy)))
    inc = np.diff(oy - np.array(ic))
    return dict(increments=inc, sweep=np.array(sweep), base_after_icp=np.array(ba_icp), status=status,
                tries_per_angle=float(np.mean(tries)))


def bag_summary(npz: Path):
    d = np.load(npz)
    O, J = d["O"], d["J"]
    t = O[:, 0]
    yo = np.unwrap(O[:, 1])
    jl, jr = np.interp(t, J[:, 0], J[:, 1]), np.interp(t, J[:, 0], J[:, 2])
    r, b = 0.033, 0.287
    dyo, dt_ = np.diff(yo), np.diff(t)
    dye = r * (np.diff(jr) - np.diff(jl)) / b
    v = r * (np.diff(jr) + np.diff(jl)) / 2 / dt_
    w = np.degrees(dye) / dt_
    rot = (np.abs(v) < 0.005) & (np.abs(w) > 0.02)
    out = {}
    for sgn, name in ((1, "CCW"), (-1, "CW")):
        m = rot & (np.sign(w) == sgn)
        out[f"odom_over_encoder_{name}"] = float(dyo[m].sum() / dye[m].sum())
        slow = m & (np.abs(w) < 0.5)
        out[f"slow_lt0p5_odom_over_encoder_{name}"] = float(dyo[slow].sum() / dye[slow].sum())
    tot = np.abs(np.degrees(dye[rot])).sum()
    out["rotation_fraction_below_0p5_dps"] = float(np.abs(np.degrees(dye[rot & (np.abs(w) < 0.5)])).sum() / tot)
    moving = np.r_[False, (np.abs(np.diff(jl)) > 1e-9) | (np.abs(np.diff(jr)) > 1e-9)]
    last, since = -1e9, np.zeros(len(t))
    for i in range(len(t)):
        if moving[i]:
            last = t[i]
        since[i] = t[i] - last
    m = (~moving[1:]) & (since[1:] <= 0.5)
    out["yaw_change_within_0p5s_after_wheel_stop_deg"] = float(np.degrees(dyo[m].sum()))
    out["nominal_wheel"] = dict(radius_m=r, separation_m=b)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--teach", type=Path, required=True)
    ap.add_argument("--repeat", action="append", required=True, help="LABEL=path")
    ap.add_argument("--bag-arrays", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    teach = json.loads(a.teach.read_text())
    dT = teach_increments(teach)
    res = dict(teach=dict(file=str(a.teach), sha256=sha256(a.teach), version=teach.get("version"),
                          created=teach.get("created"), increments=stats(dT)), repeats={}, paired={})
    reps = {}
    for item in a.repeat:
        lab, p = item.split("=", 1)
        p = Path(p)
        r = json.loads(p.read_text())
        q = repeat_quantities(r)
        reps[lab] = q
        sw = stats(q["sweep"])
        res["repeats"][lab] = dict(file=str(p), sha256=sha256(p), version=r.get("version"), created=r.get("created"),
                                   increments=stats(q["increments"]), sweep=sw,
                                   transit_align_mean=stats(q["increments"])["mean"] - sw["mean"],
                                   base_after_icp=stats(q["base_after_icp"]),
                                   not_converged=q["status"].count("NOT_CONVERGED"), tries_per_angle=q["tries_per_angle"],
                                   corr_with_teach=float(np.corrcoef(q["increments"], dT)[0, 1]))
        res["paired"][f"{lab}-TEACH"] = stats(q["increments"] - dT)
    labs = list(reps)
    for i in range(len(labs)):
        for j in range(i + 1, len(labs)):
            x, y = reps[labs[j]]["increments"], reps[labs[i]]["increments"]
            res["paired"][f"{labs[j]}-{labs[i]}"] = stats(x - y)
            res["repeats"][labs[j]][f"corr_with_{labs[i]}"] = float(np.corrcoef(x, y)[0, 1])
    means = [res["teach"]["increments"]["mean"]] + [res["repeats"][l]["increments"]["mean"] for l in labs]
    res["run_mean_sd"] = float(np.std(means, ddof=1))
    res["run_mean_max_over_min"] = float(max(means) / min(means))
    if a.bag_arrays:
        res["bag"] = dict(file=str(a.bag_arrays), sha256=sha256(a.bag_arrays), summary=bag_summary(a.bag_arrays))
    a.out.mkdir(parents=True, exist_ok=True)
    out = a.out / "RESULTS.json"
    out.write_text(json.dumps(res, indent=1))
    man = dict(command=sys.argv, timestamp_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
               outputs={str(out): sha256(out)}, script_sha256=sha256(Path(__file__)))
    (a.out / "MANIFEST.json").write_text(json.dumps(man, indent=1))
    print(json.dumps({k: res[k] for k in ("run_mean_sd", "run_mean_max_over_min")}, indent=1))


if __name__ == "__main__":
    main()
