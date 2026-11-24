"""Extract the frozen V1 measured CIR features for the six new Full channels."""

import argparse
import csv
import gzip
import hashlib
import json
import runpy
from pathlib import Path

import numpy as np


FEATURE_SHA256 = "c2913abc9347286ad83812c0f84beadb5b2c0d7ce2a9ee57bc1ae6bd44ac2466"
FREQUENCY_SHA256 = "fe0bcfeb1426847ea090668845fe124482086d0510e38ebdb463609e2a1169f8"
ROUTE_COUNTS = dict(N1=953, N2=941, N3=1341, N4=1274, N5=918, N6=962)
# The feature order is the HGB input contract in v1_common.EXIST.
EXIST = (
    "log_fp_power", "abs_s_fp", "early4", "early8", "early16", "delay_rms_ns",
    "peak_diff_ns", "eta_fp_win80", "s_diff4", "s_diff8", "s_diff16",
    "tap_pol_var80", "jones_diversity", "freq_s_var", "detector_s_span",
    "detector_delay_span_ns",
)
MEASURED = ("s_fp", "range_m", "tap", "valid") + EXIST
COLUMNS = (
    "case", "route", "channel", "pose_id", "global_pose_id", "t",
    "x_eval", "y_eval", "z_eval", "yaw_eval_rad", "s_fp", "range_m",
    "fp_tap", "valid",
) + EXIST


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_extractor(feature_source, reference_frequencies):
    if sha256(feature_source) != FEATURE_SHA256:
        raise ValueError("Frozen CIR extractor SHA-256 mismatch")
    if sha256(reference_frequencies) != FREQUENCY_SHA256:
        raise ValueError("Frozen frequency grid SHA-256 mismatch")
    return (
        runpy.run_path(str(feature_source))["extract"],
        np.load(reference_frequencies, allow_pickle=False),
    )


def extract_batch(extract, channel, frequencies):
    # Frozen build_dataset selects TX index 0 and retains both RX columns.
    measured = extract(channel[:, :, :, 0], frequencies)
    for name in MEASURED:
        if measured[name].shape != (len(channel),):
            raise ValueError("Unexpected frozen extractor field shape: " + name)
    if not measured["valid"].all() or not all(
        np.isfinite(measured[name]).all() for name in MEASURED
    ):
        raise ValueError("Invalid CIR observation or nonfinite V1 feature")
    return measured


def extract_case(results, route, count, extract, frequencies, writer):
    case = route + "_aB_m0"
    folder = results / "cases" / case
    samples_path = folder / "SAMPLES.json"
    h_path = folder / "H_full.npy"
    samples = json.loads(samples_path.read_text(encoding="utf-8"))
    channel = np.load(h_path, mmap_mode="r", allow_pickle=False)
    if (
        len(samples) != count
        or channel.shape != (count, len(frequencies), 2, 2)
        or channel.dtype != np.complex128
    ):
        raise ValueError("Unexpected observation count or H shape/dtype: " + case)
    for index, sample in enumerate(samples):
        if (
            sample["case"] != case or sample["route"] != route
            or sample["pose_id"] != index or sample["sequence_index"] != index
            or not isinstance(sample["global_pose_id"], int)
            or sample["global_pose_id"] < 0
            or abs(sample["t"] - 0.2 * index) > 1e-9
            or not np.isfinite([sample[k] for k in ("t", "x", "y", "z", "yaw")]).all()
        ):
            raise ValueError("Unexpected observation identity: {} row {}".format(case, index))
    for start in range(0, count, 64):
        batch = extract_batch(extract, channel[start:start + 64], frequencies)
        for offset, sample in enumerate(samples[start:start + 64]):
            writer.writerow((
                case, route, "full", sample["pose_id"], sample["global_pose_id"],
                sample["t"], sample["x"], sample["y"], sample["z"], sample["yaw"],
                *(batch[name][offset].item() for name in MEASURED),
            ))
    return {
        "case": case, "rows": count,
        "samples_sha256": sha256(samples_path), "h_full_sha256": sha256(h_path),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path, help="Completed N1–N6 RT results directory")
    parser.add_argument("--feature-source", type=Path, required=True)
    parser.add_argument("--reference-frequencies", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    extract, reference = load_extractor(args.feature_source, args.reference_frequencies)
    frequencies_path = args.results / "FREQUENCIES_HZ.npy"
    frequencies = np.load(frequencies_path, allow_pickle=False)
    if frequencies.dtype != reference.dtype or not np.array_equal(frequencies, reference):
        raise ValueError("RT frequency grid differs from frozen V1 grid")

    args.output_dir.mkdir(exist_ok=False)
    features_path = args.output_dir / "OBSERVATION_FEATURES.csv.gz"
    with gzip.open(features_path, "xt", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(COLUMNS)
        cases = [
            extract_case(args.results, route, count, extract, frequencies, writer)
            for route, count in ROUTE_COUNTS.items()
        ]
    report = {
        "status": "PASS", "rows": sum(case["rows"] for case in cases), "cases": cases,
        "feature_source_sha256": FEATURE_SHA256,
        "reference_frequency_sha256": FREQUENCY_SHA256,
        "input_frequency_sha256": sha256(frequencies_path),
        "features_sha256": sha256(features_path),
        "adapter_sha256": sha256(Path(__file__)),
        "numpy_version": np.__version__,
        "model_feature_order": EXIST,
    }
    (args.output_dir / "CIR_FEATURES_REPORT.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(report))


if __name__ == "__main__":
    main()
