"""V0 (unit / parity checks) and V1 (model vs ray-traced channel at GT poses).  No filter is run here.

  python exp_v01.py --stage V0
  python exp_v01.py --stage V1 [--cases all|primary] [--variants all|primary]

V1 compares, on every packet pose of the B0 control trace (route order), the modeled first-path observables with the
stored full-channel observables (which equal the filter inputs to 1e-16).  Truth is used only as the evaluation pose.
"""
from __future__ import annotations

import argparse
import json
import math
import time

import numpy as np
import pandas as pd

import common as C
from refl_model import ReflectiveFFD, reflection_coefficients, corridor_planes, enumerate_sequences, trace_sequence

C.OUT.mkdir(parents=True, exist_ok=True)
VARIANTS = [(d, m) for m in ("slab", "halfspace") for d in (1, 2, 3)]
PRIMARY_VARIANT = (3, "slab")
CRIT = dict(far_rms_max=0.02, far_slow_rms_max=0.01, tap_agree_min=0.95, reduction_min=0.90, approx_reduction_min=0.70)


def log(msg, **kw):
    rec = dict(t=time.strftime("%Y-%m-%dT%H:%M:%S"), msg=msg, **kw)
    with open(C.OUT / "events.jsonl", "a") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    print(msg, kw, flush=True)


# ------------------------------------------------------------------ V0
def stage_v0():
    base = C.base_model()
    checks = []

    def add(name, ok, **info):
        checks.append(dict(check=name, ok=bool(ok), **info))
        log("V0 " + name, ok=bool(ok), **info)

    # (a) Fresnel limits and conventions
    f = np.array([6.5e9])
    cos_i = np.array([1.0, 0.7, 0.2])
    rte, rtm = reflection_coefficients(cos_i, np.array([1e12 - 0j]), 0.2, f, "halfspace")
    add("fresnel_PEC_limit", np.allclose(rte[:, 0], -1, atol=1e-5) and np.allclose(rtm[:, 0], 1, atol=1e-5))
    rte, rtm = reflection_coefficients(np.array([1.0]), np.array([5.24 - 0.5j]), 0.2, f, "halfspace")
    add("fresnel_normal_incidence_TM_eq_minus_TE", np.allclose(rtm, -rte, atol=1e-12))
    rte, rtm = reflection_coefficients(cos_i, np.array([5.24 - 0.5j]), 0.2, f, "halfspace")
    add("fresnel_passive", (abs(rte) <= 1 + 1e-12).all() and (abs(rtm) <= 1 + 1e-12).all())
    s_te, s_tm = reflection_coefficients(cos_i, np.array([5.24 - 3.0j]), 5.0, f, "slab")
    h_te, h_tm = reflection_coefficients(cos_i, np.array([5.24 - 3.0j]), 5.0, f, "halfspace")
    add("slab_thick_lossy_equals_halfspace", np.allclose(s_te, h_te, atol=1e-6) and np.allclose(s_tm, h_tm, atol=1e-6))

    # (b) image-method geometry: reflection law, path length, bounds
    planes = corridor_planes()
    rng = np.random.default_rng(1)
    tags = np.column_stack([rng.uniform(1, 19, 400), rng.uniform(-0.6, 0.6, 400), np.full(400, 0.45)])
    anchor = np.array([4.0, 0.0, 2.65])
    worst_law, worst_len, nvalid = 0.0, 0.0, 0
    for seq in enumerate_sequences(6, 3)[1:]:
        valid, V, L = trace_sequence(anchor, tags, seq, planes)
        if not valid.any():
            continue
        V = V[valid]; L = L[valid]; nvalid += int(valid.sum())
        seg = np.diff(V, axis=1)
        worst_len = max(worst_len, float(np.max(abs(np.linalg.norm(seg, axis=2).sum(1) - L))))
        u = seg / np.linalg.norm(seg, axis=2, keepdims=True)
        for j, pidx in enumerate(seq):
            n = np.array(planes[pidx].normal, float)
            kin, kout = u[:, j], u[:, j + 1]
            refl = kin - 2 * (kin @ n)[:, None] * n[None]
            worst_law = max(worst_law, float(np.max(np.linalg.norm(refl - kout, axis=1))))
    add("image_reflection_law", worst_law < 1e-9, worst=worst_law, n_paths=nvalid)
    add("image_path_length", worst_len < 1e-9, worst=worst_len)

    # (c) depth 0 == SourceFFD (observables, tap, Jacobian) on random states, both mounts
    m0 = ReflectiveFFD(base, max_depth=0)
    for case in ("R2_aA_m45", "R4_aB_m0"):
        st = np.column_stack([rng.uniform(1.2, 18.9, 200), rng.uniform(-0.5, 0.5, 200), rng.uniform(-np.pi, np.pi, 200), np.zeros(200)])
        hb, Jb, db = base.batch(st, C.CASES[case], gradient=True, return_diagnostics=True)
        hm, Jm, dm = m0.batch(st, C.CASES[case], gradient=True, return_diagnostics=True)
        add(f"los_parity_obs_{case}", np.max(abs(hb - hm)) < 1e-9 and (db["tap"] == dm["tap"]).all(), max_abs=float(np.max(abs(hb - hm))))
        rel = np.abs(Jm[:, 1, :3] - Jb[:, 1, :3]) / np.maximum(np.abs(Jb[:, 1, :3]), 1e-3)
        add(f"los_parity_jacobian_{case}", np.median(rel) < 1e-2, median_rel=float(np.median(rel)), p95_rel=float(np.percentile(rel, 95)))

    # (d) depth 0 reproduces the stored LOS channel observables at GT packet poses (all 7 routes)
    for case in C.CASES:
        z = C.load_control(case, "B0"); pid = z["pose_id"]; gt = z["truth_scoring_only"]
        _, Hl, _ = C.load_rf(case)
        from qclean_uwb.drivesim import observation as O
        ol = O.observe(np.asarray(Hl[pid]), m0.freqs, None, None, tx=0)
        st = np.column_stack([gt[:, :3], np.zeros(len(gt))])
        hm, _, dm = m0.batch(st, C.CASES[case], gradient=False, return_diagnostics=True)
        add(f"los_channel_parity_{case}", np.nanmax(abs(ol["s"] - hm[:, 1])) < 1e-4 and np.mean(ol["index"] == dm["tap"]) > 0.999,
            max_abs_s=float(np.nanmax(abs(ol["s"] - hm[:, 1]))), tap_agree=float(np.mean(ol["index"] == dm["tap"])))
    pd.DataFrame(checks).to_csv(C.OUT / "V0_CHECKS.csv", index=False)
    ok = all(c["ok"] for c in checks)
    (C.OUT / "V0_GATE.json").write_text(json.dumps(dict(status="PASS" if ok else "FAIL", n=len(checks), failed=[c["check"] for c in checks if not c["ok"]]), indent=1))
    C.write_manifest("V0", dict(checks=[c["check"] for c in checks]), ["V0_CHECKS.csv", "V0_GATE.json"])
    return ok


# ------------------------------------------------------------------ V1
def nmse_db(Hm, Hf):
    """Per-pose NMSE (dB) of the TX0 channel over bins and both RX ports: raw, and after one optimal complex scalar."""
    e_raw = np.sum(abs(Hm - Hf) ** 2, axis=(1, 2)) / np.sum(abs(Hf) ** 2, axis=(1, 2))
    a = np.sum(np.conj(Hm) * Hf, axis=(1, 2)) / np.maximum(np.sum(abs(Hm) ** 2, axis=(1, 2)), 1e-300)
    e_al = np.sum(abs(a[:, None, None] * Hm - Hf) ** 2, axis=(1, 2)) / np.sum(abs(Hf) ** 2, axis=(1, 2))
    return 10 * np.log10(np.maximum(e_raw, 1e-30)), 10 * np.log10(np.maximum(e_al, 1e-30))


def stage_v1(cases, variants):
    from qclean_uwb.drivesim import observation as O
    base = C.base_model()
    rows, series, rs_rows = [], {}, []
    models = {v: ReflectiveFFD(base, max_depth=v[0], material_mode=v[1], range_mode="fp") for v in [(0, "slab")] + variants}
    for case in cases:
        z = C.load_control(case, "B0"); pid = z["pose_id"]; gt = z["truth_scoring_only"]; acc = z["acc"][:, z["jb"]]
        Hf, Hl, _ = C.load_rf(case)
        Hfull = np.asarray(Hf[pid])[..., 0]                              # TX0 -> (n, nf, 2)
        of = O.observe(np.asarray(Hf[pid]), models[(0, "slab")].freqs, None, None, tx=0)
        zs = z["nu"][:, z["jb"], 1] + z["h"][:, z["jb"], 1] + z["mu"][:, z["jb"], 1]
        zr = z["nu"][:, z["jb"], 0] + z["h"][:, z["jb"], 0] + z["mu"][:, z["jb"], 0]
        assert np.nanmax(abs(of["s"] - zs)) < 1e-12 and np.nanmax(abs(of["range_m"] - zr)) < 1e-12, "FULL_CHANNEL_NOT_FILTER_INPUT"
        a = np.array(C.CASES[case]["anchor"][:2]); rg = np.hypot(gt[:, 0] - a[0], gt[:, 1] - a[1])
        st = np.column_stack([gt[:, :3], np.zeros(len(gt))])
        series[case] = dict(t=z["t_s"], rg=rg, s_full=of["s"], tap_full=of["index"], acc=acc)
        for v, m in models.items():
            t0 = time.time()
            Hm, paths = m.channel(st, C.CASES[case], return_paths=True)
            ob, cir = m.observe(Hm)
            res = of["s"] - ob["s"]
            sl = C.smooth(res)
            nm_raw, nm_al = nmse_db(Hm, Hfull)
            cnt = np.zeros(len(st))
            for p in paths:
                cnt[p["idx"]] += 1
            tag = f"d{v[0]}_{v[1]}"
            series[case][tag] = ob["s"]
            for lo, hi in zip(C.DIST_BINS[:-1], C.DIST_BINS[1:]):
                k = acc & (rg >= lo) & (rg < hi)
                rows.append(dict(case=case, variant=tag, depth=v[0], mode=v[1], bin=f"{lo}-{hi}", n=int(k.sum()),
                                 s_res_rms=float(np.sqrt(np.mean(res[k] ** 2))), s_res_mean=float(np.mean(res[k])),
                                 s_slow_rms=float(np.sqrt(np.mean(sl[k] ** 2))),
                                 tap_agree=float(np.mean(ob["index"][k] == of["index"][k])),
                                 fp_range_res_rms_cm=float(100 * np.sqrt(np.mean((ob["range_m"][k] - of["range_m"][k]) ** 2))),
                                 nmse_raw_db_med=float(np.median(nm_raw[k])), nmse_aligned_db_med=float(np.median(nm_al[k])),
                                 n_paths_mean=float(np.mean(cnt[k]))))
                if v == PRIMARY_VARIANT:
                    rs_rows.append(dict(case=case, bin_lo=lo, bin_hi=hi, n=int(k.sum()), res_var=float(np.var(res[k])), res_mean=float(np.mean(res[k]))))
            log("V1 variant done", case=case, variant=tag, sec=round(time.time() - t0, 1))
        pd.DataFrame(rows).to_csv(C.OUT / "V1_OBSERVABLES.csv", index=False)
    pd.DataFrame(rs_rows).to_csv(C.OUT / "V1_RS_BY_BIN.csv", index=False)
    np.savez_compressed(C.OUT / "V1_SERIES.npz", **{f"{c}__{k}": v for c, d in series.items() for k, v in d.items()})
    decide_v1(pd.DataFrame(rows))
    C.write_manifest("V1", dict(cases=cases, variants=variants, primary_variant=PRIMARY_VARIANT, criteria=CRIT),
                     ["V1_OBSERVABLES.csv", "V1_RS_BY_BIN.csv", "V1_SERIES.npz", "V1_DECISION.json"])


def decide_v1(df):
    """Pre-registered: primary variant (depth 3, slab) must pass on every route; only allowed switch is slab -> halfspace."""
    far = df[df.bin.isin(["3.0-6.0", "6.0-99.0"])]
    def per_route(tag):
        out = {}
        for case, g in far[far.variant == tag].groupby("case"):
            los = far[(far.case == case) & (far.variant == "d0_slab")]
            w = g.n.values
            rms = float(np.sqrt(np.sum(w * g.s_res_rms.values ** 2) / w.sum()))
            slow = float(np.sqrt(np.sum(w * g.s_slow_rms.values ** 2) / w.sum()))
            los_rms = float(np.sqrt(np.sum(los.n.values * los.s_res_rms.values ** 2) / los.n.values.sum()))
            tap = float(np.sum(w * g.tap_agree.values) / w.sum())
            red = 1 - rms / los_rms
            ok = (rms <= CRIT["far_rms_max"] or red >= CRIT["reduction_min"]) and slow <= CRIT["far_slow_rms_max"] and tap >= CRIT["tap_agree_min"]
            approx = red >= CRIT["approx_reduction_min"]
            out[case] = dict(far_rms=rms, far_slow_rms=slow, los_far_rms=los_rms, reduction=red, tap_agree=tap, PASS=bool(ok), APPROX=bool(approx))
        return out
    res = {tag: per_route(tag) for tag in sorted(df.variant.unique()) if tag != "d0_slab"}
    chosen, status = None, "FAIL"
    for tag in ("d3_slab", "d3_halfspace"):
        if tag in res and res[tag] and all(v["PASS"] for v in res[tag].values()):
            chosen, status = tag, "PASS"
            break
    if chosen is None:
        for tag in ("d3_slab", "d3_halfspace"):
            if tag in res and res[tag] and all(v["APPROX"] for v in res[tag].values()):
                chosen, status = tag, "APPROXIMATE"
                break
    (C.OUT / "V1_DECISION.json").write_text(json.dumps(dict(status=status, chosen_variant=chosen, criteria=CRIT, per_variant=res), indent=1))
    log("V1 decision", status=status, chosen=chosen)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["V0", "V1"], required=True)
    ap.add_argument("--cases", default="all", choices=["all", "primary"])
    ap.add_argument("--variants", default="all", choices=["all", "primary"])
    a = ap.parse_args()
    if a.stage == "V0":
        raise SystemExit(0 if stage_v0() else 1)
    if json.loads((C.OUT / "V0_GATE.json").read_text())["status"] != "PASS":
        raise SystemExit("V0 gate not passed")
    cases = list(C.CASES) if a.cases == "all" else list(C.PRIMARY)
    variants = VARIANTS if a.variants == "all" else [PRIMARY_VARIANT]
    stage_v1(cases, variants)
