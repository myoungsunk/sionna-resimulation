"""Targeted arithmetic self-check and posterior covariance supplement; no replay."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent
M6 = ROOT.parent.parent / "G1_GM_THETA_M6_20261116/attempt_02"

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def read(name):
    with (ROOT / name).open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def write(name, value):
    with (ROOT / name).open("x", encoding="utf-8") as f:
        json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write("\n")

if __name__ == "__main__":
    contract = dict(root_contract_sha256=sha(ROOT.parent / "RUN_CONTRACT.json"),
                    lane_contract_sha256=sha(ROOT / "RUN_CONTRACT.json"),
                    code_sha256=sha(__file__), scope="self-check and archived posterior covariance only")
    write("VERIFY_CONTRACT.json", contract)
    timeline = read("R5_TIMELINE.csv")
    windows = read("R5_PASSAGE_WINDOWS.csv")
    results = json.loads((ROOT / "RESULTS.json").read_text(encoding="utf-8"))
    rows, checks, sources = [], {}, {}
    for seed in range(10, 15):
        for arm in ("G1_LORO", "G1_KI"):
            path = M6 / ("seed10" if seed == 10 else "seed11_14") / f"seed{seed}/R5_{arm}.npz"
            sources[str(path)] = sha(path)
            with np.load(path, allow_pickle=False) as tr:
                selected = [r for r in timeline if int(r["seed"]) == seed and r["arm"] == arm]
                assert len(selected) == len(tr["t"])
                previous = np.r_[0., tr["b_theta"][:-1]]
                # Direct update with raw two-channel Knu, independent of conditional channel ledger.
                predicted = tr["alpha"] * previous + np.einsum("ni,ni->n", tr["K_aug"][:, 4], tr["nu"])
                error = float(np.max(np.abs(predicted - tr["b_theta"])))
                assert error < 1e-10
                for r in selected:
                    i = int(np.argmin(np.abs(tr["t"] - float(r["t_s"])))); P = tr["P_aug"][i]
                    rows.append(dict(seed=seed, arm=arm, t_s=float(tr["t"][i]),
                                     posterior_b_var_rad2=float(P[4,4]),
                                     posterior_b_x_cov_m_rad=float(P[4,0]),
                                     posterior_b_y_cov_m_rad=float(P[4,1]),
                                     posterior_b_heading_cov_rad2=float(P[4,2]),
                                     posterior_b_gyro_bias_cov_rad2_per_s=float(P[4,3])))
                for w in [r for r in windows if int(r["seed"]) == seed and r["arm"] == arm]:
                    passage = results["passages"][int(w["passage"])-1]["time_s"]
                    bounds = {"approach":(-20,-10), "pre":(-10,0), "post":(0,10), "passage":(-10,10)}[w["window"]]
                    sel = (tr["t"] >= passage+bounds[0]) & (tr["t"] < passage+bounds[1])
                    observed = np.sqrt(np.mean(np.asarray([float(r["y_error_cm"]) for r in selected])[sel]**2))
                    assert abs(observed - float(w["y_rmse_cm"])) < 1e-12
                near = [r for r in selected if r["fixed_g0_near"] == "1" and r["accepted"] == "1"]
                checks[f"{seed}/{arm}"] = dict(direct_bias_update_error_rad=error,
                    fixed_near_local_y_loss_quantiles={str(q):float(np.percentile([float(r["local_y_loss_fraction"]) for r in near],q)) for q in (50,90,95,99,100)})
    with (ROOT / "R5_POSTERIOR_COVARIANCE.csv").open("x", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    write("VERIFICATION.json", dict(status="PASS", verification_type="IMPLEMENTER_SELF_CHECK",
        root_contract_sha256=contract["root_contract_sha256"], code_sha256=sha(__file__),
        sources=sources, csv_rows=len(rows), checks=checks,
        checked_windows=len(windows), posterior_covariance_csv_sha256=sha(ROOT / "R5_POSTERIOR_COVARIANCE.csv"),
        analysis_result_sha256=sha(ROOT / "RESULTS.json")))
