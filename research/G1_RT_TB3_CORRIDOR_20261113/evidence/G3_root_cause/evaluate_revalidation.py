"""Evaluate completed 400k traces with the evaluator that issued the original G3 verdict."""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/g3/recovery")
import run_tb3_g3 as g3


BASE = Path("/g3")
RUN = Path("/revalidation")
RECORD = Path("/evaluation")


def main():
    started = datetime.now(timezone.utc)
    original = g3.read(BASE / "analysis/G3.json")
    g3.verify(Path(g3.__file__), original["evaluator_sha256"])
    scope = g3.read(BASE / "input/G3_CONTRACT.json")
    g3.verify(BASE / "input/G3_CONTRACT.json", original["contract_sha256"])
    contract_path = RUN / "REVALIDATION_CONTRACT.json"
    contract = g3.read(contract_path)
    if contract["frozen_scope_sha256"] != original["contract_sha256"]:
        raise ValueError("Scope identity mismatch")
    g3.verify(BASE / "analysis/G3.json", contract["frozen_gate_sha256"])
    g3.verify(RUN / "revalidate_tb3_g3_reference.py", contract["runner_sha256"])

    expected = {(case, f"{i}/6") for case in g3.CASES for i in range(6)}
    shards = g3.read(RUN / "SHARD_EXIT.json")
    actual = {(row["case"], row["shard"]) for row in shards}
    if len(shards) != len(expected) or actual != expected or any(row["exit_code"] for row in shards):
        raise ValueError("Incomplete trace shards")
    for line in (RUN / "TRACE_SHA256.txt").read_text().splitlines():
        digest, file = line.split(maxsplit=1)
        g3.verify(RUN / file, digest)
    for file, digest in contract["production_arm_sha256"].items():
        g3.verify(RUN / file, digest)

    g3.INPUT = BASE / "input"
    g3.OUT = RUN / "output"
    for case in g3.CASES:
        for task in g3.read(g3.INPUT / "cases" / f"{case}.json"):
            tag = task["tag"]
            path = g3.OUT / case / "bin_by_bin" / f"{tag}_trace_receipt.json"
            receipt = g3.read(path)
            if (receipt["solver"] != contract["reference_arm_solver"] or receipt["n_nodes"] != 257
                    or receipt["tag"] != tag):
                raise ValueError(f"Invalid reference trace receipt {path}")
    report = RECORD / "analysis"
    report.mkdir(exist_ok=False)
    t0 = time.monotonic()
    result = g3.evaluate(scope, g3.parity_file(), report)
    finished = datetime.now(timezone.utc)
    trace_started = datetime.fromisoformat((RUN / "STARTED_UTC.txt").read_text().strip())
    trace_finished = datetime.fromisoformat((RUN / "FINISHED_UTC.txt").read_text().strip())
    result.update(kind="G3_REFERENCE_REVALIDATION", started_utc=trace_started.isoformat(),
                  evaluation_started_utc=started.isoformat(), finished_utc=finished.isoformat(),
                  contract_sha256=original["contract_sha256"], evaluator_sha256=original["evaluator_sha256"],
                  parity_sha256=scope["parity_sha256"], revalidation_contract_sha256=g3.sha(contract_path),
                  trace_manifest_sha256=g3.sha(RUN / "TRACE_SHA256.txt"),
                  reference_rays=contract["reference_arm_solver"]["samples_per_src"],
                  trace_stage_s=(trace_finished - trace_started).total_seconds(), evaluation_s=time.monotonic()-t0,
                  original_g3_status=original["status"], original_g3_sha256=contract["frozen_gate_sha256"])
    g3.write(report / "G3.json", result)
    print("G3 reference revalidation " + result["status"], flush=True)
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
