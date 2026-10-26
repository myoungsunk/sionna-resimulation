"""Office M0 paired RF campaign. Reuse the sealed M45 producer; change mount only."""
import argparse
import copy
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tarfile
import time
import urllib.request

HERE = Path(__file__).resolve().parent
REF = "df1bee938c71ac17b1910edbf94ae563e4610bb7"
RAW = "https://raw.githubusercontent.com/myoungsunk/sionna-resimulation/" + REF + "/"
ARCHIVE_URL = "https://github.com/myoungsunk/sionna-resimulation/releases/download/route-rf-o01-20261019-r01/O01.tar.gz"
ARCHIVE_SHA = "e4f3d130cfd8fc6d59261e3c6d2087243217b3d567d52cc4857299629f82eeca"
PLAN_SHA = "a8d9a2cc14575f90c5d0523552f15a901d5aaef39e07bc9cb3d534b41c5abc35"
RUNNER_SHA = "5c91c902186df00dbad669ba98c23618c0a2aa9b1a4762618de143dc8de696be"
GENERATOR_SHA = "a584023452b4d05be80adea5ebc1be26f0ca6f970bddcf00b402a0c0692d085a"
REQUEST_SHA = "794aac938701ec2acd5f6c74404bfc1deb114e925a3368db5637bc77d43319d5"
COUNTS = {"O01": (461, 192), "O02": (521, 207), "O03": (1175, 412)}
BANKS = {
    "LP_plus45_bank.npz": (247727983, "b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b"),
    "LP_minus45_bank.npz": (247743979, "39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9"),
}
THRESHOLDS = {"relative_complex": 1e-4, "delay_s": 1e-12, "s_absolute": 1e-4, "fp_tap_equal": True}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def download(url, destination, expected=None):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        with urllib.request.urlopen(url, timeout=120) as src, destination.open("xb") as dst:
            shutil.copyfileobj(src, dst)
    if expected:
        require(sha(destination) == expected, "DOWNLOAD_SHA:" + destination.name)
    return destination


def read_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def safe_member(name):
    p = PurePosixPath(name)
    require(not p.is_absolute() and ".." not in p.parts and "\\" not in name
            and not any(":" in s for s in p.parts), "UNSAFE_ARCHIVE_PATH")
    return p


def patch_mount(text):
    old = "assert abs((float(row['yaw_antenna_deg'])-float(row['yaw_body_deg']))%360-45)<1e-6"
    new = "assert abs((float(row['yaw_antenna_deg'])-float(row['yaw_body_deg'])+180)%360-180)<1e-6"
    require(text.count(old) == 1, "RUNNER_PATCH_TARGET")
    text = text.replace(old, new)
    text = text.replace("Nine existing route-anchor cases, fixed Mount45.",
                        "Three existing office routes, fixed Mount0; M45 geometry and QA retained.")
    compile(text, "run_route_full_rf_20261019.py", "exec")
    return text


def prepare(root, archive=None):
    require(not root.exists(), "OUTPUT_EXISTS")
    root.mkdir(parents=True)
    archive = Path(archive) if archive else download(ARCHIVE_URL, root.parent / "O01_M45_reference.tar.gz", ARCHIVE_SHA)
    require(sha(archive) == ARCHIVE_SHA, "REFERENCE_ARCHIVE_SHA")
    selected = []
    with tarfile.open(archive, "r:gz") as tar:
        for m in tar:
            name = safe_member(m.name)
            keep = m.name.startswith("O01/source/") or m.name in {
                "O01/FULL_PLAN.json", "O01/SOURCE_SHA256.json", "O01/EXPORTER.py"}
            if not keep:
                continue
            if m.isdir():
                continue
            require(m.isfile(), "REFERENCE_SPECIAL_MEMBER")
            rel = Path(*name.parts[1:])
            require(rel.as_posix() not in selected, "DUPLICATE_ARCHIVE_MEMBER")
            selected.append(rel.as_posix())
            out = root / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(m) as src, out.open("xb") as dst:
                shutil.copyfileobj(src, dst)
    require(sha(root / "FULL_PLAN.json") == PLAN_SHA, "M45_PLAN_SHA")
    original = json.loads((root / "FULL_PLAN.json").read_text())
    source_seal = json.loads((root / "SOURCE_SHA256.json").read_text())
    for name, digest in source_seal.items():
        require(sha(root / name) == digest, "ORIGINAL_SOURCE_SHA:" + name)
    shutil.copyfile(root / "FULL_PLAN.json", root / "M45_REFERENCE_PLAN.json")
    shutil.copyfile(root / "SOURCE_SHA256.json", root / "M45_REFERENCE_SOURCE_SHA256.json")
    generator_path = download(RAW + "research/POWERJOINT_M45_COMPACT_20261019/02_prepare_routes.py",
                              root / "route_generator.py", GENERATOR_SHA)
    request_path = download(RAW + "research/POWERJOINT_M45_COMPACT_20261019/01_ROUTE_REQUEST.json",
                            root / "M45_REFERENCE_REQUEST.json", REQUEST_SHA)
    require(json.loads(request_path.read_text()) == original["request"], "REQUEST_PLAN_MISMATCH")
    sys.path.insert(0, str(root / "source/src"))
    generator = load_module(generator_path, "frozen_m45_route_generator")
    plan = copy.deepcopy(original)
    plan.update(schema="OFFICE_M0_RF_V1", status="PREPARED_NOT_RUN", mount_deg=0,
                cases=[], batches=[], unique_route_poses=811, pose_anchor_conditions=811,
                expected_pathsolver_calls=811 * 257 * 2, worker_count=2,
                runtime_image="GitHub ubuntu-24.04 Python3.11 pinned packages",
                remote_root=None, bank_root=None, pilot_root=None,
                user_authorization="2026-10-26 user requested Office O01/O02/O03 Mount0 GitHub Actions",
                reference_m45_plan_sha256=PLAN_SHA)
    plan["request"]["motion"]["mount_deg"] = 0
    plan["request"]["routes"] = [r for r in plan["request"]["routes"] if r["id"] in COUNTS]
    plan["request"]["schema"] = "OFFICE_M0_EXISTING_SCENE_REQUEST_V1"
    plan["request"]["issued_date"] = "2026-10-26"
    plan["request"]["status"] = "PREPARED_NOT_RUN"
    plan["request"]["scope"] = "O01/O02/O03 only; same Office E geometry, O0 anchor, body motion and RF schedule as M45; antenna mount 0 degrees."
    (root / "POSES").mkdir()
    (root / "BATCH_POSES").mkdir()
    route_receipts = []
    for route in plan["request"]["routes"]:
        rid = route["id"]
        old_rows = generator.generate(original["request"], route)
        check_path = root / "POSES" / (rid + "_M45_RADIO_CHECK.csv")
        generator.emit_csv(check_path, [r for r in old_rows if r["rf_sample"]])
        old_case = next(c for c in original["cases"] if c["route"] == rid)
        require(sha(check_path) == old_case["poses_sha256"], "ORIGINAL_RF_POSES_NOT_IDENTICAL:" + rid)
        rows = generator.generate(plan["request"], route)
        require(len(rows) == COUNTS[rid][0], "MOTION_COUNT")
        for new, old in zip(rows, old_rows):
            require({k: v for k, v in new.items() if k != "yaw_antenna_deg"} ==
                    {k: v for k, v in old.items() if k != "yaw_antenna_deg"}, "BODY_MOTION_CHANGED")
            require(new["yaw_antenna_deg"] == new["yaw_body_deg"], "MOUNT0_ALIGNMENT")
        motion = root / "POSES" / (rid + "_ROUTE_POSE.csv")
        radio = root / "POSES" / (rid + "_RADIO_POSE.csv")
        generator.emit_csv(motion, rows)
        rf = [r for r in rows if r["rf_sample"]]
        generator.emit_csv(radio, rf)
        require(len(rf) == COUNTS[rid][1], "RF_COUNT")
        case = copy.deepcopy(old_case)
        case.update(case_id=rid + "_O0_M0_FULL", poses_file=str(radio.relative_to(root)).replace("\\", "/"),
                    poses_sha256=sha(radio), count=len(rf), mount_deg=0)
        plan["cases"].append(case)
        for start in range(0, len(rf), 20):
            stop = min(start + 20, len(rf))
            bid = case["case_id"] + "_P%04d_%04d" % (start, stop)
            path = root / "BATCH_POSES" / (bid + ".csv")
            generator.emit_csv(path, rf[start:stop])
            plan["batches"].append(dict(batch_id=bid, case_id=case["case_id"], start=start,
                stop=stop, count=stop-start, poses_file=str(path.relative_to(root)).replace("\\", "/"),
                poses_sha256=sha(path)))
        route_receipts.append(dict(route=rid, motion_n=len(rows), rf_n=len(rf),
            motion_sha256=sha(motion), radio_sha256=sha(radio), reference_radio_sha256=sha(check_path),
            same_body_motion_time_and_rf_schedule=True))
    runner = root / "source/scripts/run_route_full_rf_20261019.py"
    require(sha(runner) == RUNNER_SHA, "M45_RUNNER_SHA")
    runner.write_text(patch_mount(runner.read_text()), encoding="utf-8", newline="\n")
    source_seal["source/scripts/run_route_full_rf_20261019.py"] = sha(runner)
    write(root / "SOURCE_SHA256.json", source_seal)
    write(root / "FULL_PLAN.json", plan)
    write(root / "PREPARATION_RECEIPT.json", dict(status="PREPARATION_PASS_RF_NOT_RUN",
        mount_deg=0, reference_archive_sha256=ARCHIVE_SHA, reference_plan_sha256=PLAN_SHA,
        original_runner_sha256=RUNNER_SHA, m0_runner_sha256=sha(runner),
        modification="mount validation 45->0; documentation only otherwise; RF solver, physics and QA unchanged",
        routes=route_receipts, pathsolver_calls=0, sensor_v2_generated=False,
        estimation_performance="NOT_ASSESSED"))
    validate_prepared(root)
    seal = {str(p.relative_to(root)).replace("\\", "/"): sha(p) for p in sorted(root.rglob("*")) if p.is_file()}
    write(root / "PREPARED_SHA256.json", seal)
    pilot = [b["batch_id"] for b in plan["batches"] if b["start"] == 0]
    full = [b["batch_id"] for b in plan["batches"] if b["start"] != 0]
    matrices = dict(pilot={"batch": pilot}, full={"batch": full})
    write(root / "MATRICES.json", matrices)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            for k, v in matrices.items():
                f.write(k + "=" + json.dumps(v, separators=(",", ":")) + "\n")
    print(json.dumps(dict(routes=route_receipts, pilot_batches=len(pilot), full_batches=len(full))))


def validate_prepared(root):
    plan = json.loads((root / "FULL_PLAN.json").read_text())
    require(plan["schema"] == "OFFICE_M0_RF_V1" and plan["mount_deg"] == 0, "PLAN_IDENTITY")
    require(plan["thresholds"] == THRESHOLDS, "QA_THRESHOLDS_CHANGED")
    require({c["route"] for c in plan["cases"]} == set(COUNTS) and len(plan["cases"]) == 3, "CASE_SCOPE")
    require(len(plan["batches"]) == 42 and len({b["batch_id"] for b in plan["batches"]}) == 42, "BATCH_SCOPE")
    for name, digest in json.loads((root / "SOURCE_SHA256.json").read_text()).items():
        safe_member(name)
        require(sha(root / name) == digest, "SOURCE_SHA:" + name)
    for case in plan["cases"]:
        rid = case["route"]
        require(case["case_id"] == rid + "_O0_M0_FULL" and case["anchor"] == "O0"
                and case["anchor_m"] == [5, 2.2, 2.65], "CASE_IDENTITY")
        path = root / case["poses_file"]
        require(sha(path) == case["poses_sha256"], "CASE_POSE_SHA")
        rows = read_csv(path)
        require(len(rows) == COUNTS[rid][1], "CASE_COUNT")
        require(all(float(a["t_s"]) < float(b["t_s"]) for a, b in zip(rows, rows[1:])), "CLOCK")
        require(all(float(r["yaw_antenna_deg"]) == float(r["yaw_body_deg"]) for r in rows), "MOUNT0")
        covered = []
        for batch in [b for b in plan["batches"] if b["case_id"] == case["case_id"]]:
            require(batch["count"] == batch["stop"] - batch["start"] and 0 < batch["count"] <= 20, "BATCH_COUNT")
            require(sha(root / batch["poses_file"]) == batch["poses_sha256"], "BATCH_POSE_SHA")
            require(read_csv(root / batch["poses_file"]) == rows[batch["start"]:batch["stop"]], "BATCH_ORDER")
            covered.extend(range(batch["start"], batch["stop"]))
        require(covered == list(range(len(rows))), "COVERAGE")
    return plan


def verify_seal(root):
    for name, digest in json.loads((root / "PREPARED_SHA256.json").read_text()).items():
        safe_member(name)
        require(sha(root / name) == digest, "PREPARED_SHA:" + name)
    return validate_prepared(root)


def banks(root):
    for name, (size, digest) in BANKS.items():
        p = download("https://media.githubusercontent.com/media/myoungsunk/sionna-resimulation/"
                     "4c0682a55298ae33f3495a4c7249f3a8c34633ad/" + name, root / "source" / name, digest)
        require(p.stat().st_size == size, "BANK_SIZE")
    write(root / "BANK_RECEIPT.json", dict(status="EXACT_BANK_SHA_PASS", banks=BANKS))


def batch(root, bid, pilot=False):
    plan = verify_seal(root)
    require(any(b["batch_id"] == bid for b in plan["batches"]), "UNKNOWN_BATCH")
    for name, (size, digest) in BANKS.items():
        require((root / "source" / name).stat().st_size == size and sha(root / "source" / name) == digest, "BANK_SHA")
    require(pilot == next(b["start"] == 0 for b in plan["batches"] if b["batch_id"] == bid), "PILOT_STAGE")
    runner = load_module(root / "source/scripts/run_route_full_rf_20261019.py", "m0_native_runner")
    # Pilot uses all 257 bins and original raw-replay/FP gates, not sparse --canary.
    runner.run_batch(root.resolve(), (root / "source").resolve(), bid)
    common = load_module(root / "source/scripts/route_full_controller_20261019.py", "m45_validation")
    b = next(b for b in plan["batches"] if b["batch_id"] == bid)
    check = common.validate_batch(root, b, sha(root / "FULL_PLAN.json"),
                                  sha(root / "source/scripts/run_route_full_rf_20261019.py"))
    write(root / "BATCHES" / bid / "ACTIONS_RECEIPT.json", dict(status="BATCH_VALIDATED",
        validation=check, mount_deg=0, pilot=pilot, run_id=os.getenv("GITHUB_RUN_ID"),
        commit=os.getenv("GITHUB_SHA"), attempt=os.getenv("GITHUB_RUN_ATTEMPT")))
    # Re-seal after adding Actions provenance, then validate exact coverage again.
    common.seal(root / "BATCHES" / bid)
    common.validate_batch(root, b, sha(root / "FULL_PLAN.json"), sha(root / "source/scripts/run_route_full_rf_20261019.py"))


def aggregate(root):
    import numpy as np
    plan = verify_seal(root)
    common = load_module(root / "source/scripts/route_full_controller_20261019.py", "m45_validation")
    exporter = load_module(root / "EXPORTER.py", "m45_exporter")
    expected = {b["batch_id"] for b in plan["batches"]}
    require({p.name for p in (root / "BATCHES").iterdir() if p.is_dir()} == expected, "MISSING_OR_EXTRA_BATCH")
    checks = [common.validate_batch(root, b, sha(root / "FULL_PLAN.json"),
              sha(root / "source/scripts/run_route_full_rf_20261019.py")) for b in plan["batches"]]
    receipts = []
    for case in plan["cases"]:
        bs = [b for b in plan["batches"] if b["case_id"] == case["case_id"]]
        receipt = exporter.aggregate_case(common, root, root, case, bs, sha(root / "FULL_PLAN.json"))
        folder = root / "CASES" / case["case_id"]
        direct = np.load(folder / "H_DIRECT_LOS.npy", allow_pickle=False)
        exists = np.load(folder / "LOS_EXISTS.npy", allow_pickle=False)
        require(not np.any(direct[~exists]), "BLOCKED_LOS_NONZERO")
        require(direct.shape == (COUNTS[case["route"]][1], 257, 2, 2), "AGGREGATE_SHAPE")
        receipt.update(mount_deg=0, los_present_count=int(exists.sum()), los_absent_count=int((~exists).sum()))
        receipts.append(receipt)
    write(root / "CAMPAIGN_RECEIPT.json", dict(status="OFFICE_M0_RF_QA_PASS", mount_deg=0,
        cases=receipts, batches=len(checks), rf_pose_count=811, pathsolver_calls=416854,
        plan_sha256=sha(root / "FULL_PLAN.json"), run_id=os.getenv("GITHUB_RUN_ID"),
        commit=os.getenv("GITHUB_SHA"), timestamp_epoch=time.time(), sensor_v2_generated=False,
        estimation_performance="NOT_ASSESSED", scientific_generalization="NOT_ESTABLISHED"))
    for case in plan["cases"]:
        rid = case["route"]
        with tarfile.open(root / (rid + "_M0.tar.gz"), "w:gz") as tar:
            for path in [root / "CASES" / case["case_id"], root / "POSES" / (rid + "_ROUTE_POSE.csv"),
                         root / "POSES" / (rid + "_RADIO_POSE.csv"), root / "CAMPAIGN_RECEIPT.json",
                         root / "PREPARATION_RECEIPT.json", root / "FULL_PLAN.json"]:
                tar.add(path, arcname=rid + "_M0/" + str(path.relative_to(root)).replace("\\", "/"))
        write(root / (rid + "_M0_ARCHIVE_SHA.json"), dict(sha256=sha(root / (rid + "_M0.tar.gz")),
              raw_paths="Retained in office-m0-batch artifacts in the same Actions run"))


def selftest(root):
    """Meaningful negative checks against the prepared, sealed real route inputs."""
    plan = verify_seal(root)
    require(sum(c["count"] for c in plan["cases"]) == 811, "RF_TOTAL")
    require(sum(b["count"] for b in plan["batches"]) * 257 * 2 == 416854, "SOLVER_TOTAL")
    for bad in ["../escape", "/absolute", "x/../../escape", "C:/escape", "x\\escape"]:
        try:
            safe_member(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("Unsafe path accepted")
    try:
        patch_mount("wrong runner")
    except ValueError:
        pass
    else:
        raise AssertionError("Unexpected source accepted")
    p = root / "FULL_PLAN.json"
    saved = p.read_bytes()
    try:
        changed = copy.deepcopy(plan)
        changed["thresholds"]["relative_complex"] = 1
        write(p, changed)
        try:
            validate_prepared(root)
        except ValueError:
            pass
        else:
            raise AssertionError("Changed QA threshold accepted")
    finally:
        p.write_bytes(saved)
    csvpath = root / plan["cases"][0]["poses_file"]
    saved = csvpath.read_bytes()
    try:
        csvpath.write_bytes(saved + b"\n")
        try:
            verify_seal(root)
        except ValueError:
            pass
        else:
            raise AssertionError("Changed pose accepted")
    finally:
        csvpath.write_bytes(saved)
    verify_seal(root)
    print("SELFTEST_PASS: 811 matched poses, 42 exact batches, M0 alignment, hash/mount/threshold/path guards; RF calls=0")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("stage", choices=["prepare", "banks", "batch", "aggregate", "selftest"])
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--archive", type=Path)
    p.add_argument("--batch")
    p.add_argument("--pilot", action="store_true")
    a = p.parse_args()
    try:
        if a.stage == "prepare":
            prepare(a.root, a.archive)
        elif a.stage == "banks":
            banks(a.root)
        elif a.stage == "batch":
            batch(a.root, a.batch, a.pilot)
        elif a.stage == "aggregate":
            aggregate(a.root)
        else:
            selftest(a.root)
    except Exception as e:
        a.root.mkdir(parents=True, exist_ok=True)
        write(a.root / "FAILURE_RECEIPT.json", dict(status="FAILED_STOP", stage=a.stage,
            batch=a.batch, error=type(e).__name__ + ": " + str(e), timestamp_epoch=time.time(),
            run_id=os.getenv("GITHUB_RUN_ID"), commit=os.getenv("GITHUB_SHA"),
            estimation_performance="NOT_ASSESSED"))
        raise


if __name__ == "__main__":
    main()

