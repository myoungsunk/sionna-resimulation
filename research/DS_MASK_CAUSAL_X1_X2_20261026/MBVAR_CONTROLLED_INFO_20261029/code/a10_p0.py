"""AMENDMENT-010-P0: forensic ablations on existing DEV2 keys (not confirmatory; no estimator or threshold is adopted here).

  a10_p0.py gen --out D                         generator-factor lock (Lhalf.npy) + canonical inputs of the 4 frozen keys
  a10_p0.py abl --case K1 --rep A --out D       byte-replay ablations of one key on this runner   (env A010_GEN_RUN)
  a10_p0.py aggregate --shards D --out D        cross-replicate comparison + reports                (env A010_GEN_RUN)

Implements PROPOSER_A010_IMPLEMENTER_HANDOFF_DRAFT_20261030 Phase A010-P0 (audit branch audit/mbvar-info-c3-a010-proposal-20261030,
ef0b707c). Frozen A008/A009 modules are imported, never modified. The truth start is recorded as ORACLE_ONLY and never selects a
solution.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import io
import json
import math
import os
import platform
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import a8_jac as AJ  # noqa: E402
import filters as FL  # noqa: E402
import info_core as IC  # noqa: E402
import manifest as MF  # noqa: E402
import s0v2 as S0V2  # noqa: E402
import s1_mc as M  # noqa: E402
import s1v2 as V  # noqa: E402
import s1v3 as B3  # noqa: E402
import s1v4 as S4  # noqa: E402
import world as Wd  # noqa: E402

N = V.N; P0M = M.P0; STATES = B3.STATES
CASES = {  # (field, role, cell, sensor, arm), fixed before any A010 result (AMENDMENT-010-P0 lock)
    "K1": (10, "LOW", "TIME_1", 2, "ORACLE_CORR_BATCH"),        # C3 kink stop-point bifurcation row
    "K2": (11, "REV60", "TIME_HIGH_5", 0, "ORACLE_CORR_BATCH"),  # C3/C3V4 STATE_STABILITY near-alternative minimum
    "K3": (10, "LOW", "LOWCORR", 1, "IID_BATCH"),               # smooth no-kink control (first rule-selected S1V4 row)
    "K4": (15, "REV60", "POSE_HIGH", 1, "ORACLE_CORR_BATCH"),   # C3V4 largest d_cost (pose-field input difference)
}
S1V4_RUN = "P2_S1V4_run_40992623257"; S1V3_RUN = "P2_S1V3_run_40981032471"
TAUS = (1e-3, 1e-6, 1e-9); TAU_MAX = 300; BASE_TAU, BASE_MAX = S4.POLISH_TOL, S4.POLISH_MAX
PERT_SIZE, PERT_SEEDS, PERT_TAUS = 1e-14, (1, 2, 3), (1e-3, 1e-9)
LLT_REL_TOL = 1e-10            # |L L^T - K_psd|_max / |K|_max (eigh backward error ~ n eps = 4e-14; fixed before the run)
PROFILE_T = np.linspace(-0.25, 1.25, 31)
LHALF_NAME = "A010_LHALF_WORLDPOSE_V2.npy"; CANON_NAME = "A010_CANONICAL_INPUTS.zip"


def lock_p0():
    lk = S0V2.lock_v2()
    if "AMENDMENT-010-P0" not in lk.get("applied_amendment_locks", []):
        raise SystemExit("ERR_CONTRACT_DRAFT: AMENDMENT-010-P0 lock not FROZEN/applied")
    return lk


def sha_arr(a):
    a = np.ascontiguousarray(np.asarray(a))
    return hashlib.sha256(a.dtype.str.encode() + str(a.shape).encode() + a.tobytes()).hexdigest()


def sha_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def sysinfo():
    cpu = ""
    try:
        cpu = next((l.split(":", 1)[1].strip() for l in subprocess.check_output(["lscpu"], text=True).splitlines() if l.startswith("Model name")), "")
    except Exception:  # noqa: BLE001
        pass
    try:
        cfg = np.show_config(mode="dicts"); blas = cfg.get("Build Dependencies", {}).get("blas", {})
        blas = {k: blas.get(k) for k in ("name", "version", "openblas configuration")}
    except Exception:  # noqa: BLE001
        blas = {}
    try:
        import scipy
        sv = scipy.__version__
    except Exception:  # noqa: BLE001
        sv = None
    feats = sorted(k for k, v in getattr(np._core._multiarray_umath, "__cpu_features__", {}).items() if v) if hasattr(np, "_core") else []
    return dict(cpu=cpu, machine=platform.machine(), python=sys.version.split()[0], numpy=np.__version__, scipy=sv, blas=blas,
                numpy_cpu_features_avx512=[f for f in feats if f.startswith("AVX512")], numpy_cpu_features_n=len(feats),
                threads={k: os.environ.get(k) for k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_CORETYPE")},
                runner=os.environ.get("RUNNER_NAME"), github_run_id=os.environ.get("GITHUB_RUN_ID"), github_job=os.environ.get("GITHUB_JOB"))


def world_kernel(lk):
    """Exactly the s1v2.setup construction: union of the four windows' canonical poses (first occurrence order) -> Kp."""
    s1 = Wd.PARAMS["synthetic_s1"]; W = S0V2.windows_v2(lk); keys = {}; xs = []
    for role, w in W.items():
        for p in w["poses"]:
            k = Wd.pose_key("FFD_ONLY_P0", "A", *p)
            if k not in keys:
                keys[k] = len(xs); xs.append(p)
    LP = np.array(xs)
    Kp = IC.k_pose(LP[:, :2], LP[:, 2], s1["pose_corr_length_m"], math.radians(s1["pose_corr_yaw_deg"]))
    return Kp, list(keys), LP


def kernel_checks(L, Kp):
    w, Vv = np.linalg.eigh(0.5 * (Kp + Kp.T)); Kpsd = (Vv * np.clip(w, 0, None)) @ Vv.T; s = float(np.max(np.abs(Kp)))
    LLt = L @ L.T
    return dict(max_abs_LLt_minus_Kpsd_rel=float(np.max(np.abs(LLt - Kpsd)) / s), max_abs_LLt_minus_K_rel=float(np.max(np.abs(LLt - Kp)) / s),
                max_abs_diag_LLt_minus_1=float(np.max(np.abs(np.diag(LLt) - 1.0))), min_eig=float(w[0]), max_eig=float(w[-1]),
                n_eig_below_1e_minus_10_of_max=int(np.sum(w < 1e-10 * w[-1])), tol_rel=LLT_REL_TOL)


def case_window(S, key):
    f, role, cn, sn, arm = key
    return S["wins"][role]


def load_receipt(run, prefix, f):
    with np.load(Wd.EXP / "results" / run / f"{prefix}_INPUTS_DEV2_{f}.zip", allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


# ----------------------------------------------------------------------------- GEN
def cmd_gen(out):
    lk = lock_p0(); M.check_code_lock(lk); out = Path(out); out.mkdir(parents=True, exist_ok=True)
    S = V.setup(lk); Kp, keys, LP = world_kernel(lk)
    L, wmin, wmax = IC.psd_sqrt(Kp)
    if not np.array_equal(L, S["Lhalf"]):
        raise SystemExit("ERR_GEN: world_kernel() does not reproduce s1v2.setup Lhalf on this runner")
    L = np.ascontiguousarray(L, dtype="<f8"); np.save(out / LHALF_NAME, L)
    chk = kernel_checks(L, Kp); chk["pass"] = chk["max_abs_LLt_minus_Kpsd_rel"] <= LLT_REL_TOL and chk["max_abs_diag_LLt_minus_1"] <= LLT_REL_TOL
    rows = []; canon = {}
    for cid, key in CASES.items():
        f, role, cn, sn, arm = key; w = S["wins"][role]; kb = f"{f}|{role}|{cn}|{sn}"
        r4 = load_receipt(S1V4_RUN, "S1V4", f); r3 = load_receipt(S1V3_RUN, "S1V3", f)
        Sig, models = B3.arm_models(S, w, cn)
        arrs = dict(z=r4[f"{kb}|z"], ds_m=r4[f"{kb}|ds_m"], gy_m=r4[f"{kb}|gy_m"], x0=r4[f"{kb}|x0"], taps=r4[f"{kb}|taps"],
                    poses=np.asarray(w["poses"], float), Xtrue=np.asarray(w["Xtrue"], float), ds_true=np.asarray(w["ds"], float),
                    dth_true=np.asarray(w["dth"], float), dts=np.asarray(w["dts"], float), Sigma_true=np.asarray(Sig, float),
                    Sigma_model=np.asarray(models[arm], float))
        if not np.array_equal(np.asarray(w["taps"]), arrs["taps"]):
            raise SystemExit(f"ERR_GEN {cid}: setup taps differ from the S1V4 receipt")
        fp = r4[f"{kb}|{arm}|Sig_model_fp"]; fp_now = B3.sig_fp(arrs["Sigma_model"])
        for k, a in arrs.items():
            canon[f"{cid}|{k}"] = a
            rows.append(dict(case=cid, key="|".join(map(str, key)), array=k, sha256=sha_arr(a), dtype=a.dtype.str, shape=str(a.shape),
                             source=("S1V4 receipt byte copy" if k in ("z", "ds_m", "gy_m", "x0", "taps") else "s1v2.setup on the GEN runner")))
        rows.append(dict(case=cid, key="|".join(map(str, key)), array="z_S1V3_receipt", sha256=sha_arr(r3[f"{kb}|z"]), dtype=r3[f"{kb}|z"].dtype.str,
                         shape=str(r3[f"{kb}|z"].shape), source=f"S1V3 receipt; max|z_S1V3 - z_S1V4| = {float(np.max(np.abs(r3[f'{kb}|z'] - arrs['z']))):.3g}"))
        rows.append(dict(case=cid, key="|".join(map(str, key)), array="Sigma_model_fp_check", sha256="", dtype="", shape="",
                         source=f"max rel |fp(S1V4 receipt) - fp(GEN Sigma_model)| = {float(np.max(np.abs(fp - fp_now) / np.maximum(np.abs(fp), 1e-300))):.3g}"))
    buf = io.BytesIO(); np.savez(buf, **canon)
    with zipfile.ZipFile(out / CANON_NAME, "w", compression=zipfile.ZIP_DEFLATED) as zf:     # deterministic member order
        zf.writestr("canonical.npz", buf.getvalue())
    pd.DataFrame(rows).to_csv(out / "A010_INPUT_CANONICAL_SHA.csv", index=False)
    lock = dict(file=LHALF_NAME, sha256=sha_file(out / LHALF_NAME), shape=list(L.shape), dtype=L.dtype.str, byteorder="little",
                construction="info_core.psd_sqrt(k_pose(world union poses, ell 0.5 m, 20 deg)) = V sqrt(clip(w,0)) from numpy.linalg.eigh",
                pose_ledger_sha256=hashlib.sha256("\n".join(keys).encode()).hexdigest(), n_poses=len(keys), Kp_sha256=sha_arr(Kp),
                plan_parameters_sha256=sha_file(Wd.EXP / "config/PLAN_PARAMETERS.json"),
                input_lock=(Path(os.environ.get("REFLECT_ROOT", ".")) / "out/INPUT_LOCK.sha256").read_text().splitlines()
                if (Path(os.environ.get("REFLECT_ROOT", ".")) / "out/INPUT_LOCK.sha256").exists() else "MISSING",
                canonical_inputs=dict(file=CANON_NAME, sha256=sha_file(out / CANON_NAME), cases=CASES, source_runs=[S1V4_RUN, S1V3_RUN]),
                checks=chk, generator_runner=sysinfo())
    (out / "A010_GENERATOR_FACTOR_LOCK.json").write_text(json.dumps(lock, indent=1, default=str))
    print("A010P0 GEN", "pass" if chk["pass"] else "FAIL", lock["sha256"][:12], flush=True)
    return 0 if chk["pass"] else 1


def cmd_gen_manifest(out):
    """Aggregate step of P2_A010P0_GEN: manifest over the copied GEN outputs (status = the lock's kernel check)."""
    out = Path(out); lk = lock_p0(); M.check_code_lock(lk)
    p = out / "A010_GENERATOR_FACTOR_LOCK.json"; ok = p.exists() and json.loads(p.read_text())["checks"]["pass"]
    ok = ok and (out / LHALF_NAME).exists() and sha_file(out / LHALF_NAME) == json.loads(p.read_text())["sha256"]
    MF.write_manifest(out, phase="P2_S1", status="PASS" if ok else "FAIL", contract_sha=MF.sha256_file(MF.CONTRACT),
                      config_files=[Wd.EXP / "config/PLAN_PARAMETERS.json", Wd.EXP / "contracts/AMENDMENT-010-P0.md", Wd.EXP / "contracts/AMENDMENT-010.md"],
                      input_lock=Path(os.environ.get("REFLECT_ROOT", ".")) / "out" / "INPUT_LOCK.sha256", outputs=sorted(out.glob("A010_*")),
                      seed_ledger=None, verdict="NOT_EVALUATED", unit="mathematical_deterministic",
                      limitations=["generator-factor lock and canonical inputs for the A010-P0 forensic keys", "SELF_REVIEW_ONLY"],
                      extra=dict(sub_phase="P2_A010P0_GEN", amendment="AMENDMENT-010-P0"))
    return 0 if ok else 1


# ----------------------------------------------------------------------------- ABL
def gen_dir():
    return Wd.EXP / "results" / os.environ["A010_GEN_RUN"]


def load_canon(gd):
    lock = json.loads((gd / "A010_GENERATOR_FACTOR_LOCK.json").read_text())
    if sha_file(gd / LHALF_NAME) != lock["sha256"] or sha_file(gd / CANON_NAME) != lock["canonical_inputs"]["sha256"]:
        raise SystemExit("ERR_INPUT_EXACT: Lhalf or canonical input file hash differs from the GEN lock (fail closed)")
    with zipfile.ZipFile(gd / CANON_NAME) as zf:
        with np.load(io.BytesIO(zf.read("canonical.npz")), allow_pickle=False) as z:
            canon = {k: z[k] for k in z.files}
    return lock, np.load(gd / LHALF_NAME, allow_pickle=False), canon, pd.read_csv(gd / "A010_INPUT_CANONICAL_SHA.csv")


def input_exact(cid, canon, shas):
    want = shas[(shas.case == cid) & (shas.sha256.astype(str).str.len() == 64) & ~shas.array.str.startswith("z_S1V3")]
    bad = [r.array for r in want.itertuples() if f"{cid}|{r.array}" not in canon or sha_arr(canon[f"{cid}|{r.array}"]) != r.sha256]
    return dict(n_arrays=int(len(want)), mismatched=bad, pass_=not bad and len(want) > 0)


def polish_logged(hb, z, Sm, ds_m, gy_m, dts, x0, theta, seed, tol, mx):
    """Same algorithm and seeds as s1v4.polish, with per-step objective logging (monotonicity) and a configurable tol/cap."""
    th0, thv = theta[0].copy(), theta[1].copy(); n = len(z); Lm, L0, qv = B3._mats(Sm, ds_m, dts); mu = np.zeros_like(z)
    cost = lambda a, b: FL._v2_parts(hb, z, mu, Lm, L0, x0, qv, ds_m, gy_m, dts, a, b, jac=False)[0]  # noqa: E731
    costs = [cost(th0, thv)]
    for k in range(mx):
        pf = B3.post_fit_P(hb, z, Sm, ds_m, gy_m, dts, x0, (th0, thv), np.eye(4))
        dmin, _, d = S4.probe(hb, z, Sm, ds_m, gy_m, dts, x0, (th0, thv), seed + k, pf["_gn_steps"])
        if not dmin < -tol:
            return (th0, thv), k, False, costs
        th0 = th0 + d[:4]; th0[2] = FL.wrap(th0[2]); thv = thv.copy(); thv[1:] = thv[1:] + d[4:].reshape(n - 1, 2); costs.append(cost(th0, thv))
    return (th0, thv), mx, True, costs


def solution_record(label, hb, w, inp, Sm, theta, T, extra=None):
    z, x0, ds_m, gy_m, dts = inp["z"], inp["x0"], inp["ds_m"], inp["gy_m"], w["dts"]
    Lm, L0, qv = B3._mats(Sm, ds_m, dts)
    c, X = FL._v2_parts(hb, z, np.zeros((N, 2)), Lm, L0, x0, qv, ds_m, gy_m, dts, theta[0], theta[1], jac=False)
    P10 = S4.c10_end(hb, z, Sm, ds_m, gy_m, dts, x0, theta); P10r = T @ P10 @ T.T
    pf = B3.post_fit_P(hb, z, Sm, ds_m, gy_m, dts, x0, theta, T); gn = pf.pop("_gn_steps"); pf.pop("_PA_end"); pf.pop("_X")
    dmin, which, _ = S4.probe(hb, z, Sm, ds_m, gy_m, dts, x0, theta, B3.key_seed("A010CLASS", label), gn)
    e4 = w["Xtrue"][-1] - X[-1]; e4[2] = float(FL.wrap(e4[2])); er = T @ e4
    r = dict(variant=label, cost=float(c), class_v31=S4.class_v31(pf["dec_A_fixed"], dmin), probe_min_dcost=dmin, dec_A=pf["dec_A_fixed"],
             kink_poses=B3.kink_count(X, w["taps"]), nees4_C10=float(e4 @ np.linalg.solve(P10, e4)),
             **{f"xend_{i}": float(X[-1, i]) for i in range(4)}, **{f"e_{a}": float(er[i]) for i, a in enumerate(STATES)},
             **{f"C10rot_{i}{j}": float(P10r[i, j]) for i in range(4) for j in range(i, 4)},
             C10_min_eig=float(np.linalg.eigvalsh(P10)[0]), C10_cond=float(np.linalg.cond(P10)))
    r.update(extra or {})
    return r, X, theta


def cmd_abl(cid, rep, out):
    lk = lock_p0(); M.check_code_lock(lk); out = Path(out); out.mkdir(parents=True, exist_ok=True)
    if cid not in CASES or rep not in lk["run_plan"]["A010P0"]["reps"]:
        raise SystemExit("ERR_SPLIT_LEAK: case/rep not in the AMENDMENT-010-P0 plan")
    lock, Lfrozen, canon, shas = load_canon(gen_dir()); key = CASES[cid]; f, role, cn, sn, arm = key
    S = V.setup(lk); root = M.seed_root(); w = dict(S["wins"][role])
    rep_out = dict(case=cid, rep=rep, key=key, sysinfo=sysinfo(), input_exact=input_exact(cid, canon, shas))
    if not rep_out["input_exact"]["pass_"]:
        (out / f"A010P0_ABL_{cid}_{rep}.json").write_text(json.dumps(rep_out, indent=1, default=str)); raise SystemExit("ERR_INPUT_EXACT (fail closed)")
    g = {k: canon[f"{cid}|{k}"] for k in ("z", "ds_m", "gy_m", "x0", "taps", "Xtrue", "ds_true", "dth_true", "dts", "Sigma_true", "Sigma_model", "poses")}
    w.update(taps=g["taps"], Xtrue=g["Xtrue"], dts=g["dts"])
    Sm = g["Sigma_model"]; inp = dict(z=g["z"], x0=g["x0"], ds_m=g["ds_m"], gy_m=g["gy_m"], vn=np.c_[g["ds_m"] - g["ds_true"], g["gy_m"] - g["dth_true"]])
    # GENERATOR_DISTRIBUTION: this runner's fresh eigh factor vs the frozen factor; regenerated z vs the receipt
    Kp, _, _ = world_kernel(lk); Lfresh = IC.psd_sqrt(Kp)[0]; cell = S["cells"][cn]
    regen = {}
    for nm, L in (("fresh_eigh", Lfresh), ("frozen_Lhalf", Lfrozen)):
        pf = L @ M.rng(root, S0V2.CELL_ID_V2[cn], f, 1).standard_normal((L.shape[1], 2)) if cell["alphas"][0] else None
        zz = B3.make_inputs(S, root, f, cn, S["wins"][role], sn, pf)["z"]; regen[nm] = float(np.max(np.abs(zz - g["z"])))
    rep_out["generator"] = dict(max_abs_Lfresh_minus_Lfrozen=float(np.max(np.abs(Lfresh - Lfrozen))),
                                max_abs_LLt_fresh_minus_frozen=float(np.max(np.abs(Lfresh @ Lfresh.T - Lfrozen @ Lfrozen.T))),
                                frozen_checks_on_this_runner=kernel_checks(Lfrozen, Kp), max_abs_regen_z_minus_receipt=regen,
                                cell_uses_pose_field=bool(cell["alphas"][0]))
    hb = lambda X, t=g["taps"]: Wd.h_H_tap(X, "A", t)  # noqa: E731
    h0, H0 = hb(g["Xtrue"]); rep_out["forward_ffd"] = dict(h_sha=sha_arr(h0), H_sha=sha_arr(H0))
    T = IC.rotation_rt(g["Xtrue"][-1], Wd.ANCHORS["A"]); rows = []
    t0 = time.time(); X, _, info = FL.batch_map_v2_ms(hb, inp["z"], np.zeros((N, 2)), Sm, inp["ds_m"], inp["gy_m"], w["dts"], inp["x0"], P0M)
    tE = time.time() - t0; seed = B3.key_seed("POLISH", *key)
    r, XE, _ = solution_record("E_raw", hb, w, inp, Sm, info["theta"], T, dict(tau=None, steps=0, cap=False, seconds=tE, ms_best_k=info["ms_best_k"],
                                                                                 stop_reason=info["stop_reason"]))
    rows.append(r); rep_out["forward_ffd"]["h_at_E_sha"] = sha_arr(hb(XE)[0])
    for tau, mx in [(BASE_TAU, BASE_MAX)] + [(t, TAU_MAX) for t in TAUS]:
        t0 = time.time(); th, n, cap, costs = polish_logged(hb, inp["z"], Sm, inp["ds_m"], inp["gy_m"], w["dts"], inp["x0"], info["theta"], seed, tau, mx)
        mono = bool(np.all(np.diff(costs) < 0)) if len(costs) > 1 else True
        rr, Xp, _ = solution_record(f"Ep_tau{tau:g}_max{mx}", hb, w, inp, Sm, th, T, dict(tau=tau, max_steps=mx, steps=n, cap=cap, seconds=time.time() - t0 + tE,
                                                                                          monotone=mono, cost_E=costs[0]))
        rr["E_vs_Ep_dref"] = B3.dref_diff(XE[-1], Xp[-1]); rows.append(rr)
    # perturbation negative fixture: +-1e-14 Gaussian on z must not move a well-posed solution beyond the noise; reported, not gated
    for ps in PERT_SEEDS:
        zp = inp["z"] + PERT_SIZE * np.random.default_rng(ps).standard_normal(inp["z"].shape); ip = dict(inp, z=zp)
        Xq, _, iq = FL.batch_map_v2_ms(hb, zp, np.zeros((N, 2)), Sm, inp["ds_m"], inp["gy_m"], w["dts"], inp["x0"], P0M)
        for tau in PERT_TAUS:
            th, n, cap, costs = polish_logged(hb, zp, Sm, inp["ds_m"], inp["gy_m"], w["dts"], inp["x0"], iq["theta"], seed, tau, TAU_MAX if tau < BASE_TAU else BASE_MAX)
            rr, _, _ = solution_record(f"PERT{ps}_tau{tau:g}", hb, w, ip, Sm, th, T, dict(tau=tau, steps=n, cap=cap, perturbation=PERT_SIZE, pert_seed=ps))
            rows.append(rr)
    modes = []
    if cid == "K2":                                             # R4: truth-free fixed start grid (diagnostic candidate) + ORACLE_ONLY truth start
        sd0 = np.sqrt(np.diag(P0M)); x0 = inp["x0"]; mu = np.zeros((N, 2))
        starts = {f"psi{k:+d}": (np.r_[x0[:2], FL.wrap(x0[2] + k * sd0[2]), x0[3]], np.zeros((N, 2))) for k in FL.MS_K}
        starts["x+1"] = (x0 + np.r_[sd0[0], 0, 0, 0], np.zeros((N, 2))); starts["y+1"] = (x0 + np.r_[0, sd0[1], 0, 0], np.zeros((N, 2)))
        starts["truth_ORACLE_ONLY"] = (g["Xtrue"][0].copy(), -inp["vn"])
        base = [x for x in rows if x["variant"] == f"Ep_tau{BASE_TAU:g}_max{BASE_MAX}"][0]
        for nm, th0 in starts.items():
            _, _, Is = FL.batch_map_v2(hb, inp["z"], mu, Sm, inp["ds_m"], inp["gy_m"], w["dts"], x0, P0M, theta0=th0)
            for tag, (tau, mx) in (("raw", (None, 0)), ("deep", (1e-9, TAU_MAX))):
                th = Is["theta"] if tau is None else polish_logged(hb, inp["z"], Sm, inp["ds_m"], inp["gy_m"], w["dts"], x0, Is["theta"], seed, tau, mx)[0]
                rr, Xs, _ = solution_record(f"start_{nm}_{tag}", hb, w, inp, Sm, th, T, dict(start=nm, oracle_only=nm.startswith("truth"), polish=tag))
                d = np.array([rr[f"xend_{i}"] - base[f"xend_{i}"] for i in range(4)]); d[2] = FL.wrap(d[2]); dr = T @ d
                sd = np.sqrt(np.array([base["C10rot_00"], base["C10rot_11"], base["C10rot_22"], base["C10rot_33"]]))
                rr.update(dcost_vs_Ep=rr["cost"] - base["cost"], dref_vs_Ep=float(np.max(np.abs(d) / B3.D_REF)),
                          **{f"dref_{a}": float(abs(d[i]) / B3.D_REF[i]) for i, a in enumerate(("x", "y", "psi", "bg"))},
                          **{f"dsd_{a}": float(abs(dr[i]) / sd[i]) for i, a in enumerate(STATES)})
                modes.append(rr); rr["_theta"] = th
        cand = min((m for m in modes if not m["oracle_only"] and m["polish"] == "deep"), key=lambda m: m["cost"])
        thA = polish_logged(hb, inp["z"], Sm, inp["ds_m"], inp["gy_m"], w["dts"], x0, info["theta"], seed, BASE_TAU, BASE_MAX)[0]; thB = cand["_theta"]
        Lm, L0, qv = B3._mats(Sm, inp["ds_m"], w["dts"]); prof = []
        for t in PROFILE_T:                                         # straight path in theta (x0 and v) between the two solutions
            a = thA[0] + t * (thB[0] - thA[0]); a[2] = FL.wrap(thA[0][2] + t * FL.wrap(thB[0][2] - thA[0][2]))
            b = thA[1] + t * (thB[1] - thA[1])
            prof.append(dict(t=float(t), cost=float(FL._v2_parts(hb, inp["z"], mu, Lm, L0, x0, qv, inp["ds_m"], inp["gy_m"], w["dts"], a, b, jac=False)[0])))
        cA, cB = prof[int(np.argmin(np.abs(PROFILE_T - 0)))]["cost"], prof[int(np.argmin(np.abs(PROFILE_T - 1)))]["cost"]
        inner = [p["cost"] for p in prof if 0 <= p["t"] <= 1]
        rep_out["mode_profile"] = dict(candidate=cand["variant"], cost_Ep=cA, cost_candidate=cB, barrier_above_higher_end=float(max(inner) - max(cA, cB)),
                                       monotone_between=bool(np.all(np.diff(inner) <= 1e-12)) or bool(np.all(np.diff(inner) >= -1e-12)), profile=prof,
                                       note="a straight-line profile is a diagnostic; it does not prove two modes are separate or connected")
        for m in modes:
            m.pop("_theta", None)
    for r in rows + modes:
        r.update(case=cid, rep=rep)
    rep_out["n_rows"] = len(rows); rep_out["n_modes"] = len(modes)
    pd.DataFrame(rows).to_csv(out / f"A010P0_ABL_{cid}_{rep}.csv", index=False, float_format="%.17g")
    if modes:
        pd.DataFrame(modes).to_csv(out / f"A010P0_MODES_{cid}_{rep}.csv", index=False, float_format="%.17g")
    (out / f"A010P0_ABL_{cid}_{rep}.json").write_text(json.dumps(rep_out, indent=1, default=str))
    print("A010P0 ABL", cid, rep, "rows", len(rows), "modes", len(modes), flush=True)
    return 0


# ----------------------------------------------------------------------------- aggregate
def _maxdiff(a, b, cols):
    return float(max(abs(a[c] - b[c]) for c in cols))


def h_impact(case_rows):
    """K2: effect of replacing the S1V4 row by the candidate mode on its (role, cell, arm) log inflation (H4_REPRO group)."""
    D = pd.read_csv(Wd.EXP / "results" / S1V4_RUN / "S1V4_RESULTS_DEV2.csv", low_memory=False)
    f, role, cn, sn, arm = CASES["K2"]; grp = D[(D.role == role) & (D.cell == cn) & (D.arm == arm) & (D.status == "OK")].copy()
    i = grp.index[(grp.field == f) & (grp.sensor_seed == sn)][0]; out = {}
    cand = case_rows; ix = {"rad": 0, "tan": 1, "psi": 2, "bg": 3}
    for a in ("tan", "psi"):
        base = math.log((grp[f"e_{a}"] ** 2).mean() / grp[f"P_{AJ.PRIMARY}_{a}"].mean())
        g2 = grp.copy(); g2.loc[i, f"e_{a}"] = cand[f"e_{a}"]; g2.loc[i, f"P_{AJ.PRIMARY}_{a}"] = cand[f"C10rot_{ix[a]}{ix[a]}"]
        alt = math.log((g2[f"e_{a}"] ** 2).mean() / g2[f"P_{AJ.PRIMARY}_{a}"].mean())
        out[a] = dict(log_infl_S1V4=base, log_infl_with_candidate=alt, delta=alt - base, n_rows=int(len(grp)))
    return out


def cmd_aggregate(shards, out):
    lk = lock_p0(); M.check_code_lock(lk); out = Path(out); out.mkdir(parents=True, exist_ok=True); gd = gen_dir()
    for nm in ("A010_GENERATOR_FACTOR_LOCK.json", "A010_INPUT_CANONICAL_SHA.csv"):
        (out / nm).write_bytes((gd / nm).read_bytes())
    J = {}; R = []; MO = []
    for f in sorted(glob.glob(str(Path(shards) / "**" / "A010P0_ABL_*.json"), recursive=True)):
        d = json.loads(Path(f).read_text()); J[(d["case"], d["rep"])] = d
    for f in sorted(glob.glob(str(Path(shards) / "**" / "A010P0_ABL_*.csv"), recursive=True)):
        R.append(pd.read_csv(f))
    for f in sorted(glob.glob(str(Path(shards) / "**" / "A010P0_MODES_*.csv"), recursive=True)):
        MO.append(pd.read_csv(f))
    R = pd.concat(R, ignore_index=True) if R else pd.DataFrame(); MO = pd.concat(MO, ignore_index=True) if MO else pd.DataFrame()
    R.to_csv(out / "A010_DEV2_ABLATION.csv", index=False, float_format="%.17g"); MO.to_csv(out / "A010_MODE_PROFILE.csv", index=False, float_format="%.17g")
    plan = lk["run_plan"]["A010P0"]; expected = [(c, r) for c in CASES for r in plan["reps"]]
    xcols = [f"xend_{i}" for i in range(4)]; pcols = [c for c in R.columns if c.startswith("C10rot_")] if len(R) else []
    S4R = pd.read_csv(Wd.EXP / "results" / S1V4_RUN / "S1V4_RESULTS_DEV2.csv", low_memory=False)
    diag = dict(expected_shards=len(expected), got_shards=len(J), sysinfo={f"{c}|{r}": J[(c, r)]["sysinfo"] for c, r in J}, cases={})
    for cid, key in CASES.items():
        reps = [r for r in plan["reps"] if (cid, r) in J]; c = dict(key=key)
        c["INPUT_EXACT"] = {r: J[(cid, r)]["input_exact"] for r in reps}
        c["GENERATOR_DISTRIBUTION"] = {r: J[(cid, r)]["generator"] for r in reps}
        c["FORWARD_FFD_identical_across_reps"] = len({json.dumps(J[(cid, r)]["forward_ffd"], sort_keys=True) for r in reps}) == 1 if reps else None
        cpus = {r: J[(cid, r)]["sysinfo"]["cpu"] for r in reps}; c["runner_cpus"] = cpus; c["distinct_cpu_configs"] = len(set(cpus.values()))
        same = {}
        for v in sorted(set(R[R.case == cid].variant)) if len(R) else []:
            g = R[(R.case == cid) & (R.variant == v)].set_index("rep")
            if len(g) >= 2:
                a, b = g.iloc[0], g.iloc[1]
                dx = np.array([a[k] - b[k] for k in xcols]); dx[2] = FL.wrap(dx[2])
                same[v] = dict(state_dref=float(np.max(np.abs(dx) / B3.D_REF)), cost=abs(a.cost - b.cost),
                               C10_full_rel=float(max(abs(a[k] - b[k]) / max(abs(a[k]), abs(b[k]), 1e-300) for k in pcols)) if pcols else None,
                               nees4_C10_rel=abs(a.nees4_C10 - b.nees4_C10) / abs(a.nees4_C10), class_same=a.class_v31 == b.class_v31)
        c["SAME_INPUT_SOLVER_rep_vs_rep"] = same
        s = S4R[(S4R.field == key[0]) & (S4R.role == key[1]) & (S4R.cell == key[2]) & (S4R.sensor_seed == key[3]) & (S4R.arm == key[4])]
        bv = f"Ep_tau{BASE_TAU:g}_max{BASE_MAX}"
        if len(s) and len(R):
            s = s.iloc[0]; c["SAME_INPUT_SOLVER_vs_S1V4_run"] = {}
            for r in reps:
                a = R[(R.case == cid) & (R.rep == r) & (R.variant == bv)].iloc[0]
                dx = np.array([a[f"xend_{i}"] - s[f"xend_{i}"] for i in range(4)]); dx[2] = FL.wrap(dx[2])
                c["SAME_INPUT_SOLVER_vs_S1V4_run"][r] = dict(state_dref=float(np.max(np.abs(dx) / B3.D_REF)), cost=abs(a.cost - s.cost),
                                                            nees4_C10_rel=abs(a.nees4_C10 - s.nees4_C10) / abs(s.nees4_C10), class_same=a.class_v31 == s.class_v31,
                                                            note="S1V4 run used identical input bytes (its own receipt) on another runner")
        sweep = {}
        for r in reps:
            g = R[(R.case == cid) & (R.rep == r)]
            for v in g.variant:
                if v.startswith("Ep_tau"):
                    x = g[g.variant == v].iloc[0]; sweep[f"{r}|{v}"] = dict(cost=x.cost, steps=int(x.steps), cap=bool(x.cap), monotone=bool(x.monotone), seconds=x.seconds,
                                                                           E_vs_Ep_dref=x.E_vs_Ep_dref, class_v31=x.class_v31)
            pert = {}
            for tau in PERT_TAUS:
                p = g[g.variant.str.startswith("PERT") & (g.tau == tau)]
                if len(p):
                    X = p[xcols].to_numpy(); dmax = 0.0
                    for i in range(len(X)):
                        for j in range(len(X)):
                            d = X[i] - X[j]; d[2] = FL.wrap(d[2]); dmax = max(dmax, float(np.max(np.abs(d) / B3.D_REF)))
                    pert[f"tau{tau:g}"] = dict(n=int(len(p)), state_spread_dref=dmax, cost_spread=float(p.cost.max() - p.cost.min()))
            c[f"PERTURBATION_FIXTURE_{r}"] = pert
        c["TAU_SWEEP"] = sweep
        if cid == "K2" and len(MO):
            m = MO[(MO.rep == reps[0])] if reps else MO
            cand_v = J[(cid, reps[0])]["mode_profile"]["candidate"] if reps else None
            cand = m[m.variant == cand_v].iloc[0] if cand_v else None
            amb = m[(~m.oracle_only.astype(bool)) & (m.dcost_vs_Ep.abs() <= 1.0) & (m.dref_vs_Ep > 2.0)]
            c["MODE"] = dict(candidate=cand_v, candidate_dcost_vs_Ep=float(cand.dcost_vs_Ep) if cand is not None else None,
                             candidate_dref_vs_Ep=float(cand.dref_vs_Ep) if cand is not None else None,
                             candidate_dref_by_coord={k: float(cand[f"dref_{k}"]) for k in ("x", "y", "psi", "bg")} if cand is not None else None,
                             candidate_dsd_by_state={k: float(cand[f"dsd_{k}"]) for k in STATES} if cand is not None else None,
                             AMBIGUOUS_STATE_IDENTIFICATION=bool(len(amb)), n_truth_free_solutions_ambiguous=int(len(amb)),
                             profile={k: v for k, v in J[(cid, reps[0])]["mode_profile"].items() if k != "profile"} if reps else None,
                             H4_REPRO_group_impact=h_impact(cand) if cand is not None else None,
                             rule="AMBIGUOUS iff a truth-free solution has dcost <= 1 chi^2 and end-state distance > 2 d_ref (existing NO_WRONG_BASIN / STATE_STABILITY pair)")
        diag["cases"][cid] = c
    neg = negative_fixtures(gd)
    (out / "A010_NEGATIVE_FIXTURES.json").write_text(json.dumps(neg, indent=1, default=str))
    diag["negative_fixtures_pass"] = all(v["detected"] for v in neg.values())
    (out / "A010_NUMERICAL_DIAGNOSTICS.json").write_text(json.dumps(diag, indent=1, default=float))
    ok = len(J) == len(expected) and all(all(v["pass_"] for v in c["INPUT_EXACT"].values()) for c in diag["cases"].values()) and diag["negative_fixtures_pass"]
    MF.write_manifest(out, phase="P2_S1", status="PASS" if ok else "FAIL", contract_sha=MF.sha256_file(MF.CONTRACT),
                      config_files=[Wd.EXP / "config/PLAN_PARAMETERS.json", Wd.EXP / "contracts/AMENDMENT-010-P0.md", Wd.EXP / "contracts/AMENDMENT-010.md"],
                      input_lock=Path(os.environ.get("REFLECT_ROOT", ".")) / "out" / "INPUT_LOCK.sha256", outputs=sorted(out.glob("A010_*")),
                      seed_ledger=None, verdict="NOT_EVALUATED", unit="mathematical_deterministic",
                      limitations=["forensic ablation on 4 existing DEV2 keys; not confirmatory; no estimator or threshold adopted", "SELF_REVIEW_ONLY"],
                      extra=dict(sub_phase="P2_A010P0", amendment="AMENDMENT-010-P0", gen_run=gd.name))
    print("A010P0 aggregate", "PASS" if ok else "FAIL", flush=True)
    return 0 if ok else 1


def negative_fixtures(gd):
    """Deliberately corrupted inputs must be detected (fail closed)."""
    lock, L, canon, shas = load_canon(gd); out = {}
    c2 = dict(canon); z = c2["K1|z"].copy(); z.view(np.uint64)[0, 0] ^= np.uint64(1); c2["K1|z"] = z
    out["z_one_bit_flip"] = dict(detected=not input_exact("K1", c2, shas)["pass_"])
    c3 = {k: v for k, v in canon.items() if k != "K2|taps"}
    out["missing_array"] = dict(detected=not input_exact("K2", c3, shas)["pass_"])
    L2 = L.copy(); L2[0, 0] = np.nextafter(L2[0, 0], np.inf)
    out["Lhalf_one_ulp"] = dict(detected=sha_arr(L2) != sha_arr(L) and hashlib.sha256(L2.tobytes()).hexdigest() != hashlib.sha256(L.tobytes()).hexdigest())
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("cmd"); ap.add_argument("--out", required=True); ap.add_argument("--case"); ap.add_argument("--rep")
    ap.add_argument("--shards")
    a = ap.parse_args()
    if a.cmd == "gen":
        return cmd_gen(a.out)
    if a.cmd == "abl":
        return cmd_abl(a.case, a.rep, a.out)
    return cmd_aggregate(a.shards, a.out)


if __name__ == "__main__":
    raise SystemExit(main())
