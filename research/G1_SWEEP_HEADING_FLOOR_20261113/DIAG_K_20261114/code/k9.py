"""G1-DIAG-002 K9: matched NR-rand horizon and separate extrapolation."""
import argparse
import csv
import hashlib
import json
from dataclasses import replace
from pathlib import Path
import sys

import numpy as np


SIGMA_BETA = (0.0, 0.05, 0.08, 0.11, 0.15, 0.25, 0.45)
BETA_NOMINAL = 0.482
SIGMA_W = 0.40
S2_DRAW_SEED = 2026111303
NR_SEED = 2026111401
LABEL = "DIAGNOSTIC_ONLY"
INPUT_HASHES = {
    "frozen_k0": "23962c097694b0084474d8682e94e59507c13c022eaaa9c068240a9b7ee8c007",
    "frozen_k3": "1f8ca024f0853059c60ae77c749f32aacc464476fad5c821cdb188531c5325fa",
    "frozen_k4": "2c8a7607fc16a2eab5160e046334f94f635f70617d8646f9de7cad71ebeb2c1a",
    "frozen_k3_driver": "a7e49380b26d2152623401e40b433eb6171424dbbe01b2c0da1d91d7bddbe853",
    "frozen_q1": "ede1a041dc275a57ca49751257d5c264f861a147e58b42166e0d737902111c3e",
    "frozen_s2_manifest": "3ecd384152e2c4b8af209ed7e54ff71a3acfd49eebeb539ef9fdfaab0a1877ce",
}


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_inputs(args, sf):
    paths = {
        "frozen_k0": args.prior / "out/K0_REPRODUCTION.json",
        "frozen_k3": args.prior / "out/K3_NR.json",
        "frozen_k4": args.prior / "out/K4_ORACLE_SCALE.json",
        "frozen_k3_driver": args.prior / "k3_k6.py",
        "frozen_q1": args.prior / "q1_sweep_rows.csv",
        "frozen_s2_manifest": args.frozen.parent / "MANIFEST.json",
    }
    digests = {}
    for key, path in paths.items():
        digests[key] = sha(path)
        if digests[key] != INPUT_HASHES[key]:
            raise ValueError(f"Frozen input SHA mismatch: {path}")
    k0 = sf.load(paths["frozen_k0"])
    if k0["status"] != "PASS" or k0["step3"] != "HELD":
        raise ValueError("K0 baseline receipt did not pass")
    manifest = sf.load(paths["frozen_s2_manifest"])
    for name in ("S1P_ERR_MODEL_LORO.json", "S2P_DRAWS.npz"):
        digest = sha(args.frozen / name)
        if digest != manifest["output_sha256"]["s2_out/" + name]:
            raise ValueError(f"Frozen S2 output SHA mismatch: {name}")
        digests[name] = digest
    return paths, digests


def path_inputs(sf, prior, stations, names, case, independent):
    prior_nr, _, _ = prior.no_repeat_paths(stations, names, case, independent, sf.SEEDS,
                                          sf.legacy.station_pool(stations))
    np.testing.assert_array_equal(prior_nr[0], np.arange(len(case)))
    rng = np.random.default_rng(NR_SEED)
    rows = {name: [] for name in names}
    for path, c in enumerate(case):
        table = stations[names[c]]["rows"]
        order = rng.permutation(len(table))
        selected = table[order, independent[path, :len(table)] % sf.SEEDS]
        np.testing.assert_array_equal(selected[:10], prior_nr[1][path])
        if len(np.unique(selected // sf.SEEDS)) != len(table):
            raise ValueError(f"Nonunique station on path {path}")
        rows[names[c]].append(selected)
    return {name: np.asarray(cases) for name, cases in rows.items()}


def standardized_dr(sf, stored):
    rng = np.random.default_rng(S2_DRAW_SEED)
    initial = rng.standard_normal(len(stored))
    beta = rng.standard_normal(len(stored))
    white = rng.standard_normal(stored.shape)
    original = 0.0 * initial[:, None] + np.cumsum(
        sf.legacy.BETA_SD * beta[:, None] + 0.486 * white, axis=1)
    np.testing.assert_array_equal(original, stored)
    return beta, white


def simulate(sf, bank, rows, paths, dr, case, rho, cal, sigma_w, sigma_beta):
    result = sf.simulate(lambda visit: bank.access(rows[:, visit], visit, paths),
                         dr, case, rho, cal, w_sd=sigma_w, beta_sd=sigma_beta)
    for key in ("err", "p_ee", "nees"):
        if not np.all(np.isfinite(result[key])):
            raise ValueError(f"Nonfinite filter result {key}")
    return result


def verify_k3(result, dr, reference):
    if int(np.count_nonzero(~result["covered"])) != reference["not_covered"]:
        raise ValueError("K3 baseline miss count differs")
    measures = np.array([np.sqrt(np.mean(result["err"]**2)),
                         np.sqrt(np.mean(dr**2)), np.mean(result["nees"])])
    pinned = np.array([reference["heading_rmse_deg"], reference["dr_rmse_deg"], reference["nees"]])
    np.testing.assert_allclose(measures, pinned, rtol=1e-11, atol=1e-12)
    return float(np.max(np.abs(measures - pinned)))


def rmse(values):
    return np.sqrt(np.mean(np.square(values), axis=0))


def dr_tail(visit, sigma_beta):
    return np.hypot(SIGMA_W * np.sqrt(visit), sigma_beta * visit)


def first_tail_crossing(n, plateau, sigma_beta):
    # Positive root of sigma_beta² * n² + SIGMA_W² * n - plateau² = 0.
    # This form is stable also at sigma_beta = 0.
    crossing = 2 * plateau**2 / (SIGMA_W**2 + np.hypot(SIGMA_W**2, 2 * sigma_beta * plateau))
    first = max(n + 1, int(np.floor(crossing)) + 1)
    while dr_tail(first, sigma_beta) <= plateau:
        first += 1
    while first > n + 1 and dr_tail(first - 1, sigma_beta) > plateau:
        first -= 1
    return first


def horizons(name, treatment, sigma_beta, g1, dr, count):
    plateau = float(np.mean(g1[-5:]))
    n = len(g1)
    observed = np.flatnonzero(dr > g1) + 1
    observed_first = int(observed[0]) if observed.size else None
    first_extended = first_tail_crossing(n, plateau, sigma_beta)
    primary = {"first_crossing_visits": observed_first or first_extended,
               "support": "OBSERVED_STATION_SUPPORT" if observed_first else "EXTRAPOLATED",
               "first_observed_crossing_visits": observed_first,
               "first_extrapolated_crossing_visits": first_extended,
               "observed_dominance_visit_count": len(observed),
               "observed_dominance_at_last_visit": bool(dr[-1] > g1[-1]),
               "observed_station_horizon": n, "paths": count,
               "last_observed_rmse_g1_deg": float(g1[-1]),
               "last_observed_rmse_dr_cal_deg": float(dr[-1]),
               "last5_g1_plateau_deg": plateau,
               "sigma_beta_deg_per_visit": sigma_beta}
    rows = []
    for visit in range(1, first_extended + 1):
        supported = visit <= n
        dr_value, g1_value = ((dr[visit - 1], g1[visit - 1]) if supported else
                              (dr_tail(visit, sigma_beta), plateau))
        rows.append(dict(classification=LABEL, case=name, calibration=treatment,
                         sigma_beta_deg_per_visit=sigma_beta, visit=visit,
                         support="OBSERVED_STATION_SUPPORT" if supported else "EXTRAPOLATED",
                         paths=count if supported else 0, rmse_g1_deg=g1_value,
                         rmse_dr_cal_deg=dr_value, ratio_g1_over_dr_cal=g1_value / dr_value,
                         dr_exceeds_g1=bool(dr_value > g1_value)))
    return primary, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("code", "inputs", "banks", "grid", "entry", "frozen", "prior", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if (args.out / "K9_HORIZON.json").exists() or (args.out / "K9_horizon.csv").exists():
        raise FileExistsError(args.out)
    sys.path[:0] = [str(args.code), str(args.prior)]
    import s2_primary_final as sf

    inputs, digests = verify_inputs(args, sf)
    import k3_k6 as prior

    names, rho, _ = sf.validate_entry(args)
    stations = sf.build_stations(args.inputs, args.banks, names)
    if tuple(len(stations[name]["gids"]) for name in names) != sf.EXPECTED:
        raise ValueError("Physical station counts changed")
    cal_data = sf.load(args.frozen / "S1P_ERR_MODEL_LORO.json")
    cal = [sf.Calibration(**cal_data[name.split("_")[0]]["calibration"]) for name in names]
    k3, k4 = [sf.load(inputs[f"frozen_{name}"]) for name in ("k3", "k4")]
    scale = prior.oracle_parameters(inputs["frozen_q1"], names, stations)
    for fresh, persisted in zip(scale, k4["oracle_parameters"], strict=True):
        assert fresh["case"] == persisted["case"]
        np.testing.assert_allclose(fresh["kappa"], persisted["kappa"], rtol=0, atol=1e-13)
    scaled = [replace(c, c_l=c.c_l * k["kappa"]) for c, k in zip(cal, scale, strict=True)]
    calibrations = {"frozen": cal, "oracle_scale": scaled}
    with np.load(args.frozen / "S2P_DRAWS.npz", allow_pickle=False) as frozen:
        np.testing.assert_array_equal(frozen["cases"], names)
        np.testing.assert_array_equal(frozen["models"], sf.MODELS)
        case = frozen["case_index"]
        xy = frozen["xy"]
        stored_dr = frozen["dr"]
        independent = frozen["nominal_rows"][sf.MODELS.index("independent")]
    assert len(case) == 200
    rows = path_inputs(sf, prior, stations, names, case, independent)
    beta, white = standardized_dr(sf, stored_dr)
    rho_by_case = list(rho.values())
    bank = sf.GroupedBank(args.inputs, args.banks, args.grid, stations, xy)
    crossing, table, controls = {}, [], {}
    try:
        for i, name in enumerate(names):
            paths = np.flatnonzero(case == i)
            n = rows[name].shape[1]
            crossing[name], controls[name] = {}, {}
            dr0 = stored_dr[paths, :10]
            for mode, params in calibrations.items():
                control = simulate(sf, bank, rows[name][:, :10], paths, dr0, case[paths],
                                   rho_by_case, params, 0.486, sf.legacy.BETA_SD)
                reference = (k3 if mode == "frozen" else k4)["arms"]["nr_rand"][name]
                controls[name][mode] = verify_k3(control, dr0, reference)
                crossing[name][mode] = []
            for sigma_beta in SIGMA_BETA:
                # The nominal r2.1.0 drift is removed in DR-cal. Keep its zero-mean residual.
                dr = np.cumsum(sigma_beta * beta[paths, None] + SIGMA_W * white[paths, :n], axis=1)
                dr_rmse = rmse(dr)
                for mode, params in calibrations.items():
                    result = simulate(sf, bank, rows[name], paths, dr, case[paths],
                                      rho_by_case, params, SIGMA_W, sigma_beta)
                    g1_rmse = rmse(result["err"])
                    summary, series = horizons(name, mode, sigma_beta, g1_rmse, dr_rmse, len(paths))
                    crossing[name][mode].append(summary)
                    table.extend(series)
            print(f"{name}: {len(paths)} paths, {n} distinct visits, K3/K4 controls matched", flush=True)
    finally:
        bank.close()

    result = {
        "question_id": "G1-DIAG-002", "classification": LABEL,
        "s2_prime_verdict": "STOP", "step3": "HELD", "spec_commit": "2068954c07770cffee1a8745e53e0383c5ef8c96",
        "prior_publication": "b070c8685e03133cfe4b846b530181acf66260b8",
        "numpy": np.__version__, "direct_code_sha256": {k: sha(args.code / k) for k in
            ("s2_primary_final.py", "run_step2.py", "v33_filter.py", "v33_observation.py", "v32_filter.py")},
        "driver_sha256": sha(Path(__file__)), "input_sha256": digests,
        "dr_model": {"revision": "r2.1.0", "nominal_beta_calibrated_deg_per_visit": BETA_NOMINAL,
                     "sigma_w_deg_per_visit": SIGMA_W, "sigma_beta_deg_per_visit": SIGMA_BETA,
                     "e0_deg": 0, "beta_residual": "run-constant zero-mean Gaussian",
                     "path_seed": S2_DRAW_SEED, "nr_order_seed": NR_SEED},
        "rmse_definition": "Per-visit root mean square over the case's assigned S2 CRN paths",
        "crossing_definition": "First strict DR-cal RMSE > G1 RMSE, even if a subsequent reversal occurs",
        "support_definition": "OBSERVED_STATION_SUPPORT uses existing BLOCK_C station visits in a simulated NR path",
        "tail_definition": "Analytic DR-cal vs mean G1 RMSE over last 5 observed visits; starts after the last observed visit.",
        "oracle_scope": "K4 modifies E1 measurement variance only; frozen AR state parameters.",
        "frozen_reference_max_abs_metrics_difference": controls, "cases": crossing,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "K9_HORIZON.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    with (args.out / "K9_horizon.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=table[0])
        writer.writeheader()
        writer.writerows(table)


if __name__ == "__main__":
    main()
