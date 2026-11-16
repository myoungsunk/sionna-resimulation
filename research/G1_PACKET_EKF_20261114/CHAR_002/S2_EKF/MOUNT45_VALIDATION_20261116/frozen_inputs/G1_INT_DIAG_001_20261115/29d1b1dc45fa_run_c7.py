"""C7 donor-only diagnostic with committed G-T1 simulated yaw sweeps."""
import argparse
import csv
import gzip
import hashlib
import io
import json
import platform
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy
from scipy.optimize import nnls


HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE.parents[1]
SLAM = ARTIFACTS.parents[1]
KS = ARTIFACTS / "continuation_ks"
CHECKOUT = SLAM / "g1_int_diag001_publication_20261115"
REVISION = "8305058bcea6a0e29b45675ea148bfa0ee85aa0c"
RESEARCH = "research/G1_PACKET_EKF_20261114"
DIAG = f"{RESEARCH}/CHAR_002/S2_EKF/INTEGRITY_DIAG_001"
CHAR_OUT = f"{RESEARCH}/CHAR_001/out"
POSES = "research/G1_RT_TB3_CORRIDOR_20261113/evidence/G0/poses"
S2_CONTRACT = f"{RESEARCH}/CHAR_002/S2_EKF/run_20261115_a/RUN_CONTRACT.json"
CONTRACT_PATH = HERE / "RUN_CONTRACT_C7.json"
ROUTES = ("R2", "R4", "R5")
SETS = ("P-A_TEACH", "P-A_REPEAT")
RULES = dict(
    bin_edges_m=[1.5, 3., 6., 10.], yaw_half_window_deg=5., min_distinct_yaw=3,
    min_stations_for_fit=2, diagnostic_ratio_reference=[.5, 2.],
    geometry="horizontal d from donor truth XY and G-T1 anchor coordinates; V8 eval uses LORO prior XY",
    yaw="dense49 achieved relative degrees; no wrapping between sweep endpoints",
    weighting="each physical station gets equal total weight per bin across its anchor views",
    fit_target="square of within-anchor/station-centered smoothed full-minus-LoS O30 s",
    train="TEACH primary; REPEAT paired sensitivity only, fitted separately with no pooling",
    sensitivity_unit="abs CSV g_psi per degree times 180/pi; V8 uses abs H_s,yaw per radian",
    scope="SIMULATED_RT_PROXY_ONLY; no field RF, no KF update or admission rerun",
)


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def blob(path):
    return subprocess.check_output(["git", "-C", str(CHECKOUT), "show", f"{REVISION}:{path}"])


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as file:
        json.dump(value, file, indent=2, allow_nan=False)
        file.write("\n")


def freeze(trigger_record):
    trigger_receipt = trigger_record.parent / "EXECUTION.json"
    trigger_digest = sha(trigger_record)
    if (read(trigger_receipt)["outputs"][trigger_record.name] != trigger_digest
            or read(trigger_record)["disposition"]["conservative"]["status"] != "FAIL"):
        raise ValueError("C7 requires a verified failed C5 conservative transfer")
    ks_contract = KS / "RUN_CONTRACT_RETRY_03.json"
    lock = read(ks_contract)
    frozen = {rec["path"]: rec["sha256"] for rec in lock["inputs"]}
    evidence = read(KS / "run_03" / "EXECUTION.json")
    git_sources = [S2_CONTRACT, f"{CHAR_OUT}/EXTRACT_MANIFEST.json", f"{RESEARCH}/CHAR_001/scripts/char_extract.py"]
    s2_pins = json.loads(blob(S2_CONTRACT))["fit_sweep_inputs"]
    donor_records, sample_records = {}, {}
    for anchor in "ABC":
        donor_csv = f"{CHAR_OUT}/ERRORS_G-T1_{anchor}.csv.gz"
        frozen_samples = next(Path(name) for name in s2_pins if Path(name).parent.name == f"G-T1_{anchor}" and Path(name).name == "SAMPLES.json")
        expected_csv = next(value for name, value in s2_pins.items() if Path(name).name == Path(donor_csv).name)
        expected_samples = s2_pins[str(frozen_samples)]
        if digest(blob(donor_csv)) != expected_csv or sha(frozen_samples) != expected_samples:
            raise ValueError(f"S2 sweep pin mismatch: {anchor}")
        donor_records[donor_csv] = expected_csv
        sample_records[f"{POSES}/G-T1_{anchor}/SAMPLES.json"] = {"path": str(frozen_samples), "sha256": expected_samples}
    local_records = {
        str(KS / "run_03" / "V8.json"): evidence["outputs"]["V8.json"],
        str(ARTIFACTS / "RUN_CONTRACT.json"): frozen[str(ARTIFACTS / "RUN_CONTRACT.json")],
    }
    for route in ROUTES:
        for key in (f"attempt_02/d5/B_B0_{route}.npz", f"continuation_d2_d3/d2/B_B0_{route}.npz"):
            path = str(ARTIFACTS / key)
            local_records[path] = frozen[path]
        for path, hash_value in frozen.items():
            if Path(path).name == f"{route}_B0_Full_10__online.npz":
                local_records[path] = hash_value
    if len(local_records) != 11:
        raise ValueError("Missing or duplicate frozen holdout inputs")
    sources = {}
    for rec in [*lock["inputs"], *lock["derived_sources"]]:
        name = Path(rec["path"]).name
        if name in ("ks_fit.py", "d3.py", "replay_s2.py"):
            sources[name] = rec
    if set(sources) != {"ks_fit.py", "d3.py", "replay_s2.py"}:
        raise ValueError("Missing inherited replay sources")
    for path, expected in local_records.items():
        if sha(path) != expected:
            raise ValueError(f"Frozen holdout input mismatch: {path}")
    write(CONTRACT_PATH, dict(
        question="G1-INT-001/KS-TRANSFER/C7", role="IMPLEMENTER",
        repository="myoungsunk/sionna-resimulation", branch="research/g1-sweep-heading-floor-spec-20261113",
        commit=REVISION, frozen_utc=now(), rules=RULES,
        trigger={"basis": "C5 unmet Goal 1 gates; parent validated execution before C7",
                 "path": str(trigger_record), "sha256": trigger_digest,
                 "parent_receipt": str(trigger_receipt), "receipt_sha256": sha(trigger_receipt)},
        runner_sha256=sha(Path(__file__)), governance=lock["governance"],
        source_s2_v8_contract_sha256=sha(ks_contract),
        committed_donor_files={**{p: digest(blob(p)) for p in git_sources}, **donor_records},
        frozen_donor_pose_files=sample_records,
        donor_pose_release_note="Use original S2 G-T1 production sample JSON pinned by SHA; repository G0 sample snapshots differ.",
        frozen_holdout_files=local_records, inherited_sources=sources,
    ))


def yaw_smooth(yaw, residual, rules):
    order = np.argsort(yaw)
    if len(np.unique(np.round(yaw, 9))) != len(yaw):
        raise ValueError("Duplicate yaw within a dense49 sweep")
    sorted_yaw = yaw[order]
    separation = np.abs(yaw[:, None] - sorted_yaw[None, :])
    inside = separation <= rules["yaw_half_window_deg"] + 1e-10
    counts = inside.sum(axis=1)
    supported = counts >= rules["min_distinct_yaw"]
    centered = residual[order] - residual.mean()
    slow = np.full(len(yaw), np.nan)
    if supported.any():
        slow[supported] = (inside[supported] @ centered) / counts[supported]
        slow[supported] -= slow[supported].mean()
        assert abs(float(slow[supported].mean())) <= 1e-12
    return slow, supported, counts


def fetch_donors(committed, rules):
    extract = json.loads(committed[f"{CHAR_OUT}/EXTRACT_MANIFEST.json"])
    donors = []
    for anchor in "ABC":
        geometry = next(row for row in extract["cases"] if row["case"] == f"G-T1_{anchor}")
        csv_path = f"{CHAR_OUT}/ERRORS_G-T1_{anchor}.csv.gz"
        sample_path = f"{POSES}/G-T1_{anchor}/SAMPLES.json"
        with gzip.GzipFile(fileobj=io.BytesIO(committed[csv_path])) as zipped:
            rows = {int(row["pose_id"]): row for row in csv.DictReader(io.TextIOWrapper(zipped, encoding="utf-8-sig"))}
        if len(rows) != geometry["poses"] or geometry["mount"] != 0:
            raise ValueError("G-T1 donor inventory or mount mismatch")
        groups = defaultdict(list)
        for sample in json.loads(committed[sample_path]):
            use = sample["set"] in SETS and sample["protocol"] == "dense49"
            if use:
                groups[sample["set"], sample["station_id"]].append(sample)
        if Counter(key[0] for key in groups) != {run: 18 for run in SETS}:
            raise ValueError("Missing or extra dense49 stations")
        for (run, station), sample in sorted(groups.items()):
            csv_rows = [rows[pose["pose_id"]] for pose in sample]
            if len(sample) != 49 or any(pose["motion"] != "in_place" for pose in sample):
                raise ValueError("Station is not the frozen dense49 in-place sweep")
            xya = np.array([[p["x"], p["y"], p["yaw_body_deg"]] for p in sample])
            np.testing.assert_allclose(xya, [[float(row[k]) for k in ("x", "y", "yaw")] for row in csv_rows],
                                       atol=1e-9, rtol=0.)
            if not np.all(xya[:, :2] == xya[0, :2]):
                raise ValueError("Station location moves during yaw sweep")
            x, y = xya[0, :2]
            distance = float(np.linalg.norm(xya[0, :2] - np.asarray(geometry["anchor"][:2])))
            np.testing.assert_allclose([float(row["d"]) for row in csv_rows],
                                       np.hypot(distance, geometry["anchor"][2] - .45), atol=1e-9, rtol=0.)
            yaw = np.array([p["achieved_rel_deg"] for p in sample])
            g = np.abs(np.array([float(row["g_psi"]) for row in csv_rows])) * (180. / np.pi)
            es = np.array([float(row["e_s"]) for row in csv_rows])
            np.testing.assert_allclose(es, [float(row["s_full"]) - float(row["s_los"]) for row in csv_rows],
                                       atol=1e-12, rtol=0.)
            if not np.isfinite(g).all() or not np.isfinite(es).all():
                raise ValueError("Sweep contains nonfinite polarization/sensitivity")
            slow, support, counts = yaw_smooth(yaw, es, rules)
            donors.extend(dict(role=run, station=station, anchor=anchor, pose_id=p["pose_id"], x_m=x, y_m=y,
                               d_xy_m=distance, relative_yaw_deg=yaw[i], g_per_rad=g[i], e_s=es[i],
                               e_s_slow=float(slow[i]) if support[i] else None, window_n=int(counts[i]))
                          for i, p in enumerate(sample))
    return donors


def summarize_fit(donors, rules):
    bins = np.asarray(rules["bin_edges_m"])
    fits = {}
    for role in SETS:
        fits[role] = []
        for low, high in zip(bins[:-1], bins[1:], strict=True):
            groups = defaultdict(list)
            for row in donors:
                if row["role"] == role and low <= row["d_xy_m"] < high and row["e_s_slow"] is not None:
                    groups[row["station"]].append(row)
            design = []
            response = []
            samples = []
            views = set()
            for station, rows in sorted(groups.items()):
                g = np.array([row["g_per_rad"] for row in rows])
                slow = np.array([row["e_s_slow"] for row in rows])
                weight = 1 / np.sqrt(len(rows))
                design.append(weight * np.column_stack([np.ones(len(rows)), g ** 2]))
                response.append(weight * slow ** 2)
                samples.extend(g)
                views.update((station, r["anchor"]) for r in rows)
            g = np.asarray(samples)
            matrix = np.vstack(design) if design else np.empty((0, 2))
            rank = int(np.linalg.matrix_rank(matrix)) if len(matrix) else 0
            beta = nnls(matrix, np.concatenate(response))[0].tolist() if (
                rank == 2 and len(groups) >= rules["min_stations_for_fit"]) else None
            fits[role].append(dict(distance_m=[low, high], physical_stations=len(groups),
                                   station_anchor_views=len(views), yaw_centers=len(g), rank=rank,
                                   station_ids=sorted(groups), beta=beta,
                                   g_min=float(g.min()) if len(g) else None,
                                   g_max=float(g.max()) if len(g) else None,
                                   g_p95=float(np.quantile(g, .95)) if len(g) else None))
    return fits


def holdout_rows(contract, fit):
    paths = list(map(Path, contract["frozen_holdout_files"]))
    for src in contract["inherited_sources"].values():
        sys.path.insert(0, str(Path(src["path"]).parent))
    from d3 import motion_arcs
    from ks_fit import _indices, _prepare, _support

    def npz(name, parent=None):
        picks = [path for path in paths if path.name == name and (parent is None or path.parent.name == parent)]
        if len(picks) != 1:
            raise ValueError(f"Input reference missing or duplicated: {name} / {parent}")
        with np.load(picks[0], allow_pickle=False) as data:
            return dict(data)

    reference = read(KS / "run_03" / "V8.json")["rows"]
    anchor = np.asarray(read(ARTIFACTS / "RUN_CONTRACT.json")["anchors"]["B"][:2])
    results = []
    for route in ROUTES:
        d2 = npz(f"B_B0_{route}.npz", "d2")
        loro = npz(f"B_B0_{route}.npz", "d5")
        packet = npz(f"{route}_B0_Full_10__online.npz")
        for field in ("t", "pose_id"):
            np.testing.assert_array_equal(d2[field], loro[field])
            np.testing.assert_array_equal(packet[field], loro[field])
        np.testing.assert_array_equal(d2["mask"], loro["mask"])
        arc, yaw = motion_arcs(packet, loro)
        case = _prepare(dict(t=packet["t"], arc=arc, yaw=yaw, eps=d2["truth_residual_r_s"],
                             g=np.abs(loro["H"][:, 1, 2]), d=np.linalg.norm(loro["prior"][:, :2] - anchor, axis=1),
                             mask=loro["mask"], Rref=loro["Reff"]))
        for i in range(3):
            indices = _indices(case, i)
            g = case["g"][indices]
            support = _support(case, indices)
            observed = float(np.var(case["parts"]["slow"][indices, 1])) if len(indices) else None
            old = next(row for row in reference if row["fold"] == route and row["bin_index"] == i)
            if support != old["support"][route]:
                raise ValueError("V8 holdout support changed")
            np.testing.assert_allclose(observed, old["measured"], atol=1e-12, rtol=1e-12)
            details = {}
            for role in SETS:
                row = fit[role][i]
                maximum, p95, beta = (row[k] for k in ("g_max", "g_p95", "beta"))
                count = int(np.sum(g > maximum)) if len(g) and maximum is not None else None
                count_p95 = int(np.sum(g > p95)) if len(g) and p95 is not None else None
                prediction = float(beta[0] + beta[1] * np.mean(g ** 2)) if beta and len(g) else None
                ratio = prediction / observed if prediction is not None and observed and observed > 1e-12 else None
                capped = float(beta[0] + beta[1] * np.mean(np.minimum(g, maximum) ** 2)) if prediction is not None else None
                details[role] = dict(exceed_g_max_n=count, exceed_g_p95_n=count_p95,
                                     exceed_g_max_fraction=count / len(g) if count is not None else None,
                                     predicted_proxy=prediction, predicted_to_v8_observed_ratio=ratio,
                                     capped_predicted_to_v8_observed_ratio=capped / observed if ratio is not None else None)
            results.append(dict(route=route, distance_m=old["distance_m"], bin_index=i, v8_holdout_support=support,
                                holdout_g_min=float(g.min()), holdout_g_max=float(g.max()),
                                v8_old_exceed_g_max_n=old["exceed_max_n"], v8_observed_slow_variance=observed,
                                sensitivities=details))
    if len(results) != 9:
        raise ValueError("Expected exactly nine V8 route/bin comparisons")
    return results


def execute():
    contract = read(CONTRACT_PATH)
    trigger = contract["trigger"]
    if contract["runner_sha256"] != sha(Path(__file__)) or contract["commit"] != REVISION or contract["rules"] != RULES:
        raise ValueError("C7 contract changed")
    if (sha(trigger["path"]) != trigger["sha256"]
            or sha(trigger["parent_receipt"]) != trigger["receipt_sha256"]):
        raise ValueError("C5 trigger record changed")
    for record in [*contract["governance"], *contract["inherited_sources"].values()]:
        if sha(record["path"]) != record["sha256"]:
            raise ValueError(f"Inherited source changed: {record['path']}")
    if sha(KS / "RUN_CONTRACT_RETRY_03.json") != contract["source_s2_v8_contract_sha256"]:
        raise ValueError("V8 frozen parent contract changed")
    for path, expected in contract["frozen_holdout_files"].items():
        if sha(path) != expected:
            raise ValueError(f"Frozen holdout digest mismatch: {path}")
    committed = {path: blob(path) for path in contract["committed_donor_files"]}
    for path, data in committed.items():
        if digest(data) != contract["committed_donor_files"][path]:
            raise ValueError(f"C7 committed donor digest mismatch: {path}")
    for alias, record in contract["frozen_donor_pose_files"].items():
        data = Path(record["path"]).read_bytes()
        if digest(data) != record["sha256"]:
            raise ValueError(f"C7 S2 production pose digest mismatch: {alias}")
        committed[alias] = data
    _, support, counts = yaw_smooth(np.array([-60., -57.5, -55., 55., 57.5, 60.]), np.arange(6.), RULES)
    np.testing.assert_array_equal(counts, np.full(6, 3))
    np.testing.assert_array_equal(support, np.ones(6, dtype=bool))
    donors = fetch_donors(committed, RULES)
    if len(donors) != 2 * 3 * 18 * 49:
        raise ValueError("Dense49 donor inventory mismatch")
    group = lambda role: {(r["station"], r["anchor"]) for r in donors if r["role"] == role}
    paired = group(SETS[0]) & group(SETS[1])
    if len(paired) != 54 or len({key[0] for key in paired}) != 18:
        raise ValueError("TEACH/REPEAT station pairing mismatch")
    fit = summarize_fit(donors, RULES)
    eval_rows = holdout_rows(contract, fit)
    totals = {}
    for route in ROUTES:
        decoded = [row for row in eval_rows if row["route"] == route]
        old = sum(row["v8_old_exceed_g_max_n"] for row in decoded)
        n = sum(row["v8_holdout_support"]["n"] for row in decoded)
        totals[route] = dict(n=n, pk_v8_original_exceed_max=old)
        for role in SETS:
            comparisons = [r for r in decoded if r["sensitivities"][role]["exceed_g_max_n"] is not None]
            totals[route][role] = dict(
                comparable_n=sum(r["v8_holdout_support"]["n"] for r in comparisons),
                exceed_n=sum(r["sensitivities"][role]["exceed_g_max_n"] for r in comparisons)
            )
    output = HERE / "C7_RESULTS.json"
    write(output, dict(status="SIMULATED_PROXY_DIAGNOSTIC", paired_physical_stations=18,
                       paired_station_anchor_views=len(paired), fits=fit, holdout_rows=eval_rows,
                       exceedances_over_g_max=totals, claim_boundary=[
                           "Sensitivity coverage addresses geometry only; donor derivative is CHAR_001 LoS O30, V8 derivative is the EKF LUT.",
                           "Proxy fit is centered yaw-smoothed full-minus-LoS e_s at station, not a transit-window MB_VAR-corrected EKF residual.",
                           "TEACH/REPEAT here are RT evaluations on planned poses in the same corridor; no field RF collection or independent replicate.",
                           "No admission gates or candidate EKF validation changed."
                       ]))
    table = HERE / "C7_DONOR_ROWS.csv"
    with table.open("x", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(donors[0]))
        writer.writeheader()
        writer.writerows(donors)
    return [output, table]


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("phase", choices=("freeze", "run"))
    cli.add_argument("--c5-evidence", type=Path)
    args = cli.parse_args()
    if args.phase == "freeze":
        if args.c5_evidence is None:
            cli.error("freeze requires the C5 gate evidence file")
        freeze(args.c5_evidence)
    else:
        execution = dict(question="G1-INT-001/KS-TRANSFER/C7", started_utc=now(), commit=REVISION,
                         command=[sys.executable, *sys.orig_argv[1:]], platform=platform.platform(),
                         python=sys.version, numpy=np.__version__, scipy=scipy.__version__,
                         runner_sha256=sha(Path(__file__)), contract_sha256=sha(CONTRACT_PATH))
        try:
            outputs = execute()
            execution.update(status="PASS_EXECUTION", exit_code=0,
                             outputs={path.name: sha(path) for path in outputs})
        except Exception as exc:
            execution.update(status="FAIL_EXECUTION", exit_code=1, reason=repr(exc))
            raise
        finally:
            execution["finished_utc"] = now()
            write(HERE / "EXECUTION_C7.json", execution)
