"""Record bounded synthetic implementation checks, never M7 performance runs."""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import traceback
import unittest

import numpy as np

import check_m7_replay
import m7_inputs
import m7_replay
import m7_spec


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(plan, output_dir):
    root, plan, out = Path(__file__).resolve().parent, Path(plan), Path(output_dir)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError("Preserve previous check evidence; use a new attempt directory")
    out.mkdir(parents=True, exist_ok=True)
    paths = sorted(root.glob("*.py"))
    before = {p.name: sha(p) for p in paths}
    report = dict(classification="SYNTHETIC_IMPLEMENTATION_ONLY", status="FAIL_CHECKS",
                  started_utc=datetime.now(timezone.utc).isoformat(),
                  command=[sys.executable, *sys.argv], python=sys.version, numpy=np.__version__,
                  plan=dict(path=str(plan.resolve()), commit=m7_spec.PLAN_COMMIT,
                            expected_sha256=m7_spec.PLAN_SHA256), source_sha256=before,
                  authorization=m7_spec.execution_policy()["authorization"],
                  actual_input_generation="NOT_RUN", actual_donor_fit="NOT_RUN",
                  native_archived_parity="NOT_RUN", M7_research_replay="NOT_RUN",
                  scientific_acceptance="NOT_ASSESSED")
    log = io.StringIO()
    try:
        report["plan"]["actual_sha256"] = sha(plan)
        if sha(plan) != m7_spec.PLAN_SHA256:
            raise ValueError("Published revised M7 plan hash differs")
        for path in paths:
            compile(path.read_text(encoding="utf-8-sig"), str(path), "exec")
        report["compile"] = dict(status="PASS", source_count=len(paths))
        if tuple(m7_replay.ARMS) != m7_spec.ARMS:
            raise ValueError("Replay/spec arm sets differ")
        for condition, policy in m7_spec.CONDITIONS.items():
            if m7_replay.CONDITION_GYRO[condition] != (policy["injected_N_deg_sqrt_s"],
                                                       policy["filter_N_deg_sqrt_s"]):
                raise ValueError("Replay/spec gyro Q conditions differ")
        if m7_inputs.CONDITIONS != m7_spec.MAIN_CONDITIONS or m7_inputs.EXPECTED_COUNT != 120:
            raise ValueError("Input/spec condition grid differs")
        report["expected_grid"] = m7_spec.validate_cell_index(m7_spec.expected_cells())
        suite = unittest.TestLoader().loadTestsFromNames(
            ["test_m7_support", "test_m7_assess", "test_m7_score", "test_m7_report"])
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
        report["unit_tests"] = dict(tests_run=result.testsRun, failures=len(result.failures),
                                    errors=len(result.errors), skipped=len(result.skipped))
        if not result.wasSuccessful() or result.skipped:
            raise AssertionError("Synthetic unit tests did not all pass")
        report["replay_checks"] = check_m7_replay.run_synthetic_checks()
        report["status"] = "PASS_SYNTHETIC_IMPLEMENTATION_CHECKS"
    except BaseException as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        log.write(traceback.format_exc())
    finally:
        after = {p.name: sha(p) for p in sorted(root.glob("*.py"))}
        report["sources_unchanged"] = before == after
        if before != after:
            report["status"] = "FAIL_SOURCE_CHANGED_DURING_CHECKS"
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        with (out / "UNITTEST.log").open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(log.getvalue())
        report["unittest_log_sha256"] = sha(out / "UNITTEST.log")
        with (out / "CHECKS.json").open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.write("\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    result = verify(args.plan, args.output_dir)
    print(json.dumps({key: result[key] for key in
          ("status", "unit_tests", "expected_grid", "actual_input_generation",
           "actual_donor_fit", "native_archived_parity", "M7_research_replay") if key in result},
          ensure_ascii=False))
    sys.exit(0 if result["status"] == "PASS_SYNTHETIC_IMPLEMENTATION_CHECKS" else 1)
