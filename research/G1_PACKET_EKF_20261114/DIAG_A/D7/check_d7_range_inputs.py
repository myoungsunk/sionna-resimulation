"""Before D7, reconcile the D4 range variance with noise-free BLOCK_C taps."""
import json
import os
from pathlib import Path
from zipfile import ZipFile

os.environ["OPENBLAS_NUM_THREADS"] = "1"
import numpy as np
import pandas as pd

from check_d7_limits import d4_inputs
from diag_inputs import BASE, CASES, MANIFEST_PATH, PREP, ROOT, WORK, _r2_trace, anchor_evidence
from run_diag import write_json


def main():
    manifest = json.loads((ROOT / MANIFEST_PATH).read_text(encoding="utf-8"))
    p2_path = BASE / "original_RF_R2.zip"
    with ZipFile(p2_path) as rf:
        p2 = json.loads(rf.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))
    d4 = d4_inputs()
    meta = {row["id"]: row for row in manifest["cases"]}
    observations = pd.read_csv(PREP/"OBSERVATION_FEATURES_LABELS.csv.gz")
    out = {"classification": "DIAGNOSTIC_ONLY", "spec_commit": "f3c2717d45326f4226c4e548c0f25db116c51026",
           "basis": "D4 range residual with frozen noisy or prepared observations, paired to D4 clean full H"}
    for case in CASES:
        with np.load(WORK/"results"/case/"D4_PACKET_WINDOW.npz", allow_pickle=False) as w:
            pose, clean = w["pose"], w["range_full_m"]
            if case.startswith("R2"):
                trace = _r2_trace(case)
                observed = trace["z_r_m"]
                mu = np.zeros_like(observed)
                np.testing.assert_array_equal(w["t"], trace["t_s"])
            else:
                receipt_dir = anchor_evidence(case)
                with np.load(receipt_dir/f"{case}_full_B0_TRACE.npz", allow_pickle=False) as trace:
                    j = trace["arms"].tolist().index("JOINT4")
                    mu = trace["mu"][:, j, 0]
                    observed = observations[(observations.case == case)
                                            & (observations.channel == "full")].set_index(
                                                "pose_id").loc[trace["pose_id"], "range_m"].to_numpy()
                    np.testing.assert_array_equal(w["t"], trace["t_s"])
        anchor = meta[case]["anchor"]
        height = anchor[2] - meta[case]["robot_z_m"]
        xy = pose[:, :2] - anchor[:2]
        prediction = np.sqrt(np.sum(xy**2, axis=1) + height**2) - .5315983906250129
        error_obs = observed - mu - prediction
        error_clean = clean - mu - prediction
        extra = observed - clean
        np.testing.assert_allclose(np.var(error_obs), d4[case]["range_residual_variance_m2"],
                                   rtol=0, atol=1e-14)
        stats = lambda a: {"variance_m2": np.var(a), "mean_square_m2": np.mean(a**2)}
        out[case] = {"frames": len(pose), "clean_range_equals_observed_count": np.count_nonzero(clean == observed),
                     "observed_residual": stats(error_obs), "clean_full_residual": stats(error_clean),
                     "observed_minus_clean": stats(extra), "diff_max_abs_m": np.max(np.abs(extra)),
                     "covariance_between_clean_error_and_difference_m2":
                        np.mean((error_clean-error_clean.mean()) * (extra-extra.mean()))}
        print(case, out[case], flush=True)
    out["r2_original_summary_keys"] = list(p2)
    write_json(Path("/d7/range_input_diagnostic.json"), out)


if __name__ == "__main__":
    main()
