"""Replay the recovered Section 3.3 programs and persist their in-memory traces."""

import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import hashlib
from io import StringIO
import json
from pathlib import Path
import platform
import sys
import traceback

import numpy as np


ROOT = Path(__file__).resolve().parent
MODELS = ("A1", "A2_4", "A2_4_weak")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, payload):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")


def utc():
    return datetime.now(timezone.utc).isoformat()


def verify_binding(record):
    path = Path(record["path"])
    if not path.is_absolute():
        path = ROOT / path
    if sha(path) != record["sha256"]:
        raise ValueError(f"Frozen input or source hash differs: {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "runs")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    contract_path = ROOT / "RUN_CONTRACT.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    receipt = dict(question_id=contract["question_id"], started_utc=utc(),
                   contract_sha256=sha(contract_path), argv=sys.argv,
                   python=sys.version, executable=sys.executable,
                   numpy=np.__version__, platform=platform.platform(),
                   source_revision=contract["source_revision"],
                   trace_origin="Regenerated from recovered original executed code",
                   phases={}, outputs={})
    try:
        for record in contract["bindings"]:
            verify_binding(record)
        for model in MODELS:
            directory = output / model
            directory.mkdir()
            source_name = ("original_directional_weaken.py" if model.endswith("_weak")
                           else "original_main.py")
            source = (ROOT / source_name).read_text(encoding="utf-8")
            if source_name == "original_main.py":
                source = source.replace("__MODEL__", model)
            namespace = {"__name__": "__section33_original__"}
            captured = StringIO()
            with redirect_stdout(captured):
                exec(compile(source, source_name, "exec"), namespace)
            actual = json.loads(captured.getvalue())
            expected = json.loads((ROOT / "original_results" / f"{model}.json").read_bytes())
            if actual != expected:
                write(directory / "RESULT_DIFFERENCE.json", dict(actual=actual, expected=expected))
                raise ValueError(f"Regenerated result differs from original execution: {model}")
            write(directory / "RESULT.json", actual)
            for name, original in namespace["traces"].items():
                trace = dict(original)
                trace.update(t=namespace["t"], pose_id=namespace["p"]["pose_id"],
                             near=namespace["near"], rho=namespace["rho"])
                path = directory / f"{name}.npz"
                with path.open("xb") as stream:
                    np.savez_compressed(stream, **trace)
            # Preserve unrounded scores and bootstrap intervals as well as the
            # six-decimal original console result.
            write(directory / "SCORES.json", namespace["scores"])
            receipt["phases"][model] = dict(status="PASS", original_result_exact=True,
                                           traces=len(namespace["traces"]),
                                           parity_all=actual["parity_all"],
                                           parity_base=actual["parity_base"])
            print(f"{model}: original result exact, {len(namespace['traces'])} traces saved", flush=True)
        receipt.update(status="PASS", exit_code=0)
    except BaseException as exc:
        receipt.update(status="FAIL", exit_code=1, error=str(exc), traceback=traceback.format_exc())
        raise
    finally:
        for path in sorted(output.rglob("*")):
            if path.is_file():
                receipt["outputs"][path.relative_to(output).as_posix()] = sha(path)
        receipt["finished_utc"] = utc()
        write(output / "EXECUTION.json", receipt)


if __name__ == "__main__":
    main()
