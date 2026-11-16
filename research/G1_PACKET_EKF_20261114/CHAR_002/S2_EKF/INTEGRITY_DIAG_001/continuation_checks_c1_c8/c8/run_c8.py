"""Independent invocation of V3 from committed sources and authenticated frozen inputs."""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import traceback

import numpy as np
import scipy
from scipy.stats import chi2


HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE.parents[1]
ORIGINAL = ARTIFACTS / "continuation_ks"
CHECKOUT = ARTIFACTS.parents[1] / "g1_int_diag001_publication_20261115"
REVISION = "8305058bcea6a0e29b45675ea148bfa0ee85aa0c"
S2_TREE = "research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF"
DIAG_TREE = f"{S2_TREE}/INTEGRITY_DIAG_001"
KS_TREE = f"{DIAG_TREE}/continuation_ks"
CONTRACT_NAME = "RUN_CONTRACT_RETRY_03.json"
STAGE = HERE / "stage"
DIAG = STAGE / "diag"
KS = DIAG / "continuation_ks"
S2 = STAGE / "s2"
NATIVE = STAGE / "R45_sources"
OUT = HERE / "replay"
PARENT_RECEIPT_SHA256 = "d28f44847a76af193aa7483c83f7af986c19a044258e43f15125c9d86596ca2e"
ARMS = {"a": ("oracle", False), "c": ("sensitivity_matched_distance_length", False),
        "a_prime": ("oracle", True)}
ATOL = 1e-12


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def write(path, data):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write("\n")


def blob(name):
    return subprocess.check_output(["git", "-C", str(CHECKOUT), "show", f"{REVISION}:{name}"])


def check_digest(path, expected):
    if sha(path) != expected:
        raise ValueError(f"SHA-256 mismatch: {path}")


def stage_blob(repo_path, target, expected, records):
    content = blob(repo_path)
    if hashlib.sha256(content).hexdigest() != expected:
        raise ValueError(f"Committed source/data changed: {repo_path}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(content)
    records[repo_path] = {"stage": str(target.relative_to(HERE)), "sha256": expected}


def independently_score(trace, truth):
    diff = trace["x"][:, :3] - truth
    diff[:, 2] = np.arctan2(np.sin(diff[:, 2]), np.cos(diff[:, 2]))
    cov = trace["P"][:, :3, :3]
    pose_nees = np.einsum("ni,ni->n", diff, np.linalg.solve(cov, diff[..., None])[..., 0])
    xy = diff[:, :2]
    xy_nees = np.einsum("ni,ni->n", xy, np.linalg.solve(cov[:, :2, :2], xy[..., None])[..., 0])
    return dict(
        n=len(diff), heading_rmse_deg=float(np.rad2deg(np.sqrt(np.mean(diff[:, 2] ** 2)))),
        xy_rmse_cm=float(100 * np.sqrt(np.mean(np.sum(xy ** 2, axis=1)))),
        mean_nees3=float(np.mean(pose_nees)), pose95_coverage=float(np.mean(pose_nees <= chi2.ppf(.95, 3))),
        xy95_coverage=float(np.mean(xy_nees <= chi2.ppf(.95, 2))),
        heading95_coverage=float(np.mean(diff[:, 2] ** 2 <= 1.96 ** 2 * cov[:, 2, 2]))
    )


def compare(trace, path):
    maximum = {}
    exact = {}
    with np.load(path, allow_pickle=False) as original:
        if set(original.files) != set(trace):
            raise ValueError(f"Trace field mismatch: {path}")
        for key, actual in trace.items():
            expected = original[key]
            if actual.dtype != expected.dtype or actual.shape != expected.shape:
                raise ValueError(f"Trace metadata mismatch: {path}/{key}")
            if actual.dtype.kind == "f":
                np.testing.assert_allclose(actual, expected, atol=ATOL, rtol=ATOL, equal_nan=True, err_msg=key)
                good = np.isfinite(actual) & np.isfinite(expected)
                maximum[key] = float(np.max(abs(actual[good] - expected[good]), initial=0.))
            else:
                np.testing.assert_array_equal(actual, expected, err_msg=key)
                maximum[key] = 0.
            exact[key] = bool(np.array_equal(actual, expected, equal_nan=True))
    return dict(field_count=len(exact), exact_fields=sum(exact.values()), max_abs_by_field=maximum)


def main(receipt):
    contract_source = ORIGINAL / CONTRACT_NAME
    contract_hash = sha(contract_source)
    lock = read(contract_source)
    original_run = ORIGINAL / "run_03"
    output_record = original_run / "EXECUTION.json"
    check_digest(output_record, PARENT_RECEIPT_SHA256)
    anchor = read(output_record)
    if anchor["status"] != "PASS_EXECUTION" or anchor["contract_sha256"] != contract_hash:
        raise ValueError("Frozen V3 execution and contract mismatch")
    receipt.update(contract_sha256=contract_hash, original_execution_sha256=PARENT_RECEIPT_SHA256,
                   governance=lock["governance"], frozen_input_count=len(lock["inputs"]))
    staged_blobs = receipt["staged_committed_blobs"]
    manifest = json.loads(blob(f"{KS_TREE}/PUBLICATION_MANIFEST.json"))
    if manifest["frozen_contract_sha256"] != contract_hash:
        raise ValueError("Published contract SHA mismatch")
    stage_blob(f"{KS_TREE}/{CONTRACT_NAME}", KS / CONTRACT_NAME, contract_hash, staged_blobs)
    stage_blob(f"{KS_TREE}/PLAN_FROZEN.md", KS / "PLAN_FROZEN.md", lock["plan"]["sha256"], staged_blobs)

    native_original = Path(read(ARTIFACTS / "RUN_CONTRACT.json")["native"])
    for entry in [*lock["inputs"], *lock["derived_sources"]]:
        source, expected = Path(entry["path"]), entry["sha256"]
        if source.is_relative_to(native_original):
            relative = source.relative_to(native_original)
            dest = NATIVE / relative
            if source.suffix == ".py":
                stage_blob(f"{KS_TREE}/replay_inputs/R45_sources/{relative.as_posix()}", dest, expected, staged_blobs)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                check_digest(source, expected)
                os.link(source, dest)
                receipt["staged_frozen_links"][str(dest.relative_to(HERE))] = expected
        elif source.is_relative_to(ARTIFACTS):
            relative = source.relative_to(ARTIFACTS)
            if source.suffix in {".py", ".json"}:
                stage_blob(f"{DIAG_TREE}/{relative.as_posix()}", DIAG / relative, expected, staged_blobs)
            elif source.suffix == ".npz" and relative.parts[0] in {"attempt_02", "continuation_d2_d3"}:
                dest = DIAG / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                check_digest(source, expected)
                shutil.copyfile(source, dest)
                check_digest(dest, expected)
                receipt["staged_frozen_copies"][str(dest.relative_to(HERE))] = expected
        elif source.suffix == ".py":
            stage_blob(f"{S2_TREE}/{source.name}", S2 / source.name, expected, staged_blobs)

    check_digest(KS / CONTRACT_NAME, contract_hash)
    sys.path[:0] = [str(KS), str(S2), str(NATIVE / "src")]
    import run_ks
    import run_structure

    lock = run_ks.authenticate(KS / CONTRACT_NAME)
    receipt["original_absolute_inputs_authenticated"] = True

    authenticate_structure = run_structure.authenticate

    def bind_staged_sources():
        paths = list(sys.path)
        try:
            structural, base = authenticate_structure()
        finally:
            sys.path[:] = paths
        return structural, base | {"s2": str(S2), "native": str(NATIVE)}

    run_structure.authenticate = bind_staged_sources
    OUT.mkdir(exist_ok=False)
    print("C8 authenticates inputs and runs staged preflight", flush=True)
    core, online, model, _, primary, cases, fit_cases, preflight = run_ks.read_setup(lock)
    write(OUT / "PREFLIGHT.json", preflight)
    from ks_fit import v1_v2, v8
    from ks_replay import check_trace, clipping_summary, replay_ks
    from ks_diagnostics import scores_with_blocks, v3_status
    from verify_s2 import from_trace

    # Refit the V3 parameter table from its registered donor replays.
    print("C8 recomputes V8/V1/V2 parameters", flush=True)
    _, internal = v8(fit_cases)
    _, _, fitted = v1_v2(fit_cases, internal)
    fit_file = OUT / "FITTED_PARAMETERS.json"
    write(fit_file, fitted)
    original_fit = original_run / fit_file.name
    check_digest(original_fit, anchor["outputs"][fit_file.name])
    if read(fit_file) != read(original_fit):
        raise ValueError("Refitted parameters differ from frozen execution")
    receipt["refitted_parameters_exact"] = True
    source_v3 = original_run / "V3.json"
    check_digest(source_v3, anchor["outputs"][source_v3.name])
    original_v3 = read(source_v3)
    r4 = cases["R4"]
    truth = primary["R4"]["truth"]
    rows = {"LORO": from_trace(r4["loro"], truth)}
    checks = {}
    clipping = {}
    for arm, (variant, uncap) in ARMS.items():
        if uncap and not clipping["a"]["fraction"] > lock["rules"]["V3_uncap_above"]:
            raise ValueError("Fitted oracle does not meet registered cap-override trigger")
        replay = replay_ks(r4, core, online, model, run_ks.noise_for(fitted, "R4", variant), uncap_slow=uncap)
        check_trace(replay, r4)
        np.testing.assert_array_equal(replay["mask"], r4["mask"])
        clipping[arm] = clipping_summary(replay)
        trace_name = f"V3_{arm}.npz"
        destination = OUT / trace_name
        np.savez_compressed(destination, **replay)
        source_trace = original_run / trace_name
        check_digest(source_trace, anchor["outputs"][trace_name])
        checks[arm] = compare(replay, source_trace)
        scores = independently_score(replay, truth)
        for metric, value in scores.items():
            np.testing.assert_allclose(value, original_v3["scores"]["point"]["R4"][arm][metric],
                                       atol=ATOL, rtol=ATOL, err_msg=f"{arm}/{metric}")
        rows[arm] = from_trace(replay, truth)
        checks[arm].update(independent_point_scores=scores, mask_accepted=int(replay["mask"].sum()),
                           frozen_trace_sha256=anchor["outputs"][trace_name],
                           identical_npz_sha256=sha(destination) == anchor["outputs"][trace_name])
        print(f"C8 replay {arm} complete", flush=True)
    contrasts = [(arm, "LORO") for arm in ARMS] + [("a_prime", "a")]
    scores = scores_with_blocks({"R4": rows}, {"R4": r4["packet"]["t"]}, contrasts)
    for arm in ARMS:
        decision = v3_status(scores, arm, clipping[arm]["supported"])
        if decision != original_v3["decisions"][arm] or clipping[arm] != original_v3["clipping"][arm]:
            raise ValueError(f"V3 decision/clipping mismatch: {arm}")
        checks[arm]["decision"] = decision
    for width in scores["blocks"]:
        block = scores["blocks"][width]["by_group"]["R4"]
        frozen_block = original_v3["scores"]["blocks"][width]["by_group"]["R4"]
        if any(values != frozen_block["absolute_ci95"][arm] for arm, values in block["absolute_ci95"].items()):
            raise ValueError(f"V3 absolute block CI mismatch: {width}")
        if any(values != frozen_block["paired_ci95"][key] for key, values in block["paired_ci95"].items()):
            raise ValueError(f"V3 paired block CI mismatch: {width}")
    write(OUT / "V3.json", {"scores": scores, "checks": checks, "clipping": clipping})
    receipt["arms"] = checks


if __name__ == "__main__":
    receipt = dict(question="G1-INT-001/KS-TRANSFER/C8", role="INDEPENDENT_REPLAY_IMPLEMENTER",
                   repository="myoungsunk/sionna-resimulation",
                   branch="research/g1-sweep-heading-floor-spec-20261113", commit=REVISION,
                   started_utc=utc(), command=[sys.executable, *sys.orig_argv[1:]],
                   python=sys.version, numpy=np.__version__, scipy=scipy.__version__,
                   platform=platform.platform(), cwd=os.getcwd(), runner_sha256=sha(Path(__file__)),
                   isolation=("Fresh Python -I process and fresh local source/output layout from committed blobs. "
                              "Same host, installed runtime, and SHA-authenticated original frozen packet/evaluator "
                              "assets and governance. FFD bank files hardlinked read-only by use. No independent "
                              "RF data, alternate KS implementation, or remote-only reconstruction."),
                   staged_committed_blobs={}, staged_frozen_links={}, staged_frozen_copies={})
    try:
        main(receipt)
        receipt.update(status="PASS_C8_REPLAY", exit_code=0)
    except Exception as error:
        receipt.update(status="FAIL_C8_REPLAY", exit_code=1, reason=repr(error))
        traceback.print_exc()
    finally:
        receipt["finished_utc"] = utc()
        receipt["outputs"] = {file.name: sha(file) for file in sorted(OUT.glob("*"))}
        write(HERE / "EXECUTION_C8.json", receipt)
    raise SystemExit(receipt["exit_code"])
