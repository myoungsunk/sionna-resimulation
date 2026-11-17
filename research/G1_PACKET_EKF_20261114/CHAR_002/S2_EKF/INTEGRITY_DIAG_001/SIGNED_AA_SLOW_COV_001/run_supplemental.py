"""Pre-score frozen AUXILIARY_PLAN only. Fixed primary fits; no selection."""
import argparse
import datetime as dt
import json
from pathlib import Path
import numpy as np
import covariance_core_v2 as C
from p0_inputs_v2 import sha, put, pairs_for
from p1_design_v2 import components, bin_ids
from run_covariance import read_raw, blocks, paired_report
from reference_d3 import decompose


def run(attempt):
    plan = json.loads((attempt/"AUXILIARY_PLAN.json").read_bytes())
    assert not plan["P3_result_seen"]
    p3_contract = json.loads((attempt/"p3/RUN_CONTRACT.json").read_bytes())
    audit = json.loads((attempt/"AUDIT_PRE_FIT.json").read_bytes())
    assert audit["approved_inputs"]["AUXILIARY_PLAN.json"] == sha(attempt/"AUXILIARY_PLAN.json")
    assert plan["timestamp"] < p3_contract["timestamp"]
    out = attempt/"supplemental"
    out.mkdir(exist_ok=False)
    put(out/"RUN_CONTRACT.json", dict(plan_sha256=sha(attempt/"AUXILIARY_PLAN.json"), implementation_sha256=sha(__file__),
                                     timestamp=dt.datetime.now(dt.timezone.utc).isoformat(), primary_selection=False))
    splits = json.loads((attempt/"p1_revision_02/SPLITS.json").read_bytes())
    fits = json.loads((attempt/"p3/FITS.json").read_bytes())
    sensitivity, nulls = {}, {}
    rng = np.random.default_rng(plan["N4"]["seed"])
    for route, split in splits.items():
        d = read_raw(attempt/f"P0_{route}.npz")
        if split["eligible_rho_bins"]:
            with np.load(Path("D:/SLAM_bot/artifacts/G1_CHAR002_S2_INPUTS_20261115/locked_release")/f"{route}_B0_Full_10__online.npz") as packet:
                gate = packet["trace_mask"]
                assert gate.shape == d["t"].shape
            source = Path("D:/SLAM_bot/artifacts/G1_INT_DIAG_001_20261115/continuation_d2_d3/d3")/f"B_B0_{route}.npz"
            with np.load(source) as original: supported = original["decomposition_support"]
            primary = np.zeros(len(d["t"]), bool); primary[split["test_valid_indices"]] = True
            masks = dict(gate_intersection=primary & gate, D3_support_intersection=primary & supported,
                         all_g_descriptive=np.isin(bin_ids(d), split["eligible_rho_bins"]))
            sensitivity[route] = {}
            for name, mask in masks.items():
                rows, check = C.score_models(blocks(d, components(d, mask), fits[route]["donor_mean"]), fits[route])
                sensitivity[route][name] = dict(scores=paired_report(rows, d, split), numerics=check,
                    packets=int(mask.sum()), definition="reuse primary fixed donor fit and mean; diagnostic only",
                    extrapolation_allowed_for_descriptive_allg=name == "all_g_descriptive")
        else: sensitivity[route] = dict(status="NO_SUPPORTED_PRIMARY_FIT")
        p = pairs_for(d["t"], d["a_truth"], d["rho_m"], d["arc_m"], d["yaw_arc_rad"])
        stats = {name: [] for name in ["raw_white", "smoothed_overlap", "smoothed_nonoverlap", "cross_independent_white_stream"]}
        counts = None
        for repeat in range(plan["N4"]["replicates"]):
            w1, w2 = rng.standard_normal((2, len(d["t"]), 2))
            args = [d["t"], d["arc_m"], d["yaw_arc_rad"], plan["N4"]["config"]]
            a, b = decompose(w1, *args), decompose(w2, *args)
            i, j = p["i"], p["j"]
            use = a["support"][i] & a["support"][j]
            overlap = (a["left"][i] < a["right"][j]) & (a["left"][j] < a["right"][i])
            selections = {"raw_white": use, "smoothed_overlap": use & overlap,
                          "smoothed_nonoverlap": use & ~overlap, "cross_independent_white_stream": use}
            s1, s2 = a["slow"][:, 1], b["slow"][:, 1]
            products = {"raw_white": w1[i, 1]*w1[j, 1], "smoothed_overlap": s1[i]*s1[j],
                        "smoothed_nonoverlap": s1[i]*s1[j], "cross_independent_white_stream": s1[i]*s2[j]}
            variance = float(s1[a["support"]].var())
            for name, mask in selections.items():
                if mask.any(): stats[name].append(float(products[name][mask].mean()/(1. if name == "raw_white" else variance)))
            counts = {name: int(mask.sum()) for name, mask in selections.items()}
        nulls[route] = dict(repetitions=plan["N4"]["replicates"], pair_counts=counts,
            statistics={name: dict(mean=float(np.mean(v)), MC95=np.quantile(v, [.025, .975]).tolist()) if v else dict(status="NO_PAIR_SUPPORT")
                        for name, v in stats.items()}, interpretation="synthetic smoothing artifact; MC intervals are not RF generalization intervals")
    put(out/"FIXED_FIT_SENSITIVITIES.json", sensitivity); put(out/"N4_PAIR_CONTROLS.json", nulls)
    put(out/"STATUS.json", dict(status="EXECUTION_COMPLETE", primary_selection=False))
    (out/"SHA256SUMS").write_text("".join(f"{sha(p)}  {p.name}\n" for p in sorted(out.iterdir()) if p.is_file() and p.name != "SHA256SUMS"), encoding="utf-8")
    print("Frozen supplemental controls complete", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--attempt", type=Path, required=True); run(ap.parse_args().attempt)
