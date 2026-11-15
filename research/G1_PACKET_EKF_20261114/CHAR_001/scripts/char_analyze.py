"""G1-CHAR-001 steps C1-C7 on the extracted per-pose errors (SPEC_KO.md).

Usage: python -I char_analyze.py --errors <dir with ERRORS_*.npz> --gt1 <G-T1 root> --blockc <BLOCK_C root> --out <dir>
"""
import argparse
import hashlib
import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy import optimize, stats
from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score
from sklearn.mixture import GaussianMixture

warnings.filterwarnings("ignore", category=RuntimeWarning)
NEW = ("G-T1_A", "G-T1_B", "G-T1_C")
OLD = ("R2_aA_m0", "R2_aA_m45", "R2_aB_m0", "R4_aA_m0", "R4_aB_m0", "R5_aA_m0", "R5_aB_m0")
FIT_SETS = {"P-A_TEACH", "P-A_PRIME", "P-B", "C1", "C2", "C3", "C4", "R2", "R4", "R5"}
PATH_SETS = {"P-A_PRIME", "P-B", "C1", "C2", "C3", "C4", "R2", "R4", "R5"}
OBJ = {-1: "none", 2: "ceiling", 1: "floor", 3: "end_x_min", 4: "end_x_max", 5: "wall_y_neg", 6: "wall_y_pos",
       12: "multi2", 13: "multi3"}
SEED = 20261115
GAUSS = dict(p2=0.0455, p3=0.0027, q95_q68=1.96 / 0.994, q99_q95=2.576 / 1.96)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(errors):
    data = {}
    for case in NEW + OLD:
        z = np.load(errors / f"ERRORS_{case}.npz", allow_pickle=False)
        data[case] = {k: z[k] for k in z.files}
        g = data[case]["g_psi"]
        data[case]["e_psi"] = data[case]["e_s"] / np.where(np.abs(g) > 1e-12, g, np.nan)
    return data


def thin(z, dist=0.25, turn=20.0):
    """Keep one pose per `dist` m of travel or `turn` deg of rotation, within each fit set, in pose order."""
    keep = []
    for name in sorted(set(z["set"]) & FIT_SETS):
        ids = np.flatnonzero(z["set"] == name)
        last = None
        for i in ids:
            if last is None:
                keep.append(i)
                last = i
                continue
            step = np.hypot(z["x"][i] - z["x"][last], z["y"][i] - z["y"][last])
            rot = abs((z["yaw"][i] - z["yaw"][last] + 180) % 360 - 180)
            if step >= dist or rot >= turn:
                keep.append(i)
                last = i
    return np.array(keep, int)


def robust_scale(v):
    return 1.4826 * np.median(np.abs(v - np.median(v)))


def standardize(e, d):
    """z = (e - median_bin) / MAD_bin over 1 m distance bins (bins with <15 samples merge to the pooled scale)."""
    z = np.empty_like(e)
    pooled = robust_scale(e)
    b = np.floor(d).astype(int)
    for k in np.unique(b):
        m = b == k
        sc = robust_scale(e[m]) if m.sum() >= 15 else pooled
        z[m] = (e[m] - (np.median(e[m]) if m.sum() >= 15 else np.median(e))) / max(sc, 1e-9)
    return z


def tails(z):
    a = np.abs(z - np.median(z))
    q = lambda p: float(np.quantile(a, p))
    return dict(p_gt2=float(np.mean(a > 2)), p_gt3=float(np.mean(a > 3)),
                q95_q68=q(.95) / max(q(.68), 1e-12), q99_q95=q(.99) / max(q(.95), 1e-12), gauss=GAUSS)


def fit_shapes(v):
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    n = len(v)
    out = {}
    mu, sd = v.mean(), v.std()
    out["gauss"] = dict(ll=float(stats.norm.logpdf(v, mu, sd).sum()), k=2, mu=float(mu), sigma=float(sd))
    loc, b = stats.laplace.fit(v)
    out["laplace"] = dict(ll=float(stats.laplace.logpdf(v, loc, b).sum()), k=2, loc=float(loc), b=float(b))
    nu, loc, sc = stats.t.fit(v)
    out["student_t"] = dict(ll=float(stats.t.logpdf(v, nu, loc, sc).sum()), k=3, nu=float(nu), loc=float(loc),
                            scale=float(sc))
    for k in (1, 2, 3, 4):
        g = GaussianMixture(k, n_init=5, random_state=SEED, reg_covar=1e-8).fit(v[:, None])
        order = np.argsort(g.covariances_.ravel())
        out[f"gmm{k}"] = dict(ll=float(g.score(v[:, None]) * n), k=3 * k - 1,
                              weights=g.weights_[order].tolist(), means=g.means_.ravel()[order].tolist(),
                              sigmas=np.sqrt(g.covariances_.ravel()[order]).tolist())
    for m in out.values():
        m["bic"] = float(-2 * m["ll"] + m["k"] * np.log(n))
    best = min(out, key=lambda m: out[m]["bic"])
    best_gmm = min((m for m in out if m.startswith("gmm")), key=lambda m: out[m]["bic"])
    return dict(n=n, models=out, best=best, best_gmm_k=int(best_gmm[3:]))


def c1_shape(data):
    res = {}
    pools = {"NEW": [], "OLD_m0": []}
    for case, z in data.items():
        keep = thin(z)
        row = {"n_all": int(len(z["e_s"])), "n_thin": int(len(keep)), "n_thin_coarse": int(len(thin(z, .5, 40.)))}
        for var in ("e_s", "e_r_abs", "e_psi"):
            v = z[var][keep]
            ok = np.isfinite(v)
            if var == "e_psi":
                ok &= np.abs(z["g_psi"][keep]) >= np.quantile(np.abs(z["g_psi"][keep]), .2)
            zz = standardize(v[ok], z["d"][keep][ok])
            row[var] = dict(raw=dict(mean=float(v[ok].mean()), std=float(v[ok].std()),
                                     mad_scale=float(robust_scale(v[ok])), **tails(v[ok] / max(robust_scale(v[ok]), 1e-12)),
                                     shapes=fit_shapes(v[ok])),
                            dist_standardized=dict(**tails(zz), shapes=fit_shapes(zz)))
            # coarse thinning robustness of the tail metric
            kc = thin(z, .5, 40.)
            vc = z[var][kc]
            okc = np.isfinite(vc)
            if var == "e_psi":
                okc &= np.abs(z["g_psi"][kc]) >= np.quantile(np.abs(z["g_psi"][kc]), .2)
            row[var]["dist_standardized_coarse"] = dict(**tails(standardize(vc[okc], z["d"][kc][okc])),
                                                        best=fit_shapes(standardize(vc[okc], z["d"][kc][okc]))["best"])
        res[case] = row
        if case in NEW:
            pools["NEW"].append(standardize(z["e_s"][keep], z["d"][keep]))
        elif case.endswith("m0"):
            pools["OLD_m0"].append(standardize(z["e_s"][keep], z["d"][keep]))
    res["pooled_e_s_standardized"] = {k: dict(**tails(np.concatenate(v)), shapes=fit_shapes(np.concatenate(v)))
                                      for k, v in pools.items()}
    return res


def cls_stats(e, labels):
    out = {}
    for lab in np.unique(labels):
        m = labels == lab
        if m.sum() < 10:
            continue
        v = e[m]
        out[str(lab)] = dict(n=int(m.sum()), mean=float(v.mean()), std=float(v.std()), rms=float(np.sqrt(np.mean(v**2))),
                             mad_scale=float(robust_scale(v)), p_abs_gt_0p3=float(np.mean(np.abs(v) > .3)),
                             q95_abs=float(np.quantile(np.abs(v), .95)))
    return out


def classes(z, case):
    dt = z["dtap"]
    c = dict(dtap=np.where(dt == 0, "0", np.where(dt == -1, "-1", np.where(dt == 1, "+1",
                                                                       np.where(dt < -1, "<=-2", ">=+2")))),
             d_bin=np.char.add("d", np.floor(z["d"]).astype(int).astype(str)),
             elev_bin=np.char.add("el", (np.floor(z["elev"] / 10) * 10).astype(int).astype(str)),
             rel_bearing_bin=np.char.add("rb", (np.floor(z["rel_bearing"] / 30) * 30).astype(int).astype(str)),
             motion=z["motion"].astype(str),
             g_low=np.where(np.abs(z["g_psi"]) < np.quantile(np.abs(z["g_psi"]), .2), "low20", "rest"))
    if "near_dom" in z:
        has = z["near_has"]
        c["near_dom"] = np.where(has, np.vectorize(lambda k: OBJ.get(int(k), str(k)))(z["near_dom"]), "no_near_export")
        r = z["near_ratio_db"]
        c["near_ratio_bin"] = np.where(~has, "no_near_export",
                                       np.where(~np.isfinite(r), "no_near_path",
                                                np.char.add("nr", (np.floor(np.nan_to_num(r, neginf=-99) / 5) * 5)
                                                            .astype(int).astype(str))))
    return c


def c2_causes(data):
    res = {}
    for case, z in data.items():
        keep = thin(z)
        c = classes(z, case)
        e = z["e_s"]
        var_tot = e.var()
        same, shift = z["e_s_same"], e - z["e_s_same"]
        row = dict(decomposition=dict(var_total=float(var_tot), var_same_tap=float(same.var()),
                                      var_shift=float(shift.var()), cov2=float(2 * np.cov(same, shift)[0, 1]),
                                      frac_dtap0=float(np.mean(z["dtap"] == 0)),
                                      var_e_s_when_dtap0=float(e[z["dtap"] == 0].var()),
                                      var_e_s_when_dtap_ne0=float(e[z["dtap"] != 0].var())))
        row["by_class_e_s"] = {k: cls_stats(e, v) for k, v in c.items()}
        row["dtap_pmf"] = {str(k): float(np.mean(z["dtap"] == k)) for k in np.unique(z["dtap"])}
        row["by_class_e_r_abs"] = {k: cls_stats(z["e_r_abs"], v) for k, v in c.items() if k in ("dtap", "d_bin", "near_dom",
                                                                                        "motion", "elev_bin")}
        # GMM component vs physical class on thinned standardized e_s
        zz = standardize(e[keep], z["d"][keep])
        k = fit_shapes(zz)["best_gmm_k"]
        assign = None
        if k > 1:
            g = GaussianMixture(k, n_init=5, random_state=SEED).fit(zz[:, None])
            assign = g.predict(zz[:, None])
        corr = {}
        for name in ("dtap", "near_dom", "motion", "d_bin", "rel_bearing_bin", "g_low"):
            if name in c and assign is not None:
                lab = c[name][keep]
                m = lab != "no_near_export"
                corr[name] = dict(ari=float(adjusted_rand_score(lab[m], assign[m])),
                                  nmi=float(normalized_mutual_info_score(lab[m], assign[m])), n=int(m.sum()))
        row["gmm_vs_class"] = dict(k=k, association=corr)
        res[case] = row
    return res


def window_var(along, e, width):
    b = np.floor(along / width).astype(int)
    means = np.array([e[b == k].mean() for k in np.unique(b)])
    counts = np.array([(b == k).sum() for k in np.unique(b)])
    return b, means, counts


def nested(along, e):
    """Nested window decomposition of var(e) about the case mean: 5 m / 1 m / 0.25 m / residual."""
    tot = float(np.mean((e - e.mean()) ** 2))
    parts, prev = {}, np.full(len(e), e.mean())
    for w in (5.0, 1.0, 0.25):
        b = np.floor(along / w).astype(int)
        cur = np.empty(len(e))
        for k in np.unique(b):
            cur[b == k] = e[b == k].mean()
        parts[f"{w}m"] = float(np.mean((cur - prev) ** 2))
        prev = cur
    parts["residual"] = float(np.mean((e - prev) ** 2))
    return dict(var_total=tot, mean_sq=float(e.mean() ** 2), **parts,
                share={k: v / tot for k, v in parts.items()})


def revisit(case, z, gt1_root):
    samples = json.load(open(gt1_root / "poses" / case / "SAMPLES.json"))
    e = z["e_s"]
    er = z["e_r"]
    out = {}
    tr = {}
    for r in samples:
        if r["set"] in ("P-A_TEACH", "P-A_REPEAT") and r["selected_5pt"] is True:
            tr.setdefault((r["station_id"], r["planned_rel_deg"]), {})[r["set"]] = r["pose_id"]
    pairs = [(v["P-A_TEACH"], v["P-A_REPEAT"]) for v in tr.values() if len(v) == 2]
    a, b = np.array(pairs).T
    out["TEACH_REPEAT"] = dict(n=len(a), rho_e_s=float(np.corrcoef(e[a], e[b])[0, 1]),
                               rho_e_r=float(np.corrcoef(er[a], er[b])[0, 1]),
                               rms_diff_e_s=float(np.sqrt(np.mean((e[a] - e[b]) ** 2))), rms_e_s=float(np.sqrt(np.mean(e[a] ** 2))))
    by = {}
    for r in samples:
        if r["set"] in ("P-D", "P-E"):
            key = r["set"] if r["set"] == "P-E" else f"P-D_{float(r['offset_m']):.3f}"
            by.setdefault(key, []).append((r["source_pose_id"], r["pose_id"]))
    for key, p in sorted(by.items()):
        a, b = np.array(p).T
        out[key] = dict(n=len(a), rho_e_s=float(np.corrcoef(e[a], e[b])[0, 1]),
                        rho_e_r=float(np.corrcoef(er[a], er[b])[0, 1]),
                        rms_diff_e_s=float(np.sqrt(np.mean((e[a] - e[b]) ** 2))))
    return out


def c3_scales(data, gt1_root):
    res = {}
    for case, z in data.items():
        row = {}
        for var in ("e_s", "e_r", "e_psi"):
            per = {}
            for name in sorted(set(z["set"]) & PATH_SETS):
                m = (z["set"] == name) & np.isfinite(z[var])
                if var == "e_psi":
                    m &= np.abs(z["g_psi"]) >= np.quantile(np.abs(z["g_psi"]), .2)
                if m.sum() < 30:
                    continue
                al = z["along"][m]
                per[name] = nested(al - al.min(), z[var][m])
            tot = sum(p["var_total"] * 1 for p in per.values())
            row[var] = dict(per_set=per, mean_share={k: float(np.mean([p["share"][k] for p in per.values()]))
                                                       for k in ("5.0m", "1.0m", "0.25m", "residual")})
        # station sweeps (yaw) on TEACH
        m = z["set"] == "P-A_TEACH"
        if m.any():
            st = z["station"][m]
            e = z["e_s"][m]
            means = {s: e[st == s].mean() for s in np.unique(st)}
            within = float(np.mean([e[st == s].var() for s in means]))
            between = float(np.var(list(means.values())))
            row["station_sweeps_e_s"] = dict(stations=len(means), within_station_yaw_var=within,
                                             between_station_mean_var=between,
                                             within_share=within / (within + between))
            row["revisit"] = revisit(case, z, gt1_root)
        res[case] = row
    return res


def boot_std(v, n=400, rng=None):
    if len(v) < 10:
        return None
    idx = rng.integers(0, len(v), (n, len(v)))
    s = v[idx].std(axis=1)
    return [float(np.quantile(s, .025)), float(np.quantile(s, .975))]


def c4_geometry(data):
    rng = np.random.default_rng(SEED)
    res = {}
    for case, z in data.items():
        keep = thin(z)
        row = {}
        for var in ("e_s", "e_r_abs"):
            v, d = z[var][keep], z["d"][keep]
            bins = {}
            for k in np.unique(np.floor(d).astype(int)):
                m = np.floor(d).astype(int) == k
                if m.sum() >= 10:
                    bins[f"{k}"] = dict(n=int(m.sum()), mean=float(v[m].mean()), std=float(v[m].std()),
                                        mad_scale=float(robust_scale(v[m])), std_ci95=boot_std(v[m], rng=rng))
            ks = np.array([int(k) + .5 for k in bins])
            ss = np.array([b["std"] for b in bins.values()])
            ns = np.array([b["n"] for b in bins.values()])
            slope = np.polyfit(np.log(ks), np.log(ss), 1, w=np.sqrt(ns)) if len(ks) >= 3 else [np.nan, np.nan]
            row[var] = dict(by_distance=bins, loglog_slope=float(slope[0]), loglog_intercept=float(slope[1]),
                            by_elev=cls_stats(v, classes(z, case)["elev_bin"][keep]),
                            by_rel_bearing=cls_stats(v, classes(z, case)["rel_bearing_bin"][keep]))
        db = np.floor(z["d"]).astype(int)
        row["dtap_by_distance_all_poses"] = {f"{k}": dict(n=int((db == k).sum()), p_dtap_ne0=float(np.mean(z["dtap"][db == k] != 0)),
                                                          p_dtap_ge2=float(np.mean(z["dtap"][db == k] >= 2)))
                                             for k in np.unique(db) if (db == k).sum() >= 20}
        # GMM wide-component weight by distance (standardized by pooled scale only, so the weight can move with d)
        v, d = z["e_s"][keep], z["d"][keep]
        g = GaussianMixture(2, n_init=5, random_state=SEED).fit(v[:, None])
        wide = int(np.argmax(g.covariances_.ravel()))
        post = g.predict_proba(v[:, None])[:, wide]
        row["gmm2_raw"] = dict(weights=g.weights_.tolist(), means=g.means_.ravel().tolist(),
                               sigmas=np.sqrt(g.covariances_.ravel()).tolist(), wide=wide,
                               wide_weight_by_distance={f"{k}": float(post[np.floor(d).astype(int) == k].mean())
                                                        for k in np.unique(np.floor(d).astype(int))
                                                        if (np.floor(d).astype(int) == k).sum() >= 10})
        res[case] = row
    return res


# ---------- C5 LOAO representations ----------
def nll_gauss_d(p, e, ld):
    mu, a, b = p
    s = np.exp(a + b * ld)
    return -stats.norm.logpdf(e, mu, s).sum()


def nll_t_d(p, e, ld):
    mu, a, b, lnu = p
    return -stats.t.logpdf(e, np.exp(lnu), mu, np.exp(a + b * ld)).sum()


def mix_parts(p, ld):
    m1, m2, a1, a2, b, c0, c1 = p
    w = 1 / (1 + np.exp(-(c0 + c1 * ld)))
    return w, m1, m2, np.exp(a1 + b * ld), np.exp(a2 + b * ld)


def nll_mix_d(p, e, ld):
    w, m1, m2, s1, s2 = mix_parts(p, ld)
    return -np.log(w * stats.norm.pdf(e, m1, s1) + (1 - w) * stats.norm.pdf(e, m2, s2) + 1e-300).sum()


def fit_reps(e, d, kstar):
    ld = np.log(d)
    reps = {}
    reps["R0_gauss_const"] = ("gauss", (e.mean(), e.std()))
    p = optimize.minimize(nll_gauss_d, [e.mean(), np.log(e.std()), 0], args=(e, ld), method="Nelder-Mead",
                          options=dict(maxiter=4000)).x
    reps["R1_gauss_sigma_d"] = ("gauss_d", p)
    best = None
    for lnu in (np.log(1.5), np.log(3), np.log(8)):
        r = optimize.minimize(nll_t_d, [np.median(e), np.log(robust_scale(e)), 0, lnu], args=(e, ld),
                              method="Nelder-Mead", options=dict(maxiter=6000))
        if best is None or r.fun < best.fun:
            best = r
    reps["R2_student_t_scale_d"] = ("t_d", best.x)
    g = GaussianMixture(max(kstar, 2), n_init=5, random_state=SEED).fit(e[:, None])
    reps["R3_gmm_const"] = ("gmm", g)
    sc = robust_scale(e)
    best = None
    for c0 in (-1.0, 1.0):
        r = optimize.minimize(nll_mix_d, [np.median(e), e.mean(), np.log(sc), np.log(4 * sc), 0, c0, 0],
                              args=(e, ld), method="Nelder-Mead", options=dict(maxiter=12000, maxfev=12000))
        if best is None or r.fun < best.fun:
            best = r
    reps["R4_gsum_weights_scale_d"] = ("mix_d", best.x)
    return reps


def pit(rep, e, d):
    kind, p = rep
    ld = np.log(d)
    if kind == "gauss":
        return stats.norm.cdf(e, p[0], p[1])
    if kind == "gauss_d":
        return stats.norm.cdf(e, p[0], np.exp(p[1] + p[2] * ld))
    if kind == "t_d":
        return stats.t.cdf(e, np.exp(p[3]), p[0], np.exp(p[1] + p[2] * ld))
    if kind == "gmm":
        w, m, s = p.weights_, p.means_.ravel(), np.sqrt(p.covariances_.ravel())
        return (w[None] * stats.norm.cdf((e[:, None] - m[None]) / s[None])).sum(axis=1)
    w, m1, m2, s1, s2 = mix_parts(p, ld)
    return w * stats.norm.cdf(e, m1, s1) + (1 - w) * stats.norm.cdf(e, m2, s2)


def describe_rep(rep):
    kind, p = rep
    if kind == "gmm":
        return dict(weights=p.weights_.tolist(), means=p.means_.ravel().tolist(),
                    sigmas=np.sqrt(p.covariances_.ravel()).tolist())
    out = dict(params=[float(x) for x in p])
    if kind == "t_d":
        out["nu"] = float(np.exp(p[3]))
    return out


def loao(data, cases, var, kstar):
    res = {}
    for held in cases:
        train = [c for c in cases if c != held]
        ks = {c: thin(data[c]) for c in cases}
        e_tr = np.concatenate([data[c][var][ks[c]] for c in train])
        d_tr = np.concatenate([data[c]["d"][ks[c]] for c in train])
        reps = fit_reps(e_tr, d_tr, kstar)
        e_te, d_te = data[held][var][ks[held]], data[held]["d"][ks[held]]
        row = {}
        for name, rep in reps.items():
            u = pit(rep, e_te, d_te)
            u_tr = pit(rep, e_tr, d_tr)
            row[name] = dict(coverage95_heldout=float(np.mean((u > .025) & (u < .975))),
                             coverage95_train=float(np.mean((u_tr > .025) & (u_tr < .975))),
                             upper_tail_heldout=float(np.mean(u >= .975)), lower_tail_heldout=float(np.mean(u <= .025)),
                             pit_ks_heldout=float(stats.kstest(u, "uniform").statistic),
                             fit=describe_rep(rep))
        res[held] = dict(train=train, n_heldout=int(len(e_te)), reps=row)
    names = list(next(iter(res.values()))["reps"])
    res["min_heldout_coverage"] = {n: float(min(res[h]["reps"][n]["coverage95_heldout"] for h in cases)) for n in names}
    return res


def c5_transfer(data, c1):
    out = {}
    for var in ("e_s", "e_r_abs"):
        k = int(np.median([c1[c][var]["raw"]["shapes"]["best_gmm_k"] for c in NEW]))
        out[f"NEW_{var}"] = loao(data, NEW, var, k)
        out[f"OLD_m0_{var}"] = loao(data, ("R2_aA_m0", "R2_aB_m0"), var, k)
        out[f"OLD_m0_R5_{var}"] = loao(data, ("R5_aA_m0", "R5_aB_m0"), var, k)
    return out


def c6_heading(data):
    res = {}
    for case, z in data.items():
        g = np.abs(z["g_psi"])
        low = g < np.quantile(g, .2)
        ep = z["e_psi"]
        keep = thin(z)
        okk = keep[~low[keep]]
        row = dict(g_abs_median_per_deg=float(np.median(g)), g_abs_q20_per_deg=float(np.quantile(g, .2)),
                   e_psi_thin_rest=dict(n=int(len(okk)), median_abs=float(np.median(np.abs(ep[okk]))),
                                        q68_abs=float(np.quantile(np.abs(ep[okk]), .68)),
                                        q95_abs=float(np.quantile(np.abs(ep[okk]), .95)),
                                        mad_scale=float(robust_scale(ep[okk]))),
                   e_psi_thin_low20=dict(median_abs=float(np.median(np.abs(ep[keep[low[keep]]]))),
                                         q95_abs=float(np.quantile(np.abs(ep[keep[low[keep]]]), .95))))
        wm = []
        for name in sorted(set(z["set"]) & PATH_SETS):
            m = (z["set"] == name) & ~low
            if m.sum() < 30:
                continue
            al = z["along"][m]
            b = np.floor((al - al.min()) / 5.0).astype(int)
            wm += [np.mean(ep[m][b == k]) for k in np.unique(b) if (b == k).sum() >= 5]
        if wm:
            row["e_psi_5m_window_mean"] = dict(n=len(wm), median_abs=float(np.median(np.abs(wm))),
                                               q90_abs=float(np.quantile(np.abs(wm), .9)), max_abs=float(np.max(np.abs(wm))))
        res[case] = row
    return res


def c7_compare(data, blockc_root):
    a, b = data["R2_aA_m0"], data["R2_aA_m45"]
    same = np.allclose(a["x"], b["x"]) and np.allclose(a["yaw"], b["yaw"])
    pose = dict(
        same_poses=bool(same),
        e_s_std=dict(m0=float(a["e_s"].std()), m45=float(b["e_s"].std())),
        g_abs_median=dict(m0=float(np.median(np.abs(a["g_psi"]))), m45=float(np.median(np.abs(b["g_psi"])))),
        e_psi_median_abs=dict(m0=float(np.nanmedian(np.abs(a["e_psi"]))), m45=float(np.nanmedian(np.abs(b["e_psi"])))),
        e_psi_q95_abs=dict(m0=float(np.nanquantile(np.abs(a["e_psi"]), .95)),
                           m45=float(np.nanquantile(np.abs(b["e_psi"]), .95))),
        frac_pose_m45_smaller_abs_e_psi=float(np.mean(np.abs(b["e_psi"]) < np.abs(a["e_psi"]))),
        frac_pose_m45_larger_g=float(np.mean(np.abs(b["g_psi"]) > np.abs(a["g_psi"]))),
        e_r_std=dict(m0=float(a["e_r"].std()), m45=float(b["e_r"].std())))
    # existing BLOCK_C EKF results (prior pipeline): pair m0 vs m45 by identical configuration
    import csv
    rows = {}
    for m in ("m0", "m45"):
        p = blockc_root / "INPUTS" / f"results_R2_aA_{m}.csv"
        for r in csv.DictReader(open(p)):
            key = (r["baseline"], r["filter"], r["drift_name"], r["snr_db"], r["seed"], r["period_s"], r["lateral"])
            rows.setdefault(key, {})[m] = r
    table = {}
    for key, v in rows.items():
        if len(v) != 2 or v["m0"]["error"] or v["m45"]["error"]:
            continue
        t = table.setdefault(f"{key[0]}|{key[1]}|{key[2]}", dict(d=[], m0=[], m45=[], n0=[], n45=[]))
        h0, h45 = float(v["m0"]["heading_rmse_deg"]), float(v["m45"]["heading_rmse_deg"])
        t["m0"].append(h0)
        t["m45"].append(h45)
        t["d"].append(h45 - h0)
        for k, m in (("n0", "m0"), ("n45", "m45")):
            t[k].append(float(v[m]["nees_mean"]) if v[m]["nees_mean"] else np.nan)
    ekf = {k: dict(n=len(t["d"]), heading_rmse_median_m0=float(np.median(t["m0"])),
                   heading_rmse_median_m45=float(np.median(t["m45"])), median_diff_m45_minus_m0=float(np.median(t["d"])),
                   frac_m45_better=float(np.mean(np.array(t["d"]) < 0)),
                   nees_mean_median_m0=float(np.nanmedian(t["n0"])), nees_mean_median_m45=float(np.nanmedian(t["n45"])))
           for k, t in sorted(table.items())}
    rt = {}
    for group, cases in (("NEW_G-T1", NEW), ("OLD_m0", tuple(c for c in OLD if c.endswith("m0")))):
        rt[group] = {c: dict(e_s_std=float(data[c]["e_s"].std()), e_s_mean=float(data[c]["e_s"].mean()),
                             e_r_std=float(data[c]["e_r"].std()), frac_dtap0=float(np.mean(data[c]["dtap"] == 0)),
                             g_abs_median=float(np.median(np.abs(data[c]["g_psi"]))),
                             d_range=[float(data[c]["d"].min()), float(data[c]["d"].max())]) for c in cases}
    return dict(mount_R2_aA_pose_level=pose, mount_R2_aA_prior_pipeline_ekf=ekf, rt_compare=rt)


def to_json(o):
    if isinstance(o, dict):
        return {str(k): to_json(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [to_json(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    return o


def main():
    ap = argparse.ArgumentParser()
    for k in ("errors", "gt1", "blockc", "out"):
        ap.add_argument("--" + k, type=Path, required=True)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    data = load(a.errors)
    outputs = {}
    c1 = c1_shape(data)
    steps = [("C1_SHAPE", lambda: c1), ("C2_CAUSES", lambda: c2_causes(data)),
             ("C3_SCALES", lambda: c3_scales(data, a.gt1)), ("C4_GEOMETRY", lambda: c4_geometry(data)),
             ("C5_TRANSFER", lambda: c5_transfer(data, c1)), ("C6_HEADING", lambda: c6_heading(data)),
             ("C7_COMPARE", lambda: c7_compare(data, a.blockc))]
    for name, fn in steps:
        p = a.out / f"{name}.json"
        json.dump(to_json(fn()), open(p, "w"), indent=1)
        outputs[p.name] = sha(p)
        print(name, "done", flush=True)
    json.dump(dict(question_id="G1-CHAR-001", step="analyze", started_utc=started,
                   finished_utc=datetime.now(timezone.utc).isoformat(), command=sys.argv,
                   script_sha256=sha(__file__), inputs={p.name: sha(p) for p in sorted(a.errors.glob("ERRORS_*.npz"))},
                   outputs=outputs, seed=SEED), open(a.out / "ANALYZE_MANIFEST.json", "w"), indent=1)


if __name__ == "__main__":
    main()
