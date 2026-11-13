"""Seal G1-MODEL-001 v3.3 execution receipts after the remote launcher exits."""
from datetime import datetime, timezone
from pathlib import Path
import csv
import hashlib
import json
import sys

SPEC = "cb5496afeebe8f48ffebc2d541a3af0733ca0d42"
RUN2 = "cd6290ca44ab16c966ce2a8551cfa71a6684cb4d"


def read(path):
    return json.loads(path.read_bytes()) if path.exists() else None


def write(path, value):
    with path.open("x", encoding="utf-8") as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write("\n")


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def grid_receipts(base, out):
    entries = []
    for path in sorted((base / "grid").glob("*_INDEX.json")):
        meta = read(path)
        path_stem = path.name.removesuffix(".json")
        with (out / (path_stem + ".csv")).open("x", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(("axis_station", "physical_station", "rf_seed", "x_m", "y_m",
                             "truth_yaw_deg", "valid_observations"))
            for axis, station in enumerate(meta["groups"]):
                for seed, valid in enumerate(meta["n_valid"][axis]):
                    writer.writerow((axis, station["group"], seed, station["x"], station["y"],
                                     station["yaw_deg"], valid))
        for name, expected in sorted(meta["files"].items()):
            array = base / "grid" / name
            observed = sha(array)
            if observed != expected:
                raise ValueError(f"Grid hash mismatch: {name}")
            entries.append((name, array.stat().st_size, observed))
    if entries:
        with (out / "S1P_J_SHA256.csv").open("x", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(("file", "bytes", "sha256"))
            writer.writerows(entries)
    return entries


def main():
    base = Path(sys.argv[1])
    out, code = base / "outputs", base / "code"
    phase_names = ("verify", "prep", "bias", "e2e", "primary")
    stages = {}
    for name in phase_names:
        start = out / f"START_{name}_UTC.txt"
        if not start.exists():
            stages[name] = None
            continue
        end = out / f"FINISH_{name}_UTC.txt"
        rc = out / f"EXIT_{name}.txt"
        if not (end.exists() and rc.exists()):
            raise RuntimeError(f"Still running or missing exit receipt: {name}")
        stages[name] = {
            "started_utc": start.read_text().strip(),
            "finished_utc": end.read_text().strip(),
            "exit_code": int(rc.read_text()),
            "command": (out / f"COMMAND_{name}.txt").read_text().strip(),
        }
    r0 = read(out / "R0.json")
    obs = read(out / "S1P_OBS_PREFLIGHT.json")
    snap = read(out / "S1P_SNAP.json")
    e2e = read(out / "S1P_G_E2E.json")
    e2e_error = read(out / "E2E_INVALID.json")
    verdict = read(out / "S2P_VERDICT.json")
    status = (e2e["status"] if e2e else
              "INVALID" if e2e_error or int((out / "EXIT_RUN.txt").read_text()) != 0 else "NOT_RUN")
    if e2e is not None:
        expected = {"PASS": 0, "FAIL": 4, "INCONCLUSIVE": 5, "INVALID": 6}[status]
        if stages["e2e"]["exit_code"] != expected:
            raise ValueError("Gate exit code differs from computed status")
        with (out / "S1P_G_E2E_PATHS.csv").open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        if len(rows) != 500 or sum(row["model"] == "independent" for row in rows) != 250 or (
                sum(row["model"] == "markov" for row in rows) != 250):
            raise ValueError("Incomplete paired path artifact")
    gates = dict(question_id="G1-MODEL-001", spec_commit=SPEC,
                 R0={"reused_from": RUN2, "passed": r0["passed"]},
                 eligible_m1_mount0_cases=obs["primary"],
                 G_OBS_1_and_2={name: obs["by_case"][name]["gates"] for name in obs["primary"]},
                 G_OBS_3="NOT_APPLICABLE_M2_NOT_USED",
                 G_SNAP="PASS" if snap and snap["node_check"]["passed"] else "NOT_COMPLETE",
                 G_E2E=status,
                 step2_primary="COMPLETE" if verdict else "NOT_RUN",
                 section_8_verdict=verdict["verdict"] if verdict else None,
                 step3="HELD")
    verified_arrays = grid_receipts(base, out)
    write(out / "S1P_GATES.json", gates)
    manifest = dict(
        question_id="G1-MODEL-001", role="IMPLEMENTER",
        repository="myoungsunk/sionna-resimulation",
        branch="research/g1-sweep-heading-floor-spec-20261113",
        spec_commit=SPEC, spec_git_blob="16abddc79b2bd512118aa82b9308861a5cfe1852",
        inherited_run2_commit=RUN2,
        code_provenance="RUN2 pinned source hashes plus local v3.3 execution additions",
        research_governance_sha256=dict(
            common="a5cca7d8a8d5f20f4a89ea9b6509da0b8d7506626aac4a47fa1d27891ff5ebdb",
            implementer="2380fb1fe7302870a6c2d825cc2e65a73e91138677e095b4e51db43ab9ea90da"),
        captured_utc=datetime.now(timezone.utc).isoformat(), stages=stages,
        exit_code=int((out / "EXIT_RUN.txt").read_text()), status=gates,
        runtime=(out / "verify.log").read_text().splitlines() if (out / "verify.log").exists() else None,
        input_sha256={k: v["sha256"] for k, v in read(code / "INPUTS_CHECK_1ce68f3.json")["inputs"].items()},
        bank_sha256={
            "LP_plus45_bank.npz": "b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b",
            "LP_minus45_bank.npz": "39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9",
        },
        code_sha256={f.name: sha(f) for f in sorted(code.iterdir()) if f.is_file()},
        output_sha256={f.relative_to(base).as_posix(): sha(f) for f in sorted(out.iterdir()) if f.is_file()},
        grid_files={name: {"bytes": length, "sha256": digest}
                    for name, length, digest in verified_arrays} |
                   {f.name: {"bytes": f.stat().st_size, "sha256": sha(f)}
                    for f in sorted((base / "grid").glob("*_INDEX.json"))},
    )
    write(out / "MANIFEST.json", manifest)
    print(status, gates["step2_primary"], len(manifest["output_sha256"]), "sealed output files")


if __name__ == "__main__":
    main()
