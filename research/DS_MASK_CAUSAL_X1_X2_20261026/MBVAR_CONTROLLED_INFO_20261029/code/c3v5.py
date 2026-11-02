"""P2_C3V5 DRAFT (AMENDMENT-010): replay the exact S1V5 DEV3 input receipts, not independently regenerated inputs.

  c3v5.py run --field F --group LH|RV --out D      load the hash-verified S1V5 receipts of all shards, replay one field's
                                                    z/x0/ds_m/gy_m/taps and full Sig_true/Sig_model bytes (MAT|{f}|...),
                                                    re-run E' + post-fit P + class v3.1 + the truth-free start grid;
                                                    regenerated inputs are a REPORTED generator diagnostic only
  c3v5.py aggregate --shards D --out D            (env S1V5_RUN = committed S1V5 DEV3 run dir name)

Gating (keys without "REPORTED"): INPUT_REPRO (replayed inputs vs the receipt they were read from; definition open, D3),
STATE_COST_REPRO, P_REPRO (C10 diagonal, full C10, NEES4_C10), STATUS_REPRO, NO_WRONG_BASIN, ITER_CAP, PROBE_POWER,
LINEAR_EXACT, KINK_FIXTURES, rows. Reported only: STATE_STABILITY_FIXED (status open, D4), analytic-P, old-class changes,
F7 XMODEL truth start, KINK hypothesis, MODE_AMBIGUITY (R4, any truth-free alternative; D5), MAT cross-field consistency.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import zipfile
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import a10_canonical as CAN  # noqa: E402
import a10_validation as AV  # noqa: E402
import a8_jac as AJ  # noqa: E402
import filters as FL  # noqa: E402
import info_core as IC  # noqa: E402
import manifest as MF  # noqa: E402
import s0v2 as S0V2  # noqa: E402
import s1_mc as M  # noqa: E402
import s1v2 as V  # noqa: E402
import s1v5 as T  # noqa: E402
import world as Wd  # noqa: E402

GROUPS = {"LH": ("LOW", "HIGH"), "RV": ("REV60", "FWD60")}
D_REF = T.D_REF                                                         # fixed external scale (2 cm, 2 cm, 0.25 deg, 0.01 deg/s)
TOL = dict(z=1e-9, ctl=1e-12, fp_rel=1e-12, state_dref=1e-6, cost=1e-6, P_rel=1e-3, basin=1.0, stab1=1.0, stab2=2.0, stab_frac=0.99,
           itercap_dref=0.1, linear_rel=1e-3, probe_power_frac=0.99)
N = V.N; P0M = M.P0
SPLIT = "DEV3"


dref_diff = T.dref_diff

def full_c10_scaled_diff(row_a, row_b):
    """Ten unique entries, normalized by state covariance natural scales.
    This avoids meaningless relative blow-up for nearly zero cross terms.
    """
    worst = 0.0
    for i in range(4):
        for j in range(i, 4):
            k = f"C10rot_{i}{j}"
            ai = max(float(row_a[f"C10rot_{i}{i}"]), 0.0)
            aj = max(float(row_a[f"C10rot_{j}{j}"]), 0.0)
            bi = max(float(row_b[f"C10rot_{i}{i}"]), 0.0)
            bj = max(float(row_b[f"C10rot_{j}{j}"]), 0.0)
            scale = max(math.sqrt(ai * aj), math.sqrt(bi * bj), 1e-300)
            worst = max(worst, abs(float(row_a[k])-float(row_b[k]))/scale)
    return worst



def s1v5_dir():
    return Wd.EXP / "results" / os.environ["S1V5_RUN"]


def _same_bytes(a, b):
    return a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes()


def load_receipts_with_stats(d, strict=False):
    """Load only S1V5 original receipt ZIP bytes verified against its manifest (fail-closed).

    D2 (option a): full matrices are field-qualified, MAT|{f}|{role}|{cell}|..., so every key is unique across shards.
      - any key present in two zips          -> ERR_C3V5_DUPLICATE_INPUT_KEY (MAT copies with different bytes: ERR_C3V5_MAT_CONFLICT)
      - legacy field-less MAT|{role}|{cell}|  -> ERR_C3V5_LEGACY_MAT_KEY
      - MAT field not among the zip's fields  -> ERR_C3V5_MAT_FIELD_MISMATCH
    Returns (receipts, stats); stats records the MAT key / duplicate / conflict counts (the last two are 0 on success).
    """
    manpath = d / "MANIFEST.json"
    if not manpath.exists():
        raise SystemExit("ERR_C3V5_MISSING_MANIFEST")
    manifest = json.loads(manpath.read_text())
    hashes = {Path(k).name: v for k, v in manifest.get("output_sha256", {}).items()}
    rec, origin = {}, {}
    if strict:
        if (manifest.get("contract_sha256") != MF.sha256_file(MF.CONTRACT)
                or manifest.get("source_code_sha256") != MF.code_hashes()
                or len(manifest.get("source_git_sha", "")) != 40):
            raise SystemExit("ERR_A010_S1V5_SOURCE_CONTRACT_HASH")
    zips = sorted(d.glob(f"S1V5_INPUTS_{SPLIT}_*.zip"))
    if not zips:
        raise SystemExit("ERR_C3V5_MISSING_RECEIPTS")
    st = dict(n_receipt_files=len(zips), receipt_files=[f.name for f in zips], mat_keys=0, mat_duplicate_keys=0, mat_conflicts=0,
              mat_key_schema="MAT|{field}|{role}|{cell}|Sig_true, MAT|{field}|{role}|{cell}|{arm}|Sig_model")
    st["strict_index_verified"] = bool(strict)
    st["array_hashes_verified"] = 0
    for f in zips:
        if f.name not in hashes or CAN.sha_file(f) != hashes[f.name]:
            raise SystemExit("ERR_C3V5_RECEIPT_HASH")
        if strict:
            idx = f.with_name(f.name.replace("INPUTS_", "INPUT_HASHES_").replace(".zip", ".json"))
            try:
                _, proof = AV.verify_receipt_index(f, idx, hashes)
            except (ValueError, KeyError, OSError, zipfile.BadZipFile) as e:
                raise SystemExit(f"ERR_C3V5_RECEIPT_INTEGRITY {e}") from e
            st["array_hashes_verified"] += proof["n_arrays"]
        with np.load(f, allow_pickle=False) as z:
            files = list(z.files)
            fields = {k.split("|", 1)[0] for k in files if not (k.startswith("MAT|") or k.startswith("TRUTH|"))}
            for k in files:
                a = z[k]
                if k.startswith("MAT|"):
                    p = k.split("|")
                    shape_ok = (len(p) == 5 and p[4] == "Sig_true") or (len(p) == 6 and p[5] == "Sig_model")
                    if not (shape_ok and p[1].isdigit()):
                        raise SystemExit(f"ERR_C3V5_LEGACY_MAT_KEY {k} in {f.name}: MAT keys must be field-qualified")
                    if p[1] not in fields:
                        raise SystemExit(f"ERR_C3V5_MAT_FIELD_MISMATCH {k} in {f.name} (fields {sorted(fields)})")
                    st["mat_keys"] += 1
                if k in rec:
                    if k.startswith("MAT|") and not _same_bytes(rec[k], a):
                        raise SystemExit(f"ERR_C3V5_MAT_CONFLICT {k}: {origin[k]} vs {f.name}")
                    raise SystemExit(f"ERR_C3V5_DUPLICATE_INPUT_KEY {k}: {origin[k]} and {f.name}")
                rec[k] = a; origin[k] = f.name
    st["n_keys"] = len(rec)
    return rec, st


def load_receipts(d):
    return load_receipts_with_stats(d)[0]


def mat_cross_field_report(rec):
    """REPORTED only: are the field-qualified copies of one (role, cell, arm) matrix byte-identical across fields?

    Under the former field-less schema these were the colliding keys; a difference here (e.g. exp() ULPs on different
    runners) is kept per field, never merged, and does not gate.
    """
    groups = {}
    for k, a in rec.items():
        if k.startswith("MAT|"):
            p = k.split("|"); groups.setdefault("|".join(p[2:]), {})[int(p[1])] = a
    multi = {g: v for g, v in groups.items() if len(v) > 1}; ident = differ = 0; mx = 0.0
    for v in multi.values():
        arrs = [v[f] for f in sorted(v)]; ref = arrs[0]
        if all(_same_bytes(ref, a) for a in arrs[1:]):
            ident += 1; continue
        differ += 1
        for a in arrs[1:]:
            mx = max(mx, float(np.max(np.abs(a - ref)) / max(float(np.max(np.abs(ref))), 1e-300)) if a.shape == ref.shape else math.inf)
    return dict(n_groups=len(groups), n_groups_multi_field=len(multi), n_byte_identical=ident, n_differ=differ, max_rel_diff=mx,
                note="REPORTED only; each field is replayed with its own matrices")


def mode_ambiguity(sol, ref="E", oracle=("truth",), cost_tol=None, dref_tol=None):
    """R4 / D5: count every truth-free solution s != E' with |cost_s - cost_E'| <= 1 chi^2 and dref(E', s) > 2 d_ref.

    sol = {start: (cost, X)}; sol[ref] is E'. Oracle starts are excluded. REPORTED only (never gating).
    """
    cost_tol = TOL["basin"] if cost_tol is None else cost_tol; dref_tol = TOL["stab2"] if dref_tol is None else dref_tol
    c0, X0 = sol[ref]; within = []; amb = []
    for k, (c, X) in sol.items():
        if k == ref or k in oracle:
            continue
        if abs(float(c) - float(c0)) <= cost_tol:
            d = dref_diff(X0[-1], X[-1]); within.append(d)
            if d > dref_tol:
                amb.append(k)
    return dict(n_alt_ambiguous=len(amb), max_alt_dref_within_1chi2=float(max(within, default=0.0)), alt_ambiguous_starts=";".join(sorted(amb)))


def input_diffs(rec, kb, inp, w, Sig, models):
    """A8-1: per-component comparison of inputs with the S1V5 receipt (regenerated -> generator diagnostic; replayed -> INPUT_EXACT)."""
    if f"{kb}|z" not in rec:
        return dict(receipt_found=False)
    rel = lambda a, b: float(np.max(np.abs(a - b) / np.maximum(np.abs(b), 1e-300)))  # noqa: E731
    out = dict(receipt_found=True,
               d_z=float(np.max(np.abs(inp["z"] - rec[f"{kb}|z"]))), d_ds=float(np.max(np.abs(inp["ds_m"] - rec[f"{kb}|ds_m"]))),
               d_gy=float(np.max(np.abs(inp["gy_m"] - rec[f"{kb}|gy_m"]))), d_x0=float(np.max(np.abs(inp["x0"] - rec[f"{kb}|x0"]))),
               taps_equal=bool(np.array_equal(np.asarray(w["taps"]), rec[f"{kb}|taps"])),
               pose_keys_equal=bool(str(rec[f"{kb}|pose_keys_sha"]) == T.pose_keys_sha(w)),
               d_sig_true_rel=rel(T.sig_fp(Sig), rec[f"{kb}|Sig_true_fp"]))
    out["d_sig_model_rel"] = max((rel(T.sig_fp(Sm), rec[f"{kb}|{arm}|Sig_model_fp"]) if f"{kb}|{arm}|Sig_model_fp" in rec else float("inf"))
                                 for arm, Sm in models.items())
    return out


def cmd_run(field, group, out):
    lk = T.lock_v5(); M.check_code_lock(lk)
    if field not in lk["run_plan"]["C3V5"]["fields"]:
        raise SystemExit("ERR_SPLIT_LEAK C3V5 runs on the frozen S1V5 DEV3 fields only")
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    S = T.canonical_setup(lk); root = M.seed_root(); rows = []
    rec, receipt_stats = load_receipts_with_stats(s1v5_dir(), strict=True)
    if not receipt_stats["strict_index_verified"]:
        raise SystemExit("ERR_A010_INDEX_NOT_VERIFIED")
    all_poses, seen = [], set()
    for ww in S["wins"].values():
        for pp in ww["poses"]:
            key = Wd.pose_key("FFD_ONLY_P0", "A", *pp)
            if key not in seen:
                seen.add(key); all_poses.append(pp)
    factor_check = AV.factor_law(S["Lhalf"], np.asarray(all_poses), S["s1"])
    if not factor_check["pass_"] or len(all_poses) != 180:
        raise SystemExit("ERR_A010_GENERATOR_FACTOR_LAW")
    law_checks = []
    truth_checks = []
    sd0 = np.sqrt(np.diag(P0M))
    for cn, cell in S["cells"].items():
        wins = [S["wins"][r] for r in GROUPS[group] if cn in S["wins"][r]["cells"]]
        if not wins:
            continue
        pf = S["Lhalf"] @ M.rng(root, S0V2.CELL_ID_V2[cn], field, 1).standard_normal((S["Lhalf"].shape[1], 2)) if cell["alphas"][0] else None
        for w in wins:
            for sn in M.SENSOR_SEEDS:
                generated = T.make_inputs(S, root, field, cn, w, sn, pf)
                Sig_generated, models_generated = T.arm_models(S, w, cn)
                kb = f"{field}|{w['role']}|{cn}|{sn}"
                generated_diffs = input_diffs(rec, kb, generated, w, Sig_generated, models_generated)
                required = [f"{kb}|{name}" for name in ("z", "x0", "ds_m", "gy_m", "taps")]
                required += [T.mat_key(field, w["role"], cn)]
                required += [T.mat_key(field, w["role"], cn, arm) for arm in models_generated]
                if any(key not in rec for key in required):
                    raise SystemExit(f"ERR_C3V5_MISSING_CANON_ARRAY {kb}")
                if not np.array_equal(w["taps"], rec[f"{kb}|taps"]):
                    raise SystemExit(f"ERR_C3V5_TAP_MISMATCH {kb}")
                inp = dict(generated)
                for name in ("z", "x0", "ds_m", "gy_m"):
                    inp[name] = np.array(rec[f"{kb}|{name}"], copy=True)
                inp["vn"] = np.c_[inp["ds_m"] - w["ds"], inp["gy_m"] - w["dth"]]
                Sig = np.array(rec[T.mat_key(field, w["role"], cn)], copy=True)
                models = {arm: np.array(rec[T.mat_key(field, w["role"], cn, arm)], copy=True)
                          for arm in models_generated}
                tk = f"TRUTH|{field}|{w['role']}|{cn}"
                truth_expected = {"Xtrue": w["Xtrue"], "poses": w["poses"], "dts": w["dts"],
                                  "ds_true": w["ds"], "dth_true": w["dth"],
                                  "prior_P0": P0M, "mu": np.zeros((N, 2)),
                                  "pose_keys_sha": np.array(T.pose_keys_sha(w))}
                truth_ok = all(f"{tk}|{name}" in rec and
                               AV.array_sha(rec[f"{tk}|{name}"]) == AV.array_sha(v)
                               for name, v in truth_expected.items())
                truth_checks.append(bool(truth_ok))
                if not truth_ok:
                    raise SystemExit(f"ERR_A010_TRUTH_ONLY_REPLAY {tk}")
                law = AV.generator_law(w, S, cn, Sig)
                law_checks.append(law)
                if not law["pass_"]:
                    raise SystemExit(f"ERR_A010_GENERATOR_LAW {tk}")
                idf = input_diffs(rec, kb, inp, w, Sig, models)
                idf["INPUT_EXACT"] = bool(idf.get("receipt_found") and all(idf[k] == 0 for k in ("d_z","d_ds","d_gy","d_x0")))
                idf["generator_regen_d_z_REPORTED"] = generated_diffs.get("d_z", float("nan"))
                ht = lambda X, t=w["taps"]: Wd.h_H_tap(X, "A", t)  # noqa: E731
                z, x0, dsm, gym = inp["z"], inp["x0"], inp["ds_m"], inp["gy_m"]; mu = np.zeros((N, 2))
                Tr = IC.rotation_rt(w["Xtrue"][-1], Wd.ANCHORS["A"])
                for arm, Sm in models.items():
                    skey = (field, w["role"], cn, sn, arm)
                    r, XE, IE, thp = T.eval_batch(w, arm, Sm, inp, skey)          # XE = X' (polished E); r["cost"] = cost(E')
                    starts = {f"psi{k:+d}": (np.r_[x0[:2], FL.wrap(x0[2] + k * sd0[2]), x0[3]], np.zeros((N, 2))) for k in FL.MS_K}
                    starts["x+1"] = (x0 + np.r_[sd0[0], 0, 0, 0], np.zeros((N, 2))); starts["y+1"] = (x0 + np.r_[0, sd0[1], 0, 0], np.zeros((N, 2)))
                    starts["truth"] = (w["Xtrue"][0].copy(), -inp["vn"])
                    sol = {"E": (r["cost"], XE)}
                    for nm, th in starts.items():
                        Xs, _, Is = FL.batch_map_v2(ht, z, mu, Sm, dsm, gym, w["dts"], x0, P0M, theta0=th)
                        sol[nm] = (Is["cost"], Xs)
                    # Truth-start is a diagnostic, NEVER part of the operational/reference best-start choice.
                    nonoracle = {k:v for k,v in sol.items() if k != "truth"}
                    cstar = min(v[0] for v in nonoracle.values()); best = min(nonoracle, key=lambda k: nonoracle[k][0])
                    pc10 = np.array([r[f"P_{AJ.PRIMARY}_{a}"] for a in T.STATES])
                    de = XE[-1] - sol[best][1][-1]; de[2] = FL.wrap(de[2])
                    integrity = AV.verify_estimator_inputs(rec, kb, inp, Sm, w["taps"], arm)
                    if not integrity["pass_"]:
                        raise SystemExit(f"ERR_A010_ESTIMATOR_INPUT_BYTES {kb}|{arm} {integrity['mismatches']}")
                    rec_ = dict(field=field, role=w["role"], cell=cn, sensor_seed=sn, arm=arm,
                                RECEIPT_ARRAY_EXACT=integrity["pass_"],
                                RECEIPT_ARRAYS_CHECKED=integrity["n_checked"],
                                TRUTH_ONLY_VERIFIED=truth_ok, GENERATOR_LAW_PASS=law["pass_"], **idf,
                                **{k: r[k] for k in ("conv", "class_v31", "cost", "cost_E", "ms_best_k", "rescued", "ms_triggered", "kink_poses_at_E",
                                                     "probe_min_dcost", "dec_A_fixed", "rel_spread", "KINK_P_UNCERTAIN", "polish_steps",
                                                     "polish_cost_decrease", "polish_E_vs_Ep_dref", "nees4_C10")},
                                **{f"xend_{i}": r[f"xend_{i}"] for i in range(4)}, **{f"xendE_{i}": r[f"xendE_{i}"] for i in range(4)},
                                **{f"P_{m}_{a}": r[f"P_{m}_{a}"] for m in ("A", AJ.PRIMARY) for a in T.STATES},
                                **{f"C10rot_{i}{j}": r[f"C10rot_{i}{j}"] for i in range(4) for j in range(i,4)},
                                C_star=cstar, best_start=best, gap_E=r["cost"] - cstar, E_vs_best_dref=dref_diff(XE[-1], sol[best][1][-1]),
                                E_vs_best_sdC10=float(np.max(np.abs(Tr @ de) / np.sqrt(pc10))),
                                truth_gap=sol["truth"][0] - cstar, n_starts_gross_worse=int(sum(v[0] > cstar + 1.0 for v in nonoracle.values())),
                                **mode_ambiguity(sol),
                                **T.probe_power(ht, z, Sm, dsm, gym, w["dts"], x0, thp, T.key_seed("PP", field, w["role"], cn, sn, arm) % (2 ** 62)))
                    if IE["status"] != "CONVERGED":
                        _, I3, _, X3p, c3p, _ = T.estimate(w, Sm, inp, skey, max_iter=300)
                        rec_.update(E300_status=I3["status"], E300_vs_E_dref=dref_diff(X3p[-1], XE[-1]), E300_cost_minus_E=c3p - r["cost"])
                    else:
                        rec_.update(E300_status="NOT_RUN_CONVERGED", E300_vs_E_dref=0.0, E300_cost_minus_E=0.0)
                    rows.append(rec_)
        print("C3V5", field, group, cn, len(rows), flush=True)
    pd.DataFrame(rows).to_csv(out / f"C3V5_ROWS_{field}_{group}.csv", index=False, float_format="%.17g")
    law_receipt = dict(pass_=bool(factor_check["pass_"] and all(x["pass_"] for x in law_checks)
                                  and truth_checks and all(truth_checks)),
                       factor=factor_check, n_covariance_law_checked=len(law_checks),
                       max_cov_relative_error=max((x["max_relative_error"] for x in law_checks), default=None),
                       min_cov_eigenvalue=min((x["min_eig"] for x in law_checks), default=None),
                       n_truth_replayed=len(truth_checks), field=field, group=group)
    (out / f"C3V5_GENERATOR_LAW_{field}_{group}.json").write_text(json.dumps(law_receipt, indent=1))
    return 0


def linear_exact():
    """LINEAR_EXACT: on an affine h with the real window controls, every P convention equals the analytic-H P (rel <= 1e-3)."""
    lk = T.lock_v5(); S = T.canonical_setup(lk); w = S["wins"]["LOW"]; hb = AJ.linear_h()
    rg = np.random.default_rng(7); z = hb(w["Xtrue"])[0] + 0.05 * rg.standard_normal((N, 2)); Sm = np.eye(2 * N) * 0.05 ** 2
    x0 = w["Xtrue"][0].copy(); theta = (x0.copy(), np.zeros((N, 2)))
    Tr = IC.rotation_rt(w["Xtrue"][-1], Wd.ANCHORS["A"])
    pf = T.post_fit_P(hb, z, Sm, w["ds"], w["dth"], w["dts"], x0, theta, Tr)
    ref = np.array([pf[f"P_A_{a}"] for a in T.STATES])
    worst = max(float(np.max(np.abs(np.array([pf[f"P_{m}_{a}"] for a in T.STATES]) - ref) / ref)) for m in AJ.METHODS)
    return dict(pass_=bool(worst <= TOL["linear_rel"] and all(pf[f"pd_{m}"] for m in AJ.METHODS)), max_rel=worst)


def kink_fixtures():
    hv, Xk, Xs = AJ.fixture_piecewise()
    L = AJ.fd_H(hv, Xk, *AJ.METHODS["L"]); R = AJ.fd_H(hv, Xk, *AJ.METHODS["R"]); Cc = AJ.fd_H(hv, Xk, *AJ.METHODS[AJ.PRIMARY])
    an = np.zeros((len(Xs), 2, 4)); an[:, 0, 0] = 5.0; an[:, 0, 1] = 0.1; an[:, 1, 1] = Xs[:, 1]; an[:, 1, 2] = 0.3
    smooth = max(float(np.max(np.abs(AJ.fd_H(hv, Xs, *AJ.METHODS[m]) - an))) for m in AJ.METHODS if AJ.METHODS[m] is not None)
    ok = bool(np.allclose(L[:, 0, 0], 2.0, atol=1e-6) and np.allclose(R[:, 0, 0], 5.0, atol=1e-6) and np.allclose(Cc[:, 0, 0], 3.5, atol=1e-9) and smooth <= 1e-6)
    return dict(pass_=ok, left=float(L[0, 0, 0]), right=float(R[0, 0, 0]), central=float(Cc[0, 0, 0]), smooth_control_max_abs=smooth)


def cmd_aggregate(shards, out):
    lk = T.lock_v5(); M.check_code_lock(lk); out = Path(out); out.mkdir(parents=True, exist_ok=True)
    fs = sorted(glob.glob(str(Path(shards) / "**" / "C3V5_ROWS_*.csv"), recursive=True))
    C = pd.concat([pd.read_csv(f) for f in fs], ignore_index=True) if fs else pd.DataFrame()
    src = s1v5_dir(); D = pd.read_csv(src / f"S1V5_RESULTS_{SPLIT}.csv")
    REC, receipt_load = load_receipts_with_stats(src, strict=True)
    mat_xf = mat_cross_field_report(REC)
    field_equivalence = AV.covariance_equivalence(REC, expected_fields=lk["run_plan"]["S1V5"]["fields"])
    pd.DataFrame(field_equivalence["details"]).to_csv(out / "A010_CROSS_FIELD_COV.csv", index=False)
    del REC
    law_paths = sorted(Path(shards).glob("**/C3V5_GENERATOR_LAW_*.json"))
    laws = [json.loads(p.read_text()) for p in law_paths]
    gen_law_pass = bool(laws and len(laws) == 2 * len(lk["run_plan"]["C3V5"]["fields"])
                        and all(l.get("pass_") for l in laws))
    D = D[D.arm.astype(str).str.endswith("_BATCH") & (D.status == "OK")].set_index(["field", "role", "cell", "sensor_seed", "arm"])
    fields = lk["run_plan"]["C3V5"]["fields"]
    n_exp = len(fields) * len(M.SENSOR_SEEDS) * (2 * len(V.LH_CELLS) * 2 + 2 * (len(S0V2.REV_CELLS) * 2 + len(S0V2.XMODEL)))
    cmp = []
    for _, r in C.iterrows():
        k = (r.field, r.role, r.cell, r.sensor_seed, r.arm)
        if k not in D.index:
            cmp.append(dict(found=False)); continue
        s = D.loc[k]
        cmp.append(dict(found=True, d_state_dref=dref_diff([r[f"xend_{i}"] for i in range(4)], [s[f"xend_{i}"] for i in range(4)]),
                        d_cost=abs(r.cost - s.cost), same_best_k=int(r.ms_best_k) == int(s.ms_best_k),
                        d_stateE_dref=dref_diff([r[f"xendE_{i}"] for i in range(4)], [s[f"xendE_{i}"] for i in range(4)]), d_costE=abs(r.cost_E - s.cost_E),
                        d_P_C10_rel=max(abs(r[f"P_{AJ.PRIMARY}_{a}"] - s[f"P_{AJ.PRIMARY}_{a}"]) / s[f"P_{AJ.PRIMARY}_{a}"] for a in T.STATES),
                        d_P_A_rel=max(abs(r[f"P_A_{a}"] - s[f"P_A_{a}"]) / s[f"P_A_{a}"] for a in T.STATES),
                        d_P_full_C10_rel=full_c10_scaled_diff(r,s),
                        d_NEES4_C10_rel=abs(r.nees4_C10-s.nees4_C10)/max(abs(s.nees4_C10),1e-300),
                        same_class_v31=r.class_v31 == s.class_v31, same_old_class=r.conv == s.conv))
    C = pd.concat([C, pd.DataFrame(cmp, index=C.index)], axis=1) if len(C) else C
    # Reconstruct every 4x4 C10 in two independent receipts and check SPD/condition.
    full_c10_checks = []
    for _, rr in C.iterrows():
        key = (rr.field, rr.role, rr.cell, rr.sensor_seed, rr.arm)
        if not bool(rr.get("found", False)) or key not in D.index:
            full_c10_checks.append(dict(pass_=False, full_C10_rel=np.inf,
                                        condition_log10_delta=np.inf, nees4_rel=np.inf))
            continue
        full_c10_checks.append(AV.covariance_replay_check(rr, D.loc[key],
                                  scaled_difference=full_c10_scaled_diff))
    if len(C):
        C["full_C10_spd_pass"] = [v["pass_"] for v in full_c10_checks]
        C["c10_log10_cond_delta"] = [v.get("condition_log10_delta", np.inf) for v in full_c10_checks]
        C["c10_source_eigmin"] = [v.get("source", {}).get("min_eigenvalue") for v in full_c10_checks]
        C["c10_replay_eigmin"] = [v.get("replay", {}).get("min_eigenvalue") for v in full_c10_checks]
    C.to_csv(out / "C3V5_ROWS.csv", index=False, float_format="%.17g")
    if len(C):
        C[["field", "role", "cell", "sensor_seed", "arm", "d_P_full_C10_rel",
           "d_NEES4_C10_rel", "full_C10_spd_pass", "c10_log10_cond_delta",
           "c10_source_eigmin", "c10_replay_eigmin"]].to_csv(out / "A010_FULL_C10_REPRO.csv", index=False)
    allrows = bool(len(C) == n_exp and C.found.all()) if len(C) else False
    rf = C.INPUT_EXACT.astype(bool) if len(C) else pd.Series(dtype=bool)
    per_arm = C.groupby("arm").apply(lambda d: dict(n=len(d), frac_le_1dref=float((d.E_vs_best_dref <= TOL["stab1"]).mean()),
                                                    max_dref=float(d.E_vs_best_dref.max()), max_sdC10_REPORTED=float(d.E_vs_best_sdC10.max())),
                                     include_groups=False).to_dict() if len(C) else {}
    xm = C[C.arm == "XMODEL_BATCH"] if len(C) else C
    nc = C[C.conv != "CONVERGED"] if len(C) else C
    crit = dict(
        INPUT_REPRO_LEGACY_REPORTED=dict(pass_=bool(allrows and rf.all() and (C.d_z <= TOL["z"]).all() and (C[["d_ds", "d_gy", "d_x0"]].max(axis=1) <= TOL["ctl"]).all()
                                    and C.taps_equal.astype(bool).all() and C.pose_keys_equal.astype(bool).all()
                                    and (C[["d_sig_true_rel", "d_sig_model_rel"]].max(axis=1) <= TOL["fp_rel"]).all()),
                         max_z=float(C.d_z.max()), max_ctl=float(C[["d_ds", "d_gy", "d_x0"]].max().max()),
                         max_sig_fp_rel=float(C[["d_sig_true_rel", "d_sig_model_rel"]].max().max())),
        STATE_COST_REPRO=dict(pass_=bool(allrows and (C.d_state_dref <= TOL["state_dref"]).all() and (C.d_cost <= TOL["cost"]).all() and C.same_best_k.all()),
                              max_state_dref=float(C.d_state_dref.max()), max_cost=float(C.d_cost.max()), n_best_k_diff=int((~C.same_best_k.astype(bool)).sum()),
                              raw_E_max_state_dref_REPORTED=float(C.d_stateE_dref.max()), raw_E_max_cost_REPORTED=float(C.d_costE.max())),
        P_REPRO_LEGACY_REPORTED=dict(pass_=bool(allrows and (C.d_P_C10_rel <= TOL["P_rel"]).all()
                                              and (C.d_P_full_C10_rel <= TOL["P_rel"]).all()
                                              and (C.d_NEES4_C10_rel <= TOL["P_rel"]).all()),
                      max_full_C10_rel=float(C.d_P_full_C10_rel.max()),
                      max_nees4_C10_rel=float(C.d_NEES4_C10_rel.max()), max_C10_rel=float(C.d_P_C10_rel.max()),
                     analytic_A_max_rel_REPORTED=float(C.d_P_A_rel.max()), analytic_A_n_gt_tol_REPORTED=int((C.d_P_A_rel > TOL["P_rel"]).sum())),
        STATUS_REPRO=dict(pass_=bool(allrows and C.same_class_v31.all()), n_class_v31_diff=int((~C.same_class_v31.astype(bool)).sum()),
                          old_class_changes_REPORTED=int((~C.same_old_class.astype(bool)).sum())),
        NO_WRONG_BASIN=dict(pass_=bool(allrows and (C.gap_E <= TOL["basin"]).all()), max_gap=float(C.gap_E.max()), n_gt_1=int((C.gap_E > TOL["basin"]).sum()),
                            note="C* = min cost over E' and the 9 truth-free fixed starts (psi -3..+3 SD x7, x+1 SD, y+1 SD); "
                                 "the truth start is an ORACLE_ONLY diagnostic (truth_gap) and never enters C* (bounded search, not a global-optimum proof)"),
        STATE_STABILITY_FIXED_LEGACY=dict(pass_=bool(allrows and all(v["frac_le_1dref"] >= TOL["stab_frac"] for v in per_arm.values()) and (C.E_vs_best_dref <= TOL["stab2"]).all()),
                                   per_arm=per_arm, d_ref=D_REF.tolist()),
        ITER_CAP=dict(pass_=bool(allrows and (nc.E300_vs_E_dref <= TOL["itercap_dref"]).all()), max_dref=float(C.E300_vs_E_dref.max()),
                      n_not_converged=int(len(nc))),
        PROBE_POWER=dict(pass_=bool(allrows and (C.pp_class == "NOT_CERTIFIED").mean() >= TOL["probe_power_frac"]),
                         frac_not_certified=float((C.pp_class == "NOT_CERTIFIED").mean()), rise_min_max=[float(C.pp_rise.min()), float(C.pp_rise.max())],
                         note="negative control: displaced point (cost +~1 chi^2) must be NOT_CERTIFIED"),
        LINEAR_EXACT=linear_exact(),
        KINK_FIXTURES=kink_fixtures(),
        F7_XMODEL_truth_start_REPORTED=dict(rows=int(len(xm)), truth_start_worse_than_E_frac=float((xm.truth_gap > xm.gap_E + 1e-6).mean()) if len(xm) else None,
                                            all_arms_frac=float((C.truth_gap > C.gap_E + 1e-6).mean()) if len(C) else None),
        KINK_HYPOTHESIS_REPORTED=dict(frac_kink_KINK_P_UNCERTAIN=float((C[C.KINK_P_UNCERTAIN.astype(str).str.lower() == "true"].kink_poses_at_E > 0).mean())
                                      if (C.KINK_P_UNCERTAIN.astype(str).str.lower() == "true").any() else None,
                                      class_v31_counts=C.class_v31.value_counts().to_dict(), old_class_counts=C.conv.value_counts().to_dict()),
        MODE_AMBIGUITY_REPORTED=dict(rule="R4: a row is AMBIGUOUS if ANY truth-free solution s != E' has |cost_s - cost_E'| <= 1 chi^2 "
                                          "and dref(E', s) > 2 (truth start excluded)",
                                     n_ambiguous=int((C.n_alt_ambiguous > 0).sum()), n_alt_solutions=int(C.n_alt_ambiguous.sum()),
                                     max_alt_dref_within_1chi2=float(C.max_alt_dref_within_1chi2.max()),
                                     n_ambiguous_best_start_only_legacy=int(((C.gap_E <= TOL["basin"]) & (C.E_vs_best_dref > TOL["stab2"])).sum()),
                                     claim_unique_map_allowed=False),
        rows=dict(pass_=allrows, n=int(len(C)), n_expected=n_exp))
    # D3/D4: no suffix-based gate selection; all IDs explicitly registered.
    criterion_input = crit["INPUT_REPRO_LEGACY_REPORTED"]
    receipt_ok = bool(allrows and receipt_load["strict_index_verified"] and
                      receipt_load["array_hashes_verified"] > 0 and len(C) and
                      C.RECEIPT_ARRAY_EXACT.astype(bool).all() and
                      C.TRUTH_ONLY_VERIFIED.astype(bool).all() and
                      criterion_input["pass_"])
    crit["RECEIPT_INTEGRITY"] = dict(pass_=receipt_ok, checked_input_arrays=receipt_load["array_hashes_verified"],
                                        exact_estimator_rows=int(C.RECEIPT_ARRAY_EXACT.astype(bool).sum()) if len(C) else 0,
                                        original_zip_and_index_sha_verified=True,
                                        truth_only_replayed=bool(len(C) and C.TRUTH_ONLY_VERIFIED.astype(bool).all()),
                                        note="Original S1V5 bytes used, not proof of the field's generating distribution")
    crit["GENERATOR_LAW"] = dict(pass_=gen_law_pass, n_runner_law_receipts=len(laws),
                                 source="independent closed-form full covariance and 180-pose Lhalf@Lhalf.T",
                                 stochastic_field_distribution="REPORTED_ONLY, n=10 not a distribution proof")
    crit["CROSS_FIELD_COV_EQUIVALENCE"] = dict(pass_=field_equivalence["pass_"],
                                              n_groups=field_equivalence["n_groups"],
                                              n_failed=field_equivalence["n_failed"],
                                              delta_max=field_equivalence["delta_max"],
                                              delta_F=field_equivalence["delta_F"],
                                              tol=AV.COV_EQ_TOL)
    c10_ok = bool(allrows and full_c10_checks and all(v["pass_"] for v in full_c10_checks)
                  and crit["P_REPRO_LEGACY_REPORTED"]["pass_"])
    crit["FULL_C10_REPRO"] = dict(pass_=c10_ok, n_checked=len(full_c10_checks),
                                 worst_condition_log10_delta=max((v.get("condition_log10_delta", np.inf)
                                                                  for v in full_c10_checks), default=None),
                                 n_fail=sum(not v["pass_"] for v in full_c10_checks),
                                 tol_log10_condition=AV.C10_COND_LOG_TOL)
    # All historical 4D state-stability rows remain in the output; new modes are prospective.
    crit["STATE_STABILITY_FIXED_LEGACY"]["historical_status"] = "PRESERVED_NOT_RETROACTIVE_PASS"
    mode = AV.mode_identifiability(C.to_dict("records")) if len(C) else AV.mode_identifiability([])
    C[["field", "role", "cell", "sensor_seed", "arm", "n_alt_ambiguous",
       "E_vs_best_dref", "alt_ambiguous_starts"]].to_csv(out / "A010_MODE_IDENTIFIABILITY.csv", index=False) if len(C) else None
    numeric = AV.gate_verdict(crit)
    gating = numeric["gated"]
    status = numeric["status"]
    (out / "A010_RECEIPT_INTEGRITY.json").write_text(json.dumps(crit["RECEIPT_INTEGRITY"], indent=1))
    (out / "A010_GENERATOR_LAW.json").write_text(json.dumps(dict(criteria=crit["GENERATOR_LAW"], detail=laws), indent=1))
    (out / "A010_G5_MODE_IDENTIFIABILITY.json").write_text(json.dumps(mode, indent=1))
    res = dict(status=status, G5_NUMERIC_REPLAY=numeric, G5_MODE_IDENTIFIABILITY=mode,
               G5_science="MODE_IDENTIFIABILITY_SEPARATE_FROM_NUMERIC_REPLAY",
               science_release_allowed=False, science_release="NO-GO_AUDIT_PENDING",
               SOLVER_REPRO_CROSS_RUNNER="NOT_YET_VERIFIED",
               gating=gating, criteria=crit, s1v5_run=src.name, tolerances=TOL,
               receipt_load=receipt_load, MAT_CROSS_FIELD_REPORTED=mat_xf,
               preserved=["C2 run 40871327417 FAIL", "C1 original-rule FAIL", "S1V2 DEV runs 40864089916 / 40867939262 FAIL",
                          "C3 run 40992589158 FAIL", "C3V4 run 41005158792 FAIL", "G5 FAIL",
                          "S1V3/S1V4 DEV2 H1 LOW POSE_HIGH tan FAIL and H2 tan sign reversal"],
               holdout2_allowed=False,
               holdout2_note="HOLDOUT2 stays closed: requires AMENDMENT-010 FROZEN, an independent audit of S1V5+C3V5 and a separate confirmatory approval",
               p3="NO-GO")
    (out / "C3V5_STATUS.json").write_text(json.dumps(res, indent=1, default=float))
    MF.write_manifest(out, phase="P2_S1", status=status, contract_sha=MF.sha256_file(MF.CONTRACT),
                      config_files=[Wd.EXP / "config/PLAN_PARAMETERS.json"] + [Wd.EXP / f"contracts/AMENDMENT-00{i}.md" for i in range(3, 10)] + [Wd.EXP / "contracts/AMENDMENT-010.md"],
                      input_lock=Path(os.environ.get("REFLECT_ROOT", ".")) / "out" / "INPUT_LOCK.sha256", outputs=sorted(list(out.glob("C3V5_*")) + list(out.glob("A010_*"))),
                      seed_ledger=None, verdict="NOT_EVALUATED", unit="mathematical_deterministic",
                      limitations=["technical reproducibility/convergence verification on DEV3 only", "SELF_REVIEW_ONLY"],
                      extra=dict(sub_phase="P2_C3V5", amendment="AMENDMENT-010"))
    print("C3V5", status, {k: crit[k]["pass_"] for k in gating}, "| receipts", receipt_load["n_receipt_files"], "MAT keys", receipt_load["mat_keys"],
          "dup", receipt_load["mat_duplicate_keys"], "conflict", receipt_load["mat_conflicts"])
    return 0 if status == "PASS" else 1


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("cmd"); ap.add_argument("--out", required=True)
    ap.add_argument("--field", type=int); ap.add_argument("--group"); ap.add_argument("--shards")
    a = ap.parse_args()
    if a.cmd == "run":
        return cmd_run(a.field, a.group, a.out)
    return cmd_aggregate(a.shards, a.out)


if __name__ == "__main__":
    raise SystemExit(main())
