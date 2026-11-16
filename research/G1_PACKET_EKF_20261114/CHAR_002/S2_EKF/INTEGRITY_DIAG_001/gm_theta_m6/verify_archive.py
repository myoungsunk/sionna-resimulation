"""Verify published M6 receipts and recompute all reported point scores."""

import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def checked(path, expected):
    require(digest(path) == expected, f"SHA-256 differs: {path}")


def published_path(original):
    original = str(original).replace("\\", "/")
    marker = "G1_GM_THETA_M6_20261116/"
    require(marker in original, f"Unmapped archive record {original}")
    relative = original.split(marker, 1)[1]
    target = ROOT / relative
    require(target.resolve().is_relative_to(ROOT.resolve()), f"Escaping path {relative}")
    return target


def verify_bytes():
    inventory = {}
    for line in (ROOT / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        expected, name = line.split("  ", 1)
        require(name not in inventory, "Duplicate inventory record")
        inventory[name] = expected
        checked(ROOT / name, expected)
    actual = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*")
              if p.is_file() and "__pycache__" not in p.parts and p.name != "SHA256SUMS"}
    require(set(inventory) == actual, "Missing or unexpected archive files")
    receipts, outputs = 0, 0
    for receipt_path in ROOT.rglob("EXECUTION.json"):
        receipt = read(receipt_path)
        checked(receipt_path.parent / "RUN_CONTRACT.json", receipt["contract_sha256"])
        records = receipt["outputs"]
        if isinstance(records, dict):
            for name, expected in records.items():
                checked(receipt_path.parent / name, expected)
        else:
            for record in records:
                checked(published_path(record["path"]), record["sha256"])
        receipts += 1
        outputs += len(records)
    content_hashes = set(inventory.values())
    for name in ("characterization/RUN_CONTRACT.json", "attempt_02/RUN_CONTRACT.json",
                 "online_barrier/RUN_CONTRACT.json", "attempt_02/results/RUN_CONTRACT.json",
                 "characterization_tables/attempt_02/RUN_CONTRACT.json",
                 "diagnostics_tables/attempt_02/RUN_CONTRACT.json"):
        def check_source_records(node):
            if isinstance(node, dict):
                if {"path", "sha256"} <= node.keys() and "G1_GM_THETA_M6_20261116" in str(node["path"]):
                    require(node["sha256"] in content_hashes, f"Missing frozen content {node['path']}")
                else:
                    for value in node.values():
                        check_source_records(value)
            elif isinstance(node, list):
                for value in node:
                    check_source_records(value)
        check_source_records(read(ROOT / name))
    return dict(files=len(inventory), receipts=receipts, receipt_outputs=outputs)


def metric_rows(trace, truth):
    error = trace["x"][:, :3] - truth
    error[:, 2] = (error[:, 2] + np.pi) % (2 * np.pi) - np.pi
    p = trace["P"][:, :3, :3]
    n3 = np.einsum("ni,ni->n", error, np.linalg.solve(p, error[..., None])[..., 0])
    n2 = np.einsum("ni,ni->n", error[:, :2], np.linalg.solve(p[:, :2, :2], error[:, :2, None])[..., 0])
    return np.column_stack([np.rad2deg(error[:, 2]) ** 2, (error[:, :2] ** 2).sum(axis=1) * 10000.,
                            n3, n3 <= 7.814727903251179, n2 <= 5.991464547107979,
                            abs(error[:, 2]) <= 1.96 * np.sqrt(p[:, 2, 2])])


def point_rows(rows):
    mean = rows.mean(axis=0)
    return dict(n=len(rows), heading_rmse_deg=float(np.sqrt(mean[0])), xy_rmse_cm=float(np.sqrt(mean[1])),
                mean_nees3=float(mean[2]), pose95_coverage=float(mean[3]), xy95_coverage=float(mean[4]),
                heading95_coverage=float(mean[5]))


def verify_scores():
    scores = read(ROOT / "attempt_02/results/SCORES.json")
    contract = read(ROOT / "attempt_02/RUN_CONTRACT.json")
    cases = read(ROOT / "characterization/RUN_CONTRACT.json")["cells"]
    truth = {}
    for case in cases:
        path = ROOT / "inputs" / f"{case['route']}_evaluator.npz"
        checked(path, case["evaluator"]["sha256"])
        with np.load(path, allow_pickle=False) as packed:
            truth[case["route"]] = {k: packed[k] for k in ("truth", "t", "pose_id")}
    count, max_delta = 0, 0.
    for seed in contract["seeds"]:
        by_route = {}
        stage = "seed10" if seed == 10 else "seed11_14"
        for route in truth:
            baseline_path = ROOT / "attempt_02/implementation" / f"seed{seed}/{route}_G0.npz"
            with np.load(baseline_path, allow_pickle=False) as baseline:
                mask, r = baseline["mask"], baseline["Reff"]
            files = {"BASE": baseline_path}
            files.update({p.name[len(route)+1:-4]: p for p in
                          (ROOT / "attempt_02" / stage / f"seed{seed}").glob(f"{route}_*.npz")})
            by_route[route] = {}
            for arm, path in files.items():
                with np.load(path, allow_pickle=False) as trace:
                    for key in ("t", "pose_id"):
                        np.testing.assert_array_equal(trace[key], truth[route][key])
                    np.testing.assert_array_equal(trace["mask"], mask)
                    if arm != "BASE":
                        np.testing.assert_array_equal(trace["R_ref"], r)
                    by_route[route][arm] = metric_rows(trace, truth[route]["truth"])
                count += 1
        record = scores[str(seed)]
        for section in (record["common"], *(row["scores"] for row in record["subsets"].values())):
            routes = [r for r in section["point"] if r != "pooled"]
            for group, by_arm in section["point"].items():
                for arm, archived in by_arm.items():
                    point = point_rows(np.concatenate([by_route[r][arm] for r in routes])
                                       if group == "pooled" else by_route[group][arm])
                    for key, value in point.items():
                        np.testing.assert_allclose(value, archived[key], atol=1e-12, rtol=1e-12,
                                                   err_msg=f"{seed}/{group}/{arm}/{key}")
                        max_delta = max(max_delta, abs(value-archived[key]))
    require(count == 69, f"Unexpected scored trace count {count}")
    require(sum(len(row["seeds"]) for row in contract["variants"]) == 54, "Candidate matrix differs")
    band = read(ROOT / "attempt_02/results/BAND.json")
    require(band["grid_status"] == "NO_BAND" and not band["gm_theta_adoption_candidate"],
            "Published M6 decision differs")
    require(band["five_seed"]["G1_KI"]["pooled_pass_seed_count"] == 3, "Hybrid seed decision differs")
    return dict(trace_conditions=count, max_absolute_point_delta=max_delta)


if __name__ == "__main__":
    print(json.dumps(dict(status="PASS", inventory=verify_bytes(), scores=verify_scores()),
                     ensure_ascii=False, indent=2))
