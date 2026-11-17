"""Hash-pinned, immutable online-only M7 replay cells.

No execution occurs at import. Actual replay requires an explicit GO contract
and a passing pre-replay receipt; scoring and evaluator access stay outside.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

import numpy as np

from m7_inputs import KEYS, arrays, checked, resolve_input
from m7_replay import load_environment, replay
from m7_spec import PLAN_COMMIT, PLAN_SHA256, expected_cells, validate_cell_index


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write_new(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def _verify_records(node):
    if isinstance(node, dict):
        if {"path", "sha256"} <= node.keys():
            checked(node)
        else:
            for value in node.values():
                _verify_records(value)
    elif isinstance(node, list):
        for value in node:
            _verify_records(value)


def _contract(value):
    if isinstance(value, (str, Path)):
        path = Path(value).resolve()
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        record = dict(path=str(path), sha256=sha(path), representation="file_bytes")
    elif isinstance(value, dict):
        data = value
        content = json.dumps(data, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
        record = dict(path=None, sha256=hashlib.sha256(content).hexdigest(),
                      representation="canonical_json")
    else:
        raise TypeError("Contract must be a JSON path or mapping")
    if data.get("authorization", {}).get("replay") != "GO":
        raise ValueError("replay GO is absent")
    if data["plan"]["commit"] != PLAN_COMMIT or data["plan"]["sha256"] != PLAN_SHA256:
        raise ValueError("M7 revised plan identity differs")
    checked(data["plan"])
    sources = data["sources"]
    root = Path(__file__).resolve().parent
    for name in ("m7_run.py", "m7_replay.py", "m7_inputs.py", "m7_spec.py"):
        pinned = [r for r in sources if Path(r["path"]).resolve() == root / name]
        if len(pinned) != 1:
            raise ValueError(f"Contract must pin this exact {name} once")
    if not data["model_assets"]:
        raise ValueError("Frozen native/model assets are required")
    policy_names = {Path(record["path"]).name for record in data["governance"]}
    if not {"COMMON_CONTRACT.md", "ROLE_IMPLEMENTER.md"} <= policy_names:
        raise ValueError("Frozen COMMON_CONTRACT/ROLE_IMPLEMENTER are required")
    for section in (sources, data["model_assets"], data["governance"],
                    data["input_index"], data["parent_contract"], data["prerequisite_checks"]):
        _verify_records(section)
    validate_cell_index(data["expected_cells"])
    prerequisite = json.loads(checked(data["prerequisite_checks"]).read_text(encoding="utf-8-sig"))
    required = data["prerequisite_checks"].get("required_status", "PASS_M7_PRE_REPLAY_CHECKS")
    if not str(required).startswith("PASS") or prerequisite.get("status") != required:
        raise ValueError("Actual pre-replay checks have not passed")
    return data, record


def _identity(contract, cell):
    lookup = {r["id"]: r for r in contract["expected_cells"]}
    row = lookup.get(cell if isinstance(cell, str) else cell["id"])
    if row is None or (not isinstance(cell, str) and row != cell):
        raise ValueError("Unknown or relabelled replay cell")
    return row


def _cell_dir(root, cell):
    root = Path(root).resolve()
    target = root.joinpath("cells", *cell["id"].split("/"))
    target.relative_to(root)
    return target


def _validate_trace(trace, packet, cell):
    n = len(packet["t"])
    for key, value in trace.items():
        value = np.asarray(value)
        if value.dtype.kind in "biuf":
            if not np.isfinite(value).all():
                raise ValueError(f"Nonfinite trace field {key}")
        elif not (key.startswith("metadata_") and value.dtype.kind in "US"):
            raise ValueError(f"Unexpected trace dtype: {key}")
    for key in ("t", "pose_id"):
        np.testing.assert_array_equal(trace[key], packet[key])
    if trace["x"].shape != (n, 4) or trace["P"].shape != (n, 4, 4):
        raise ValueError("Trace navigation grid differs")
    if trace["mask"].shape != (n,) or trace["mask"].dtype.kind != "b":
        raise ValueError("Invalid acceptance mask")
    np.testing.assert_allclose(trace["P"], trace["P"].swapaxes(-1, -2), atol=1e-10, rtol=0.)
    np.linalg.cholesky(trace["P"])
    for key, expected in (("metadata_arm", cell["arm"]),
                          ("metadata_condition", cell["condition"]),
                          ("metadata_rref_policy", "own"),
                          ("metadata_gate_mode", cell["mode"])):
        if str(np.asarray(trace[key]).item()) != expected:
            raise ValueError(f"Trace identity differs: {key}")


def _reuse(directory, contract_record, cell, input_record, packet):
    path = directory / "EXECUTION.json"
    if not path.is_file():
        raise FileExistsError(f"Preserve incomplete cell; use a new attempt: {directory}")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if (receipt.get("status") != "PASS_EXECUTION" or receipt.get("cell") != cell
            or receipt.get("contract") != contract_record or receipt.get("input") != input_record):
        raise ValueError(f"Existing cell is not a verified reuse of this contract: {directory}")
    trace_record = receipt["trace"]
    if cell["trace_alias_of"]:
        checked(receipt["alias_receipt"])
    trace = arrays(checked(trace_record))
    expected_cell = cell
    if cell["trace_alias_of"]:
        expected_cell = dict(cell, mode="own")
    _validate_trace(trace, packet, expected_cell)
    return receipt


def run_cell(contract, cell, output_root, env=None):
    """Run one frozen cell or verify exact reuse; never overwrite evidence.

    contract is preferably the frozen JSON path. An env may be reused by a
    caller in one process; native assets are still hash-checked on every call.
    """
    data, contract_record = _contract(contract)
    cell = _identity(data, cell)
    stop = os.environ.get("MANAGED_PROCESS_STOP_FILE")
    if stop and Path(stop).exists():
        raise InterruptedError("Managed stop requested before the next replay cell")
    index = json.loads(checked(data["input_index"]).read_text(encoding="utf-8"))
    input_record = resolve_input(index, cell["condition"], cell["seed"], cell["route"])
    packet = arrays(checked(input_record))
    if set(packet) != set(KEYS):
        raise ValueError("Only online fields may enter the candidate replay")
    directory = _cell_dir(output_root, cell)
    if directory.exists():
        return _reuse(directory, contract_record, cell, input_record, packet)
    params = data["parameters"][cell["route"]]
    kwargs = dict(sigma_b=params["sigma_b"], condition=cell["condition"], rref_policy="own",
                  sigma_rad=params["sigma_rad"] if cell["arm"] in ("H3", "H4") else 0.)
    if cell["arm"] in ("H3", "H5", "H5P"):
        kwargs["q_table"] = params["qprime_table"] if cell["arm"] == "H5P" else params["q_table"]
    fixed_record = None
    if cell["mode"] == "fixed" and not cell["trace_alias_of"]:
        fixed_record = data["fixed_masks"][cell["route"]]
        kwargs["fixed_mask"] = arrays(checked(fixed_record))[fixed_record.get("field", "mask")]
    alias_receipt = None
    if cell["trace_alias_of"]:
        alias_cell = _identity(data, cell["trace_alias_of"])
        alias_directory = _cell_dir(output_root, alias_cell)
        alias_receipt = _reuse(alias_directory, contract_record, alias_cell, input_record, packet)
    elif env is None:
        env = load_environment(checked(data["parent_contract"]))
    directory.mkdir(parents=True, exist_ok=False)
    receipt = dict(status="FAIL_EXECUTION", exit_code=1, started_utc=datetime.now(timezone.utc).isoformat(),
                   command=[sys.executable, *sys.argv], python=sys.version, numpy=np.__version__,
                   role="IMPLEMENTER", question_id="G1-INT-001/M7-STAGE1", cell=cell,
                   contract=contract_record, input=input_record, sources=data["sources"],
                   governance=data["governance"], model_assets=data["model_assets"],
                   prerequisite_checks=data["prerequisite_checks"], fixed_mask=fixed_record,
                   executed=cell["execute"], trace_alias_of=cell["trace_alias_of"])
    try:
        if alias_receipt is not None:
            receipt["trace"] = alias_receipt["trace"]
            receipt["alias_receipt"] = dict(path=str(alias_directory / "EXECUTION.json"),
                                             sha256=sha(alias_directory / "EXECUTION.json"))
        else:
            trace = replay(packet, env, cell["arm"], **kwargs)
            _validate_trace(trace, packet, cell)
            trace_path = directory / "trace.npz"
            with trace_path.open("xb") as stream:
                np.savez_compressed(stream, **trace)
            loaded = arrays(trace_path)
            for key in trace:
                np.testing.assert_array_equal(loaded[key], trace[key])
            receipt["trace"] = dict(path=str(trace_path), sha256=sha(trace_path))
        # Verify that neither frozen source nor input drifted during this cell.
        _, final_contract = _contract(contract)
        if final_contract != contract_record:
            raise ValueError("Frozen contract changed during replay")
        checked(input_record)
        receipt.update(status="PASS_EXECUTION", exit_code=0)
    except BaseException as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        receipt["finished_utc"] = datetime.now(timezone.utc).isoformat()
        _write_new(directory / "EXECUTION.json", receipt)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--cell-id")
    args = parser.parse_args()
    data, _ = _contract(args.contract)
    cells = [_identity(data, args.cell_id)] if args.cell_id else data["expected_cells"]
    env = None
    for cell in cells:
        if not cell["trace_alias_of"] and env is None:
            env = load_environment(checked(data["parent_contract"]))
        result = run_cell(args.contract, cell, args.output_dir, env=env)
        print(json.dumps(dict(cell=cell["id"], status=result["status"],
                              executed=result["executed"], trace=result["trace"]), ensure_ascii=False), flush=True)
