"""G1-CHAR-002: learn heading-conditioned S / e_s / e_r models on G-T1 TEACH+REPEAT, evaluate per trajectory.

Usage: python char2_fit_eval.py --errors <dir with CHAR-001 ERRORS_*.npz> --src <qclean_uwb src> --banks <dir> --out <dir>
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy import optimize, stats

TRAIN_SETS = ("P-A_TEACH", "P-A_REPEAT")
EVAL1_SETS = ("P-A_PRIME", "P-B", "C1", "C2", "C3", "C4")
NEW = ("G-T1_A", "G-T1_B", "G-T1_C")
OLD = ("R2_aA_m0", "R2_aB_m0", "R4_aA_m0", "R4_aB_m0", "R5_aA_m0", "R5_aB_m0")
FOLD = 180.0  # set by --fold; 180 = pre-registered, 360 = amendment A1 (fold check failed)
NB = 12
BIN_W = 15.0
MIN_BIN = 30


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def psi_f(z):
    return np.mod(z["rel_bearing"], FOLD)


def bins(pf):
    return np.minimum((pf // BIN_W).astype(int), NB - 1)


def load(errors):
    out = {}
    for c in NEW + OLD:
        z = np.load(errors / f"ERRORS_{c}.npz", allow_pickle=False)
        out[c] = {k: z[k] for k in z.files}
        out[c]["pf"] = psi_f(out[c])
        out[c]["b"] = bins(out[c]["pf"])
        g = out[c]["g_psi"]
        out[c]["e_psi"] = out[c]["e_s"] / np.where(np.abs(g) > 1e-12, g, np.nan)
    return out


# ---------- models ----------
class Model:
    """Location/scale family. Per-bin terms use NB+1 slots; bins with <MIN_BIN training rows share the last slot."""

    def __init__(self, name, dist, loc_bins, loc_d, scale_bins, zero_loc, const=False):
        self.name, self.dist, self.loc_bins, self.loc_d = name, dist, loc_bins, loc_d
        self.scale_bins, self.zero_loc, self.const = scale_bins, zero_loc, const

    def _sizes(self):
        nl = 0 if self.zero_loc else (NB + 1 if self.loc_bins else 1)
        nc = int(self.loc_d and not self.zero_loc)
        ns = NB + 1 if self.scale_bins else 1
        nk = 0 if self.const else 1
        return nl, nc, ns, nk, int(self.dist == "t")

    def n_params(self):
        return sum(self._sizes())

    def unpack(self, p):
        nl, nc, ns, nk, nn = self._sizes()
        i = 0
        loc = p[i:i + nl] if nl else np.zeros(1); i += nl
        c = p[i] if nc else 0.0; i += nc
        ls = p[i:i + ns]; i += ns
        k = p[i] if nk else 0.0; i += nk
        lnu = p[i] if nn else None
        return dict(loc=np.asarray(loc), c=c, ls=np.asarray(ls), k=k, lnu=lnu)

    def slot(self, b):
        return np.where(self.bin_ok[b], b, NB)

    def locscale(self, q, b, d):
        s = self.slot(b)
        loc = (q["loc"][s] if len(q["loc"]) > 1 else q["loc"][0]) + q["c"] * (d - 4.0)
        ls = q["ls"][s] if len(q["ls"]) > 1 else q["ls"][0]
        return loc, np.exp(ls + q["k"] * np.log(d / 4.0))

    def _nll(self, p, e, b, d):
        q = self.unpack(p)
        loc, sc = self.locscale(q, b, d)
        if self.dist == "t":
            return -stats.t.logpdf(e, np.exp(q["lnu"]), loc, sc).sum()
        return -stats.norm.logpdf(e, loc, sc).sum()

    def fit(self, e, b, d):
        self.bin_ok = np.array([(b == j).sum() >= MIN_BIN for j in range(NB)])
        nl, nc, ns, nk, nn = self._sizes()
        sc0 = np.log(1.4826 * np.median(np.abs(e - np.median(e))) + 1e-6)
        p0 = np.r_[np.full(nl, np.median(e)), np.zeros(nc), np.full(ns, sc0), np.zeros(nk), np.full(nn, np.log(3.0))]
        best = None
        for start in (p0, np.r_[np.full(nl, np.median(e)), np.zeros(nc), np.full(ns, np.log(e.std() + 1e-6)),
                               np.zeros(nk), np.full(nn, np.log(10.0))]):
            r = optimize.minimize(self._nll, start, args=(e, b, d), method="L-BFGS-B")
            if best is None or r.fun < best.fun:
                best = r
        self.p, self.q = best.x, self.unpack(best.x)
        self.success, self.train_nll = bool(best.success), float(best.fun)
        return self

    def cdf(self, e, b, d):
        loc, sc = self.locscale(self.q, b, d)
        if self.dist == "t":
            return stats.t.cdf(e, np.exp(self.q["lnu"]), loc, sc)
        return stats.norm.cdf(e, loc, sc)

    def logpdf(self, e, b, d):
        loc, sc = self.locscale(self.q, b, d)
        if self.dist == "t":
            return stats.t.logpdf(e, np.exp(self.q["lnu"]), loc, sc)
        return stats.norm.logpdf(e, loc, sc)

    def halfwidth95(self, b, d):
        _, sc = self.locscale(self.q, b, d)
        z = stats.t.ppf(0.975, np.exp(self.q["lnu"])) if self.dist == "t" else 1.959964
        return z * sc

    def describe(self):
        return dict(dist=self.dist, n_params=self.n_params(), success=self.success, train_nll=self.train_nll,
                    loc=[float(x) for x in self.q["loc"]], loc_slope_per_m=float(self.q["c"]),
                    log_scale=[float(x) for x in self.q["ls"]], k=float(self.q["k"]),
                    nu=None if self.q["lnu"] is None else float(np.exp(self.q["lnu"])),
                    bin_supported=[bool(x) for x in self.bin_ok], note="last slot = pooled thin bins")


def s_models():
    return [Model("S0_gauss_const", "norm", False, False, False, True, const=True),
            Model("S1_gauss_sigma_d", "norm", False, False, False, True),
            Model("S2_gauss_sigma_psi_d", "norm", False, False, True, True),
            Model("S3_t_scale_psi_d", "t", False, False, True, True),
            Model("S4_t_scale_psi_d_mean_psi[G2]", "t", True, False, True, False)]


def r_models():
    return [Model("R0_gauss_const", "norm", False, False, False, False, const=True),
            Model("R1_gauss_mu_d_sigma_d", "norm", False, True, False, False),
            Model("R2_gauss_mu_psi_d_sigma_psi_d", "norm", True, True, True, False),
            Model("R3_t_mu_psi_d_scale_psi_d", "t", True, True, True, False)]


def fit_all(models, e, b, d):
    return [m.fit(e, b, d) for m in models]


def metrics(m, e, b, d):
    dd = d
    u = m.cdf(e, b, dd)
    lp = m.logpdf(e, b, dd)
    inside = (u > .025) & (u < .975)
    return dict(n=int(len(e)), coverage95=float(inside.mean()), upper=float(np.mean(u >= .975)),
                lower=float(np.mean(u <= .025)), pit_ks=float(stats.kstest(u, "uniform").statistic),
                mean_logpdf=float(np.mean(lp))), inside, dd


def evaluate(models, z, idx, var, train_support):
    e, b, d = z[var][idx], z["b"][idx], z["d"][idx]
    ok = np.isfinite(e)
    e, b, d = e[ok], b[ok], d[ok]
    g = np.abs(z["g_psi"][idx][ok])
    extrap = (d > train_support["d_max"]) | ~np.array(train_support["bin_ok"])[b]
    out = {}
    for m in models:
        allm, inside, dd = metrics(m, e, b, d)
        row = dict(all=allm)
        if extrap.any() and (~extrap).any():
            row["in_support"] = metrics(m, e[~extrap], b[~extrap], d[~extrap])[0]
            row["extrapolated"] = metrics(m, e[extrap], b[extrap], d[extrap])[0]
        row["by_psi_bin"] = {f"{int(j * BIN_W)}-{int((j + 1) * BIN_W)}": dict(n=int((b == j).sum()),
                                                                              coverage95=float(inside[b == j].mean()))
                             for j in range(NB) if (b == j).sum() >= 10}
        row["by_distance"] = {lab: dict(n=int(mk.sum()), coverage95=float(inside[mk].mean()))
                              for lab, mk in (("d<4", d < 4), ("4<=d<8", (d >= 4) & (d < 8)), ("d>=8", d >= 8))
                              if mk.sum() >= 10}
        if var == "e_s":
            hw = m.halfwidth95(b, dd)
            ep = np.abs(e) / np.maximum(g, 1e-9)
            row["heading_domain"] = dict(pred_halfwidth95_deg_median=float(np.median(hw / np.maximum(g, 1e-9))),
                                         actual_abs_e_psi_median_deg=float(np.median(ep)),
                                         actual_abs_e_psi_q95_deg=float(np.quantile(ep, .95)),
                                         note="heading 95% coverage equals the s-domain coverage under linearization")
        out[m.name] = row
    out["n_extrapolated"] = int(extrap.sum())
    return out


def oracle(z, idx, var):
    e, b, d = z[var][idx], z["b"][idx], z["d"][idx]
    ok = np.isfinite(e)
    m = (Model("S1_oracle", "norm", False, False, False, True) if var == "e_s"
         else Model("R1_oracle", "norm", False, True, False, False)).fit(e[ok], b[ok], d[ok])
    return metrics(m, e[ok], b[ok], d[ok])[0]


def s_symmetry(data, src, banks_dir):
    """Check the 180-degree folding assumption: g_psi(yaw) vs g_psi(yaw+180) at the training poses."""
    sys.path.insert(0, str(src))
    from qclean_uwb.drivesim import hs_lut as model, observation as obs, pattern_apply as pat
    banks = [pat.Bank(dict(np.load(banks_dir / n, allow_pickle=False))) for n in ("LP_plus45_bank.npz", "LP_minus45_bank.npz")]
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "CHAR_001" / "scripts"))
    from char_mount import sens, synth_los
    from char_extract import o30, s_at
    rows = {}
    for c in NEW:
        z = data[c]
        idx = np.flatnonzero(np.isin(z["set"], TRAIN_SETS))[::4]
        anchor = {"G-T1_A": [7.0, 0, 2.65], "G-T1_B": [9.8, 0, 2.65], "G-T1_C": [3.0, 0, 2.65]}[c]
        delta = np.c_[z["x"][idx], z["y"][idx], np.full(len(idx), 0.45)] - np.array(anchor)
        dist = np.linalg.norm(delta, axis=1)
        u = delta / dist[:, None]
        g0 = sens(model, obs, banks, u, z["yaw"][idx], dist)
        g180 = sens(model, obs, banks, u, z["yaw"][idx] + 180, dist)
        h0 = obs.cir_batch(synth_los(model, banks, u, z["yaw"][idx], dist)[..., 0])
        h1 = obs.cir_batch(synth_los(model, banks, u, z["yaw"][idx] + 180, dist)[..., 0])
        s0, s1 = s_at(h0, o30(h0)), s_at(h1, o30(h1))
        rows[c] = dict(n=int(len(idx)), s_abs_diff_p90=float(np.quantile(np.abs(s0 - s1), .9)),
                       g_abs_diff_p90=float(np.quantile(np.abs(g0 - g180), .9)),
                       g_abs_median=float(np.median(np.abs(g0))))
    return rows


def main():
    ap = argparse.ArgumentParser()
    for k in ("errors", "src", "banks", "out"):
        ap.add_argument("--" + k, type=Path, required=True)
    ap.add_argument("--fold", type=float, default=180.0, choices=(180.0, 360.0))
    a = ap.parse_args()
    global FOLD, NB
    FOLD, NB = a.fold, int(a.fold / BIN_W)
    a.out.mkdir(parents=True, exist_ok=True)
    data = load(a.errors)
    tr = {c: np.flatnonzero(np.isin(data[c]["set"], TRAIN_SETS)) for c in NEW}
    cat = lambda k: np.concatenate([data[c][k][tr[c]] for c in NEW])
    b_tr, d_tr = cat("b"), cat("d")
    support = dict(d_max=float(d_tr.max()), d_min=float(d_tr.min()),
                   bin_counts=[int((b_tr == j).sum()) for j in range(NB)],
                   bin_ok=[bool((b_tr == j).sum() >= MIN_BIN) for j in range(NB)])
    # S: heading information in training data
    g_tr = np.abs(cat("g_psi"))
    s_info = {f"{int(j * BIN_W)}-{int((j + 1) * BIN_W)}": dict(n=int((b_tr == j).sum()),
                                                                g_abs_median=float(np.median(g_tr[b_tr == j])) if (b_tr == j).any() else None)
              for j in range(NB)}
    fits, evals = {}, {}
    for var, maker in (("e_s", s_models), ("e_r_abs", r_models)):
        e_tr = cat(var)
        models = fit_all(maker(), e_tr, b_tr, d_tr)
        fits[var] = {m.name: m.describe() for m in models}
        ev = {}
        for c in NEW:
            z = data[c]
            for sname in EVAL1_SETS:
                idx = np.flatnonzero(z["set"] == sname)
                if len(idx) >= 30:
                    ev[f"EVAL1|{c}|{sname}"] = evaluate(models, z, idx, var, support) | {"oracle_fit_on_eval": oracle(z, idx, var)}
            ev[f"TRAIN|{c}|TEACH+REPEAT"] = evaluate(models, z, tr[c], var, support)
        for c in OLD:
            z = data[c]
            idx = np.arange(len(z["e_s"]))
            ev[f"EVAL2|{c}"] = evaluate(models, z, idx, var, support) | {"oracle_fit_on_eval": oracle(z, idx, var)}
        evals[var] = ev
    fit_doc = dict(question_id="G1-CHAR-002", fold_deg=FOLD, n_bins=NB, train_sets=TRAIN_SETS, train_cases=NEW, support=support,
                   s_heading_information=s_info, s_fold_symmetry=s_symmetry(data, a.src, a.banks), fits=fits,
                   inputs={f"ERRORS_{c}.npz": sha(a.errors / f"ERRORS_{c}.npz") for c in NEW + OLD},
                   script_sha256=sha(__file__), command=sys.argv)
    json.dump(fit_doc, open(a.out / "FIT.json", "w"), indent=1)
    json.dump(dict(question_id="G1-CHAR-002", evals=evals), open(a.out / "EVAL.json", "w"), indent=1)
    print("done")


if __name__ == "__main__":
    main()
