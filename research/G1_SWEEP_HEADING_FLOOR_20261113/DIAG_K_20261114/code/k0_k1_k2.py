"""G1-DIAG-002 K0 and read-only K1/K2 summaries of a passed K0."""
import argparse
import csv
import hashlib
import json
import platform
from pathlib import Path
import sys
from datetime import datetime, timezone
from dataclasses import asdict

import numpy as np

EXPECTED_MISSES = {"independent": 361, "markov": 531, "cell": 568}
HORIZON = 17
SPEC = "2068954c07770cffee1a8745e53e0383c5ef8c96"
BASELINE = "d7a3529"
GOVERNANCE = {
    "common": "a5cca7d8a8d5f20f4a89ea9b6509da0b8d7506626aac4a47fa1d27891ff5ebdb",
    "implementer": "2380fb1fe7302870a6c2d825cc2e65a73e91138677e095b4e51db43ab9ea90da",
}


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dump(path, result):
    with path.open("x", encoding="utf-8") as out:
        json.dump(result, out, ensure_ascii=False, indent=2, allow_nan=False)
        out.write("\n")


def now():
    return datetime.now(timezone.utc).isoformat()


def endpoint_stats(data, selected):
    err = data["err"][selected, :HORIZON]
    p_ee = data["p_ee"][selected, :HORIZON]
    covered = data["covered"][selected, :HORIZON]
    return {
        "misses": int(np.count_nonzero(~covered)),
        "rmse_deg": float(np.sqrt(np.mean(err**2))),
        "mean_halfwidth_deg": float(np.mean(1.96 * np.sqrt(p_ee))),
    }


def relative_diff(live, frozen):
    if frozen == 0:
        return 0.0 if live == 0 else None
    return abs(live - frozen) / abs(frozen)


def k0(args, sf):
    t0 = now()
    manifest_path = args.frozen.parent / "MANIFEST.json"
    source = sf.load(manifest_path)
    assert sha(manifest_path) == "3ecd384152e2c4b8af209ed7e54ff71a3acfd49eebeb539ef9fdfaab0a1877ce"
    files = ("S2P_NOMINAL.npz", "S2P_DRAWS.npz", "S1P_ERR_MODEL_LORO.json",
             "CODE_primary_SHA256.txt")
    for name in files:
        assert sha(args.frozen / name) == source["output_sha256"]["s2_out/" + name], name
    names, rho, _ = sf.validate_entry(args)
    station = sf.build_stations(args.inputs, args.banks, names)
    receipt = sf.load(args.frozen / "S1P_ERR_MODEL_LORO.json")
    cal = [sf.Calibration(**receipt[name.split("_")[0]]["calibration"]) for name in names]
    case, dr, xy, nominal, outer, sampled = sf.pools_and_draws(station, rho)
    live_draws = dict(cases=np.array(names), models=np.array(sf.MODELS), case_index=case,
                      dr=dr, xy=xy, nominal_rows=nominal, outer_rows=outer,
                      outer_station_indices=sampled)
    with np.load(args.frozen / "S2P_DRAWS.npz", allow_pickle=False) as frozen:
        checks = {key: np.array_equal(frozen[key], arr) for key, arr in live_draws.items()}
    if not all(checks.values()):
        dump(args.out / "K0_REPRODUCTION.json", {
            "label": "DIAGNOSTIC_ONLY", "status": "FAIL", "draws_exact": checks,
            "spec_commit": SPEC, "baseline_commit": BASELINE, "started_utc": t0,
            "finished_utc": now(), "step3": "HELD"})
        return False
    del outer, sampled, live_draws
    for name, data in station.items():
        index = sf.load(args.grid / f"S1P_{name}_M1R_JOINT_INDEX.json")
        np.testing.assert_array_equal([g["group"] for g in index["groups"]], data["gids"])
        for axis in ("x", "y"):
            np.testing.assert_array_equal([g[axis] for g in index["groups"]], data[axis])
    bank = sf.GroupedBank(args.inputs, args.banks, args.grid, station, xy)
    live = {}
    try:
        for i, model in enumerate(sf.MODELS):
            rows = nominal[i]
            live[model] = sf.simulate(lambda k: bank.access(rows[:, k], k), dr, case,
                                      list(rho.values()), cal)
            print("K0 nominal simulated", model, flush=True)
        cache = bank.stats()
    finally:
        bank.close()
    args.out.joinpath("K0_NOMINAL.npz").open("xb").close()
    np.savez_compressed(args.out / "K0_NOMINAL.npz", case_index=case, dr=dr, cases=names,
                        **{f"{m}_{k}": live[m][k] for m in sf.MODELS for k in sf.KEYS})
    by_model = {}
    passed = True
    with np.load(args.frozen / "S2P_NOMINAL.npz", allow_pickle=False) as frozen:
        np.testing.assert_array_equal(frozen["case_index"], case)
        np.testing.assert_array_equal(frozen["cases"], names)
        np.testing.assert_array_equal(frozen["dr"], dr)
        for model in sf.MODELS:
            expect = {key: frozen[f"{model}_{key}"] for key in sf.KEYS}
            actual = live[model]
            matches = {key: np.array_equal(actual[key], expect[key], equal_nan=True)
                       for key in sf.KEYS}
            count = int(np.count_nonzero(~actual["covered"][:, :HORIZON]))
            frozen_count = int(np.count_nonzero(~expect["covered"][:, :HORIZON]))
            total_pass = count == frozen_count == EXPECTED_MISSES[model]
            by_case = {}
            for i, name in enumerate(names):
                new = endpoint_stats(actual, case == i)
                old = endpoint_stats(expect, case == i)
                diffs = {k: relative_diff(new[k], old[k])
                         for k in ("rmse_deg", "mean_halfwidth_deg")}
                ok = (new["misses"] == old["misses"] and
                      all(d is not None and d <= 1e-9 for d in diffs.values()))
                by_case[name] = {"live": new, "frozen": old, "relative_diff": diffs, "pass": ok}
            covered_match = matches["covered"]
            passed &= total_pass and covered_match and all(c["pass"] for c in by_case.values())
            by_model[model] = {
                "total_misses": count, "frozen_total_misses": frozen_count,
                "expected_total_misses": EXPECTED_MISSES[model], "total_pass": total_pass,
                "array_equal_all_50_visits": matches, "cases": by_case}
    dump(args.out / "K0_REPRODUCTION.json", {
        "label": "DIAGNOSTIC_ONLY", "status": "PASS" if passed else "FAIL",
        "question": "G1-DIAG-002", "role": "IMPLEMENTER",
        "spec_commit": SPEC, "baseline_commit": BASELINE, "governance_sha256": GOVERNANCE,
        "python": platform.python_version(), "numpy": np.__version__,
        "arguments": sys.argv, "started_utc": t0, "finished_utc": now(),
        "source_manifest_sha256": sha(manifest_path),
        "horizon": HORIZON, "paths": len(case), "draws_exact": checks,
        "frozen_files_sha256": {name: sha(args.frozen / name) for name in files},
        "driver_sha256": sha(Path(__file__)), "reproduced_npz_sha256": sha(args.out / "K0_NOMINAL.npz"),
        "calibration": {name: asdict(c) for name, c in zip(names, cal)},
        "rho": rho, "cache": cache, "models": by_model, "step3": "HELD"})
    print("K0", "PASS" if passed else "FAIL", {m: d["total_misses"] for m, d in by_model.items()}, flush=True)
    return passed


def finite_mean(values):
    good = values[np.isfinite(values)]
    return float(np.mean(good)) if good.size else None


def metrics(observed, mask):
    n = int(np.count_nonzero(mask))
    if not n:
        return {"n": 0, "coverage": None, "misses": 0, "mean_nees": None}
    covered = observed["covered"][mask]
    return {"n": n, "coverage": float(np.mean(covered)),
            "misses": int(np.count_nonzero(~covered)),
            "mean_nees": finite_mean(observed["nees"][mask])}


def k1_k2(args, sf):
    k0_record = sf.load(args.out / "K0_REPRODUCTION.json")
    if k0_record["status"] != "PASS" or k0_record["spec_commit"] != SPEC:
        raise RuntimeError("K0 must pass for this spec before K1 or K2")
    verified_npz = args.out / "K0_NOMINAL.npz"
    if sha(verified_npz) != k0_record["reproduced_npz_sha256"]:
        raise RuntimeError("K0 nominal hash mismatch")
    by_arm, revisits = {}, {}
    with np.load(verified_npz, allow_pickle=False) as res, np.load(args.frozen / "S2P_DRAWS.npz", allow_pickle=False) as draws:
        names, case, rows = res["cases"], res["case_index"], draws["nominal_rows"]
        np.testing.assert_array_equal(case, draws["case_index"])
        for j, model in enumerate(sf.MODELS):
            observed = {key: res[f"{model}_{key}"][:, :HORIZON] for key in sf.KEYS}
            sites = rows[j, :, :HORIZON] // len(sf.SEEDS)
            occurrence = 1 + np.sum(
                (sites[:, :, None] == sites[:, None, :]) &
                np.tri(HORIZON, k=-1, dtype=bool), axis=-1)
            distinct = np.sum(occurrence == 1, axis=1)
            before_first_revisit = np.cumsum(occurrence > 1, axis=1) == 0
            by_arm[model], revisits[model] = {}, {}
            for i, name in enumerate(names):
                chosen = case == i
                mask = np.broadcast_to(chosen[:, None], occurrence.shape)
                row = endpoint_stats(observed, chosen)
                row.update(metrics(observed, mask))
                row["rmse_deg"] = float(np.sqrt(np.mean(observed["err"][mask]**2)))
                row["mean_error_deg"] = finite_mean(observed["err"][mask])
                row["rms_z"] = float(np.sqrt(row["mean_nees"])) if row["mean_nees"] is not None else None
                row["distinct_stations_q25_median_q75"] = np.quantile(distinct[chosen], [.25, .5, .75]).tolist()
                row["coverage_by_visit"] = np.mean(observed["covered"][chosen], axis=0).tolist()
                by_arm[model][name] = row
                revisits[model][name] = {
                    "first": metrics(observed, mask & (occurrence == 1)),
                    "second": metrics(observed, mask & (occurrence == 2)),
                    "third_or_later": metrics(observed, mask & (occurrence >= 3)),
                    "before_first_revisit": metrics(observed, mask & before_first_revisit)}
    label = "DIAGNOSTIC_ONLY"
    cell_total = sum(r["misses"] for r in by_arm["cell"].values())
    dump(args.out / "K1_CASE_ARM.json", {"label": label, "horizon": HORIZON,
         "models": by_arm, "cell_r4_aB_miss_fraction": by_arm["cell"]["R4_aB_m0"]["misses"] / cell_total})
    dump(args.out / "K2_REVISIT_SPLIT.json", {"label": label, "horizon": HORIZON, "models": revisits})
    with (args.out / "K1_CASE_ARM.csv").open("x", newline="", encoding="utf-8") as stream:
        fields = ["label", "model", "case", "n", "misses", "coverage", "mean_nees", "rms_z",
                  "rmse_deg", "mean_error_deg", "mean_halfwidth_deg",
                  "distinct_q25", "distinct_median", "distinct_q75"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for model, cases in by_arm.items():
            for name, row in cases.items():
                data = {field: row[field] for field in fields if field in row}
                q25, q50, q75 = row["distinct_stations_q25_median_q75"]
                writer.writerow(dict(data, label=label, model=model, case=name,
                                     distinct_q25=q25, distinct_median=q50, distinct_q75=q75))
    print("K1/K2 complete", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["k0", "k1_k2"])
    for path in ("code", "inputs", "banks", "grid", "entry", "frozen", "out"):
        parser.add_argument(f"--{path}", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.code))
    import s2_primary_final as sf
    if args.phase == "k0":
        return 0 if k0(args, sf) else 2
    k1_k2(args, sf)
    return 0


if __name__ == "__main__":
    sys.exit(main())
