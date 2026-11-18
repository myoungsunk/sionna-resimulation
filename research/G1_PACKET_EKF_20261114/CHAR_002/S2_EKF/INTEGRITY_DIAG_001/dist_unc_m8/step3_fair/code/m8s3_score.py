"""M8 Step 3 fair-plan scoring: pinned M7 scorer functions and assess rules; accuracy reference H2 (=H2L) and H2S."""
import numpy as np, m7_score
from m7_assess import COVERAGE, assess_group, assess_seed
ARMS = ("H0", "H1", "H2", "H3", "H1S", "H2S", "F2L", "F2S", "F2SB", "F2SK", "F2SKR", "F2SKRW", "F2SKRWV")
REFS = ("H2", "H2S")
ROUTES = ("R2", "R4", "R5"); PASSES = {"R2": 2, "R4": 1, "R5": 3}


def _assess_seed(seed, groups):
    # m7_assess.assess_seed guards seed in 10..29 (M7 grid). Phase B seeds 30-49 use the identical logic with label swap.
    sa = assess_seed(seed if 10 <= seed < 30 else 10, groups); sa["seed"] = seed; return sa


def score(seed, condition, mode, traces, truth, times, *, from_trace, scores_with_blocks, branch_metrics):
    rows, branches, endpoints = {}, {}, {}
    for route in ROUTES:
        t, ref = np.asarray(times[route]), np.asarray(truth[route]); rows[route], branches[route], endpoints[route] = {}, {}, {}
        for arm in ARMS:
            tr = traces[route][arm]; assert np.array_equal(tr["t"], t)
            assert str(np.asarray(tr["metadata_condition"]).item()) == condition
            row = np.asarray(from_trace(tr, ref)); assert row.shape == (len(t), 6) and np.isfinite(row).all()
            rows[route][arm] = row
            br = branch_metrics(tr, ref, t); assert len(br["passages"]) == PASSES[route]
            branches[route][arm] = br
            end = np.asarray(tr["x"])[-1, :3] - ref[-1]; hd = np.degrees((end[2] + np.pi) % (2 * np.pi) - np.pi)
            endpoints[route][arm] = dict(heading_signed_deg=float(hd), xy_error_cm=float(100 * np.linalg.norm(end[:2])))
    pairs = [(a, r) for r in REFS for a in ARMS if a != r]
    sc = scores_with_blocks(rows, times, list(dict.fromkeys(pairs)), blocks=(5, 10, 20))
    point, b10 = sc["point"], sc["blocks"]["10"]
    assessed = {ref: {} for ref in REFS}
    for ref in REFS:
        for arm in ARMS:
            groups = {}
            for g in (*ROUTES, "pooled"):
                ci = b10["by_group"][g]; lower = {m: ci["absolute_ci95"][arm][m][0] for m in COVERAGE}; pooled = g == "pooled"
                mir = sum(branches[r][arm]["mirror_fail_count"] for r in ROUTES) if pooled else branches[g][arm]["mirror_fail_count"]
                blocks = min(b10["full_blocks"].values()) if pooled else b10["full_blocks"][g]
                groups[g] = assess_group(point[g][arm], lower, point[g][ref], pooled=pooled, effective_blocks=blocks,
                                         reference_only=bool(ci["reference_only"]), mirror_fail=mir)
            assessed[ref][arm] = _assess_seed(seed, groups)
    return dict(seed=seed, condition=condition, mode=mode, point=point,
                ci10={g: b10["by_group"][g] for g in (*ROUTES, "pooled")},
                mirror={r: {a: branches[r][a]["mirror_fail_count"] for a in ARMS} for r in ROUTES},
                endpoint=endpoints, seed_assessments=assessed)
