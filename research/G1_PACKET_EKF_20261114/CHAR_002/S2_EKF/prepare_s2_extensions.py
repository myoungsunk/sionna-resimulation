"""Bind the A2 L2 archive and verify the BLOCK_C O30 observation generator."""

import argparse
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys

import numpy as np


SOURCE = "beb845665661ad8c68d07c88f6d268da4832e493"
SPEC = "6c175a53fbbbb19f990881f7dfcf82a3760dab70"
RESEARCH = "research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104"
BASELINE = (RESEARCH + "/FP_SELECTIVE_CORRECTION_001/E0_20261105/A2_20261105/"
            "RUN_E0_A2_001/baseline")
FROZEN = RESEARCH + "/C1/C1A_001/FROZEN_PACKETS"
LOCK = "research/FP_NATIVE_B_CAUSAL_ABLATION_20261108/RELEASE_INPUT_LOCK.json"
CHAR1 = "research/G1_PACKET_EKF_20261114/CHAR_001/out/EXTRACT_MANIFEST.json"
ROWS = {"R2": 979, "R4": 742, "R5": 1415}
TRACE_FIELDS = ("prior", "Pprior", "h", "H", "K", "Reff", "mask")
EPS = 1e-10
DF = 1950000.0
STEP = 299792458.0 / (1028 * DF)


def git_blob(repo, revision, name):
    return subprocess.check_output(["git", "-c", "gc.auto=0", "-C", str(repo),
                                    "show", f"{revision}:{name}"])


def verify_bytes(data, expected, name):
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise ValueError(f"SHA mismatch for {name}: {actual} != {expected}")
    return data


def file_sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def read_npz(source):
    with np.load(source, allow_pickle=False) as values:
        return {key: values[key] for key in values.files}


def verify_array(label, actual, expected):
    if not np.array_equal(actual, expected):
        raise ValueError(f"Array mismatch: {label}")


def write_npz(path, arrays):
    with path.open("xb") as handle:
        np.savez_compressed(handle, **arrays)
    return file_sha(path)


def release_inputs(route, release, lock):
    stem = f"{route}_B0_Full_10"
    on_path = release / f"{stem}__online.npz"
    ev_path = release / f"{stem}__evaluator.npz"
    on = read_npz(io.BytesIO(verify_bytes(on_path.read_bytes(), lock[on_path.name], on_path)))
    ev = read_npz(io.BytesIO(verify_bytes(ev_path.read_bytes(), lock[ev_path.name], ev_path)))
    return on, ev


def bind_l2(route, repo, c1a, b0, b0_eval, index):
    stem = f"{route}_L2_Full_10"
    buffers = {}
    hashes = {}
    for suffix in (".json", "_CONTROLS.npz", "_REPLAY.npz"):
        name = stem + suffix
        path = BASELINE + "/" + name
        buffers[suffix] = verify_bytes(git_blob(repo, SOURCE, path), index[name], path)
        hashes[path] = index[name]
    receipt = json.loads(buffers[".json"])
    if receipt["cell"] != stem or receipt["expected_rows"] != ROWS[route]:
        raise ValueError(f"Wrong A2 receipt for {stem}")
    if receipt["recursive"]["status"] != "PASS":
        raise ValueError(f"A2 replay failed for {stem}")

    packet_path = receipt["inputs"]["packet"]["path"]
    truth_path = f"{FROZEN}/evaluator_truth/{route}_L2_TRUTH.npz"
    if packet_path != f"{FROZEN}/algorithm_input/{route}_aB_m0_L2_Full.npz":
        raise ValueError(f"Wrong A2 packet identity for {stem}")
    for path in (packet_path, truth_path):
        blob_pointer = git_blob(repo, SOURCE, path).decode("ascii")
        if not blob_pointer.startswith("version https://git-lfs.github.com/spec/v1\n"):
            raise ValueError(f"Expected committed LFS identity for {path}")
        hashes[path] = blob_pointer.split("oid sha256:", 1)[1].splitlines()[0]
    if hashes[packet_path] != receipt["inputs"]["packet"]["sha256"]:
        raise ValueError(f"C1A/L2 packet identity mismatch for {stem}")
    packet, evaluator = [read_npz(io.BytesIO(verify_bytes(
        (c1a / Path(path).name).read_bytes(), hashes[path], path)))
        for path in (packet_path, truth_path)]
    reference = read_npz(io.BytesIO(buffers["_REPLAY.npz"]))
    controls = read_npz(io.BytesIO(buffers["_CONTROLS.npz"]))
    for key in ("t", "pose_id"):
        for source in (evaluator, reference, b0, b0_eval):
            verify_array(f"{stem}/{key}", packet[key], source[key])
    verify_array(f"{stem}/truth", evaluator["truth"], b0_eval["truth"])
    delta_z = np.max(np.abs(packet["z"] - b0["z"]), axis=0)
    if np.any(delta_z > EPS):
        raise ValueError(f"L2/B0 observation identity mismatch: {stem}: {delta_z.tolist()}")
    verify_array(f"{stem}/dt", controls["dt"], np.r_[0.0, np.diff(packet["t"])])
    verify_array(f"{stem}/muMB", packet["muMB"], reference["mu"])
    verify_array(f"{stem}/P0", packet["P0"], reference["Pprior"][0])
    online = {**packet, **controls, "x0": np.r_[controls["x0"], 0.0],
              "Hrf": b0["Hrf"], "clean_Hrf": b0["clean_Hrf"],
              "prior": reference["prior"], "Pprior": reference["Pprior"],
              **{f"trace_{key}": reference[key] for key in TRACE_FIELDS}}
    evaluator["clean_H"] = b0_eval["clean_H"]
    return online, evaluator, buffers["_REPLAY.npz"], hashes, receipt.get("controls"), delta_z.tolist()


def native_measurements(observation, full_H):
    blocks = []
    for start in range(0, len(full_H), 256):
        cir = observation.cir_batch(full_H[start:start + 256])
        first = observation.first_path_batch(cir, DF)
        blocks.append(np.column_stack((first["index"] * STEP, first["s"])))
    result = np.concatenate(blocks)
    if not np.isfinite(result).all():
        raise ValueError("Nonfinite O30 measurements")
    return result


def block_c_payload(block_c, route, anchor, ids, lock):
    case = f"{route}_a{anchor}_m0"
    spec = lock[case]
    path = block_c / "FULL_RF" / f"H_{case}.npy"
    full_sha = file_sha(path)
    if full_sha != spec["h_full_sha256"]:
        raise ValueError(f"BLOCK_C input hash mismatch: {path}")
    source = np.load(path, mmap_mode="r", allow_pickle=False)
    if (source.ndim != 4 or source.shape[1:3] != (257, 2) or source.shape[3] < 1
            or ids.min() < 0 or ids.max() >= len(source)):
        raise ValueError(f"Invalid BLOCK_C tensor or pose ids: {path}")
    return np.asarray(source[ids, :, :, 0]), full_sha


def verify_block_c(observation, block_c, release, release_lock, char1_lock):
    frequencies = np.load(block_c / "freqs_hz.npy", allow_pickle=False)
    verify_array("BLOCK_C frequency grid", frequencies, 6250400000. + DF * np.arange(257))
    matched = {}
    for route in ROWS:
        b0, _ = release_inputs(route, release, release_lock)
        ids = b0["pose_id"]
        b_h, b_sha = block_c_payload(block_c, route, "B", ids, char1_lock)
        verify_array(f"{route}/anchor B Hrf", b_h, b0["Hrf"])
        delta = np.max(np.abs(native_measurements(observation, b_h) - b0["z"]), axis=0)
        if np.any(delta > EPS):
            raise ValueError(f"Anchor B generator parity failed: {route}: {delta.tolist()}")
        matched[route] = (ids, b0["t"], b_sha, delta.tolist())
    return matched


def load_anchor_donors(donor, means):
    inputs = json.loads((donor / "INPUT_LOCK.json").read_text(encoding="utf-8"))
    outputs = json.loads((donor / "OUTPUT_SHA256.json").read_text(encoding="utf-8"))
    indexed = {row["path"]: row["sha256"] for row in outputs["files"]}
    record, = [row for row in inputs["files"] if Path(row["path"]).name == means.name]
    means_sha = file_sha(means)
    if means_sha != record["sha256"]:
        raise ValueError(f"MR archive SHA mismatch: {means}")
    by_case = {f"{r}_a{a}_m0": [] for r in ROWS for a in ("A", "B")}
    with gzip.open(means, "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            case = row["case"]
            if case in by_case and row["channel"] == "full" and row["bias"] == "B0":
                by_case[case].append((int(row["pose_id"]), float(row["t_s"]), float(row["abs_ds1"])))
    return indexed, by_case, {"source_commit": inputs["source_commit"],
                              "source_run": inputs["source_run"], "MR_sha256": means_sha,
                              "X1_output_index_sha256": file_sha(donor / "OUTPUT_SHA256.json"),
                              "X1_input_lock_sha256": file_sha(donor / "INPUT_LOCK.json"),
                              "X1_producer_sha256": file_sha(donor / "run_stage.py")}


def anchor_donor_fields(route, anchor, donor, indexed, by_case, ids, t, truth):
    case = f"{route}_a{anchor}_m0"
    donor_path = f"x1/{case}_B0.npz"
    stored = read_npz(io.BytesIO(verify_bytes((donor / donor_path).read_bytes(), indexed[donor_path], donor_path)))
    for label, actual, expected in (("pose_id", stored["pose_id"], ids), ("t", stored["t_s"], t),
                                    ("truth", stored["truth_scoring_only"], truth)):
        verify_array(f"{case}/{label}", actual, expected)
    bb = stored["names"].tolist().index("BB")
    mb = stored["names"].tolist().index("MB")
    series = np.array(by_case[case])
    verify_array(f"{case}/MR pose_id", ids, series[:, 0])
    verify_array(f"{case}/MR t", t, series[:, 1])
    fields = {"z": stored["z"], "muBASE": stored["mu"][:, bb], "muMB": stored["mu"][:, mb],
              "R": stored["R"][:, bb], "P0": stored["Pprior"][0, bb], "D": series[:, 2]}
    return fields, indexed[donor_path]


def load_anchor_online(args, release_lock):
    indexed, by_case, provenance = load_anchor_donors(args.anchor_donor, args.mr_series)
    generator_receipt = args.anchor_z / "ANCHOR_A_Z_RECEIPT.json"
    generator = json.loads(generator_receipt.read_text(encoding="utf-8"))
    if generator["source_commit"] != SOURCE or generator["spec_commit"] != SPEC:
        raise ValueError("Anchor A generator receipt origin mismatch")
    char1_lock = {row["case"]: row for row in json.loads(git_blob(args.repo, SPEC, CHAR1))["cases"]}
    rows = {}
    for route in ROWS:
        b0, b0_eval = release_inputs(route, args.release, release_lock)
        ids, t, truth = b0["pose_id"], b0["t"], b0_eval["truth"]
        b_fields, b_x1_sha = anchor_donor_fields(route, "B", args.anchor_donor, indexed, by_case, ids, t, truth)
        b_delta = {k: float(np.max(np.abs(value - b0[k]))) for k, value in b_fields.items()}
        if max(b_delta.values()) > EPS:
            raise ValueError(f"Anchor B donor parity failed: {route}: {b_delta}")
        a_fields, a_x1_sha = anchor_donor_fields(route, "A", args.anchor_donor, indexed, by_case, ids, t, truth)
        stem = f"{route}_aA_m0_B0_Full_10"
        z_path = args.anchor_z / (stem + "__observations.npz")
        receipt = generator["cases"][route]
        if max(receipt["b_max_abs_error_range_and_s"]) > EPS:
            raise ValueError(f"Receipt failed Anchor B generator parity: {route}")
        generated = read_npz(io.BytesIO(verify_bytes(z_path.read_bytes(), receipt["output_sha256"], z_path)))
        for key in ("t", "pose_id"):
            verify_array(f"{route}/A generated {key}", generated[key], b0[key])
        a_delta = np.max(np.abs(a_fields["z"] - generated["z"]), axis=0)
        if np.any(a_delta > EPS):
            raise ValueError(f"Anchor A generated versus X1 z discrepancy: {route}: {a_delta.tolist()}")

        h, full_sha = block_c_payload(args.block_c, route, "A", ids, char1_lock)
        entry = char1_lock[f"{route}_aA_m0"]
        los_path = args.block_c / f"H_LoS_{route}_aA_m0.npy"
        los_sha = file_sha(los_path)
        if los_sha != entry["h_los_sha256"] or full_sha != receipt["anchor_A_full_H_sha256"]:
            raise ValueError(f"Anchor A channel input mismatch: {route}")
        los = np.load(los_path, mmap_mode="r", allow_pickle=False)[ids, :, :, 0]
        online = {**a_fields, **generated, **{k: b0[k] for k in ("ds", "gy", "dt", "x0")},
                  "Hrf": h, "clean_Hrf": h}
        ev = {"clean_H": los, "t": t, "pose_id": ids, "truth": truth}
        outputs = {stem + "__online.npz": online, stem + "__evaluator.npz": ev}
        rows[route] = {"A_donor_sha256": a_x1_sha, "B_donor_sha256": b_x1_sha,
                       "A_O30_sha256": receipt["output_sha256"], "B_calibration_parity": b_delta,
                       "A_x1_o30_abs_error_range_and_s": a_delta.tolist(),
                       "A_full_H_sha256": full_sha, "A_los_H_sha256": los_sha,
                       "outputs_sha256": {name: write_npz(args.output / name, value)
                                          for name, value in outputs.items()}}
    return {"source_commit": SOURCE, "spec_commit": SPEC, "cases": rows,
            "calibration_provenance": provenance, "A_reference_trace": "ABSENT_FOR_SEED10",
            "generator_receipt_sha256": file_sha(generator_receipt)}


def stage(args):
    release_lock = {row["asset_name"]: row["sha256"]
                    for row in json.loads(git_blob(args.repo, SOURCE, LOCK))["files"]}
    index = json.loads(git_blob(args.repo, SOURCE, BASELINE + "/ARTIFACT_HASHES.json"))
    args.output.mkdir(parents=True, exist_ok=True)
    l2 = {}
    if args.mode in ("l2", "all"):
        for route in ROWS:
            b0, b0_eval = release_inputs(route, args.release, release_lock)
            online, evaluator, replay, hashes, controls, delta_z = bind_l2(
                route, args.repo, args.c1a, b0, b0_eval, index)
            stem = f"{route}_L2_Full_10"
            files = {stem + "__online.npz": online, stem + "__evaluator.npz": evaluator}
            outputs = {name: write_npz(args.output / name, arrays) for name, arrays in files.items()}
            reference_path = args.output / f"{stem}__reference.npz"
            with reference_path.open("xb") as handle:
                handle.write(replay)
            outputs[reference_path.name] = file_sha(reference_path)
            l2[route] = {"inputs_sha256": hashes, "outputs_sha256": outputs, "controls": controls,
                         "b0_l2_max_abs_observation_delta": delta_z}
        (args.output / "L2_INPUT_RECEIPT.json").write_text(
            json.dumps({"source_commit": SOURCE, "cases": l2}, indent=2) + "\n", encoding="utf-8")

    if args.mode in ("anchor-z", "all"):
        sys.path.insert(0, str(args.pinned_src))
        from qclean_uwb.drivesim import observation

        char1_lock = {row["case"]: row for row in json.loads(git_blob(args.repo, SPEC, CHAR1))["cases"]}
        matches = verify_block_c(observation, args.block_c, args.release, release_lock, char1_lock)
        rows = {}
        for route, (ids, t, b_sha, errors) in matches.items():
            a_h, a_sha = block_c_payload(args.block_c, route, "A", ids, char1_lock)
            z = native_measurements(observation, a_h)
            output = args.output / f"{route}_aA_m0_B0_Full_10__observations.npz"
            rows[route] = {"tolerance": EPS, "b_max_abs_error_range_and_s": errors,
                           "anchor_B_full_H_sha256": b_sha, "anchor_A_full_H_sha256": a_sha,
                           "output_sha256": write_npz(output, {"z": z, "pose_id": ids, "t": t})}
        (args.output / "ANCHOR_A_Z_RECEIPT.json").write_text(
            json.dumps({"source_commit": SOURCE, "spec_commit": SPEC,
                        "observation_source_sha256": file_sha(Path(observation.__file__)),
                        "cases": rows, "anchor_A_online_complete": False}, indent=2) + "\n",
            encoding="utf-8")

    if args.mode == "anchor-online":
        payload = load_anchor_online(args, release_lock)
        with (args.output / "ANCHOR_A_INPUT_RECEIPT.json").open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("l2", "anchor-z", "anchor-online", "all"))
    for option in ("repo", "release", "output"):
        parser.add_argument("--" + option, type=Path, required=True)
    for option in ("c1a", "pinned-src", "block-c", "anchor-z", "anchor-donor", "mr-series"):
        parser.add_argument("--" + option, type=Path)
    arguments = parser.parse_args()
    if arguments.mode in ("l2", "all") and arguments.c1a is None:
        parser.error("--c1a is required for L2")
    if arguments.mode in ("anchor-z", "all") and (arguments.pinned_src is None or arguments.block_c is None):
        parser.error("--pinned-src and --block-c are required for Anchor A observations")
    if arguments.mode == "anchor-online" and any(getattr(arguments, key) is None for key in (
            "block_c", "anchor_z", "anchor_donor", "mr_series")):
        parser.error("--block-c, --anchor-z, --anchor-donor, and --mr-series are required for Anchor A online")
    stage(arguments)
