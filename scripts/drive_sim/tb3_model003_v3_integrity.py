"""MODEL-003 v3 B-method, separating integrity and harmlessness."""

import numpy as np

from tb3_model003_integrity import _path_descriptives, _prepare_level, _validate_rows


REPLICATES = 2000
SEED = 20261118


def _resample(rows, seed, replicates=REPLICATES):
    cases, seeds, sites, row_case, row_seed, row_site = _prepare_level(rows)
    values = np.asarray([[1, r["heading_included"], r["xy_included"], r["nees_heading"],
                          r["nees_xy_normalized"], r["nees_bg"], r["s_rejected"], r["s_total"],
                          r["heading_error_rad"]**2, r["xy_error_m"]**2,
                          r["dr_heading_error_rad"]**2, r["dr_xy_error_m"]**2] for r in rows], dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Nonfinite MODEL-003 v3 integrity statistic input")
    cubes = [np.zeros((len(sites[case]), len(seeds), values.shape[-1])) for case in cases]
    for i, cube in enumerate(cubes):
        match = row_case == i
        np.add.at(cube, (row_site[match], row_seed[match]), values[match])
    rng = np.random.default_rng(seed)
    samples = np.empty((replicates, values.shape[-1]))
    for b in range(replicates):
        selected_seeds = rng.integers(len(seeds), size=len(seeds))
        counts = np.bincount(selected_seeds, minlength=len(seeds))
        sample = samples[b]
        sample[:] = 0.0
        for cube in cubes:
            selected_sites = rng.integers(len(cube), size=len(cube))
            site_counts = np.bincount(selected_sites, minlength=len(cube))
            sample += np.einsum("i,j,ijk->k", site_counts, counts, cube)
    headings, xys = ["heading_rmse_rad", "xy_rmse_m"], ["heading_rmse_ratio", "xy_rmse_ratio"]

    def metrics(total):
        mean_names = ("heading_coverage", "xy_coverage", "nees_heading", "nees_xy", "nees_bg")
        summ = {name: total[..., i] / total[..., 0] for i, name in enumerate(mean_names, 1)}
        if np.all(total[..., 7] > 0):
            summ["s_rejection_rate"] = total[..., 6] / total[..., 7]
        for i, (rmse, ratio) in enumerate(zip(headings, xys, strict=True), 8):
            summ[rmse] = np.sqrt(total[..., i] / total[..., 0])
            if np.all(total[..., i+2] > 0):
                summ[ratio] = np.sqrt(total[..., i] / total[..., i+2])
        return summ

    point = {key: float(value) for key, value in metrics(values.sum(axis=0)).items()}
    ci95 = {key: np.quantile(value, [.025, .975]).tolist() for key, value in metrics(samples).items()}
    return dict(point=point, ci95=ci95)


def evaluate_level(rows, level_index, *, range_only, harmlessness_required):
    checked = _validate_rows(rows)
    base_seed = SEED + level_index*1000003
    pooled = _resample(checked, base_seed)
    by_case = {}
    for i, case in enumerate(sorted({r["case"] for r in checked})):
        subset = [row for row in checked if row["case"] == case]
        by_case[case] = _resample(subset, base_seed+1000003+i*9176)
    point, ci = pooled["point"], pooled["ci95"]
    gates = dict(
        pooled_heading_point=point["heading_coverage"] >= .92,
        pooled_heading_upper=ci["heading_coverage"][1] >= .95,
        pooled_xy_point=point["xy_coverage"] >= .90,
        mean_nees=all(.5 <= point[x] <= 2. for x in ("nees_heading", "nees_xy", "nees_bg")),
        no_severe_case=all(min(item["ci95"][k][1] for k in ("heading_coverage", "xy_coverage")) >= .80
                           for item in by_case.values()),
    )
    if not range_only:
        gates["s_used"] = point.get("s_rejection_rate", 1.) <= .20
    harms = {}
    if harmlessness_required:
        for name in ("heading_rmse_ratio", "xy_rmse_ratio"):
            harms[name] = (name in point and name in ci and point[name] <= 1.10 and ci[name][1] <= 1.25)
    return dict(integrity_pass=all(gates.values()), integrity_checks=gates,
                s_rate_applicable=not range_only, harmlessness_pass=all(harms.values()) if harms else None,
                harmlessness_checks=harms, pooled=pooled, cases=by_case,
                bootstrap=dict(replicates=REPLICATES, seed=base_seed, case_resampling=False),
                path_descriptives=_path_descriptives(checked))
