"""Small covariance-only offline core. No EKF, RF simulation, or file mutation."""
from __future__ import annotations
import numpy as np
from scipy.optimize import minimize_scalar


def kernel(arc, yaw, ell=1., yaw_deg=10.):
    return np.exp(-abs(arc[:, None]-arc[None, :])/ell-abs(yaw[:, None]-yaw[None, :])/np.radians(yaw_deg))


def matrices(K, a, model):
    if model == "S0": return [K]
    B = (a[:, None]*K)*a[None, :] if model != "S2" else (abs(a[:, None])*K)*abs(a[None, :])
    return [B] if model == "S3" else [K, B]


def covariance(K, a, model, parameters, epsilon):
    if epsilon <= 0 or any(p < 0 for p in parameters): raise ValueError("NEGATIVE_VARIANCE_OR_NONPOSITIVE_EPSILON")
    return sum(p*M for p, M in zip(parameters, matrices(K, a, model), strict=True))+epsilon*np.eye(len(a))


def validate_primary(d, definition):
    if definition != "ORIGINAL_NOISE_FREE_FULL_O30_MINUS_LOS_O30":
        raise ValueError("UNSUPPORTED_RESIDUAL_DEFINITION")
    required = ["e_rf", "s_full", "s_los", "t", "pose_id", "a_truth", "truth", "arc_m", "yaw_arc_rad", "rho_m"]
    if any(k not in d for k in required): raise ValueError("MISSING_RAW_PRIMARY_FIELDS")
    n = len(d["t"])
    if any(len(d[k]) != n for k in required): raise ValueError("PRIMARY_ALIGNMENT_MISMATCH")
    if len(np.unique(d["pose_id"])) != n or np.any(np.diff(d["t"]) <= 0): raise ValueError("PRIMARY_ID_TIME_MISMATCH")
    if any(not np.isfinite(d[k]).all() for k in required): raise ValueError("PRIMARY_NONFINITE")
    if not np.array_equal(d["e_rf"], d["s_full"]-d["s_los"]): raise ValueError("RAW_VS_M6_RESIDUAL_MISMATCH")


def logscore(e, C):
    L = np.linalg.cholesky(C)
    z = np.linalg.solve(L, e)
    return float(-.5*(2*np.log(np.diag(L)).sum()+z@z+len(e)*np.log(2*np.pi)))


def preliminary_q0(blocks):
    """Donor S0 scale MLE, pseudodeterminant only at exact repeated coordinates.

    Same-pose RF is one deterministic realization. Nullspace residual energy is
    checked before pseudoinverse use; epsilon is not increased to hide defects.
    """
    total, rank, null_energy = 0., 0, 0.
    for row in blocks:
        vals, V = np.linalg.eigh(row["K"])
        assert vals.min() >= -1e-10, "K_NOT_PSD"
        positive = vals > 1e-12*max(1., vals.max())
        z = V.T@row["e"]
        total += float((z[positive]**2/vals[positive]).sum())
        null_energy += float((z[~positive]**2).sum())
        rank += int(positive.sum())
    if null_energy > 1e-10*max(1., sum(float(r["e"]@r["e"]) for r in blocks)):
        raise ValueError("S0_NULLSPACE_RESIDUAL_UNSUPPORTED")
    assert rank > 0
    return max(total/rank, 0.), dict(rank=rank, nullspace_energy=null_energy)


def fit_one(blocks, model, epsilon):
    """Profile total scale and fixed mixing fraction; no heldout argument.

    r-grid 0,.05,...,1 plus bounded refinement of its best adjacent interval.
    Nested boundaries are explicit candidates. S0/S3 have one free scale.
    """
    n = sum(len(r["e"]) for r in blocks)
    if not n: raise ValueError("NO_DONOR_PACKETS")
    v = max(sum(float(r["e"]@r["e"]) for r in blocks)/n, 1e-12)
    cache = {}
    def profile(r):
        key = float(r)
        if key in cache: return cache[key]
        spectral = []
        for row in blocks:
            Ms = matrices(row["K"], row["a"], model)
            M = Ms[0] if len(Ms) == 1 else (1-r)*Ms[0]+r*Ms[1]
            vals, V = np.linalg.eigh(M)
            if vals.min() < -1e-10*max(1., abs(vals).max()): raise ValueError("MODEL_NOT_PSD")
            spectral.append((np.maximum(vals, 0), (V.T@row["e"])**2))
        def objective(log_scale):
            scale = np.exp(log_scale)
            return .5*sum(float(np.sum(np.log(scale*w+epsilon)+zz/(scale*w+epsilon))) for w, zz in spectral)/n
        result = minimize_scalar(objective, bounds=(np.log(v)-25, np.log(v)+25), method="bounded", options={"xatol": 1e-9})
        if not result.success: raise ValueError("SCALE_OPTIMIZER_FAILED")
        entry = (float(result.fun), float(np.exp(result.x)), float(r))
        cache[key] = entry; return entry
    if model in ["S0", "S3"]:
        best = profile(0.)
        parameters = [best[1]]
    else:
        grid = np.linspace(0, 1, 21)
        candidates = [profile(float(r)) for r in grid]
        best_index = int(np.argmin([x[0] for x in candidates]))
        lo, hi = grid[max(0, best_index-1)], grid[min(20, best_index+1)]
        refined = minimize_scalar(lambda r: profile(r)[0], bounds=(lo, hi), method="bounded", options={"xatol": 1e-7})
        if not refined.success: raise ValueError("MIX_OPTIMIZER_FAILED")
        best = min(candidates+[profile(float(refined.x))], key=lambda x: x[0])
        parameters = [best[1]*(1-best[2]), best[1]*best[2]]
    return dict(model=model, parameters=list(map(float, parameters)), donor_objective_per_packet=best[0],
                mixing_fraction=best[2], effective_parameters=len(parameters),
                theta_boundary=bool(model in ["S1", "S2"] and best[2] == 0.),
                profile_evaluations=len(cache), optimizer="fixed 21-point mix grid + scalar bounded refinement")


def fit_models(blocks):
    q0, initial = preliminary_q0(blocks)
    epsilon = 1e-8*max(q0, 1e-6)
    fits = {m: fit_one(blocks, m, epsilon) for m in ["S0", "S1", "S2", "S3"]}
    return dict(epsilon=epsilon, donor_preliminary_q0=q0, preliminary_check=initial, models=fits)


def score_models(blocks, fit):
    rows = []
    max_condition, cholesky_failures = 0., 0
    for block in blocks:
        row = dict(cluster=block["cluster"], time=block["time"], n=len(block["e"]), scores={})
        for name, params in fit["models"].items():
            C = covariance(block["K"], block["a"], name, params["parameters"], fit["epsilon"])
            max_condition = max(max_condition, float(np.linalg.cond(C)))
            try: row["scores"][name] = logscore(block["e"], C)
            except np.linalg.LinAlgError:
                cholesky_failures += 1; raise
        rows.append(row)
    return rows, dict(max_condition=max_condition, cholesky_failures=cholesky_failures)


def cluster_ci(rows, groups, seed=20261116, repetitions=2000):
    # Same linked cluster draws for all models. No resampling of individual pairs.
    totals = []
    for group in groups:
        selected = [r for r in rows if r["cluster"] in group]
        if selected:
            totals.append([sum(r["n"] for r in selected)]+[sum(r["scores"][m] for r in selected) for m in ["S0", "S1", "S2", "S3"]])
    arr = np.array(totals, float)
    if len(arr) < 3: return dict(status="INCONCLUSIVE_FEWER_THAN_3_CLUSTERS", groups=len(arr))
    rng = np.random.default_rng(seed)
    draw = rng.integers(0, len(arr), (repetitions, len(arr)))
    sample = arr[draw].sum(axis=1)
    scores = sample[:, 1:]/sample[:, :1]
    mean = arr[:, 1:].sum(axis=0)/arr[:, 0].sum()
    diffs = {"delta10": scores[:, 1]-scores[:, 0], "delta12": scores[:, 1]-scores[:, 2]}
    return dict(status="COMPUTED", groups=len(arr), packets=int(arr[:, 0].sum()),
                mean_scores=dict(zip(["S0", "S1", "S2", "S3"], map(float, mean))),
                delta10=dict(mean=float(mean[1]-mean[0]), ci95=np.quantile(diffs["delta10"], [.025, .975]).tolist()),
                delta12=dict(mean=float(mean[1]-mean[2]), ci95=np.quantile(diffs["delta12"], [.025, .975]).tolist()))
