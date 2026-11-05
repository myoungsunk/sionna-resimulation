"""E0-A2 control input preparation with an explicitly new byte identity.

This module never imports a receiver/model, uses archived filter states, or
runs an EKF.  Historical ds byte recovery remains unresolved.  The caller
must freeze the returned registry hash in its run contract before recursion.
"""
from __future__ import annotations

import ast
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys

import numpy as np

from .e0_baseline import PACKETS, STUDY_BASE, array_sha256, payload, read_npz, sha256


SCHEMA = "FP_SC_001_E0_A2_CONTROLS_V1"
IDENTITY = "LINUX_REMATERIALIZED_ORIGINAL_RECIPE"
HISTORICAL_STATUS = "UNRESOLVED_EXACT_HISTORICAL_DS_BYTES"
ROUTE_ROWS = {"R4": 742, "R5": 1415}
SEED = 10
KNOWN_REMATERIALIZED_DS = {
    "R4": "3997268152be79329a4e7adcce82ea2edcf12dbfbaad10049ed748a75288ced3",
    "R5": "d67b1945dbb20d7be32d4c0309b99478661bd1ad594d6d541133d7e934199e65",
}
RECIPE_PATH = "research/DS_MASK_CAUSAL_X1_X2_20261026/pol_bias_model/exp_pb.py"
CORE_PATH = "research/EKF4_RANGE_S_STAGED_20261014/core.py"
HISTORICAL_REGISTRY = STUDY_BASE / "A0_R3_REFIT/BASE_INPUTS.json"
PINNED = {
    RECIPE_PATH: "a637c3ef0322546215cab7aef76889f1e6e256048bb2821f1b9967679e534972",
    CORE_PATH: "1abdac002631e1de2303b0ef7c39c6c9eb619b53d9ba9fd8d89d1a3cd9c630d1",
    "src/qclean_uwb/drivesim/sensor_v2.py": "56ea1c8f5afbd1c9662885366155c490d7ad01009d8a0bf8ebe3d7f85647c2ac",
    "src/qclean_uwb/drivesim/sensors.py": "2285db90b465e13f90c99d66ae0ba867602abc148a1b1ba0bc02a565e9681118",
    HISTORICAL_REGISTRY.as_posix(): "512dc5b5e0e52db3b653171e241fd7e906fcdb93336a2ab41adf51a96d20f554",
    (PACKETS / "MANIFEST.json").as_posix(): "54570bf06aec36065ce6851fac070ff67455e261109c82a1c26335c99c38f99a",
}
ARRAY_KEYS = ("ds", "gy", "dt", "x0", "t", "pose_id")


def _put_new(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")


def _inside(repo: Path, relative: str) -> Path:
    path = repo / relative
    if Path(relative).is_absolute() or ".." in Path(relative).parts or not path.resolve().is_relative_to(repo.resolve()):
        raise ValueError("A2_PATH_OUTSIDE_REPOSITORY")
    return path


def _source_records(repo: Path) -> dict:
    records = {}
    for relative, expected in PINNED.items():
        path = payload(_inside(repo, relative), expected)
        records[relative] = {"sha256": expected, "size": path.stat().st_size}
    return records


def _selected_ast(source: str, functions: tuple[str, ...], assignments: tuple[str, ...] = ()) -> ast.Module:
    nodes = []
    found = set()
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name in functions:
            nodes.append(node)
            found.add(node.name)
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in assignments:
            nodes.append(node)
            found.add(node.targets[0].id)
    if found != set(functions + assignments):
        raise ValueError("A2_ORIGINAL_RECIPE_AST_MISSING")
    return ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))


def _original_recipe(repo: Path):
    # Execute only the pinned original control function/constants and wrap;
    # importing exp_pb would initialize unrelated historical model modules.
    from qclean_uwb.drivesim import sensor_v2, sensors
    for module, name in ((sensor_v2, "sensor_v2.py"), (sensors, "sensors.py")):
        if Path(module.__file__).resolve() != (repo / "src/qclean_uwb/drivesim" / name).resolve():
            raise ValueError("A2_SENSOR_IMPORT_OUTSIDE_PINNED_REPOSITORY")
    namespace = {"np": np, "math": math,
                 **{key: getattr(sensor_v2, key) for key in ("SensorV2Config", "generate", "motion_increments", "rng")}}
    core = _selected_ast((repo / CORE_PATH).read_text(), ("wrap",))
    recipe = _selected_ast((repo / RECIPE_PATH).read_text(), ("build_controls",), ("BIAS_LEVELS", "INITIAL_POSE_STD"))
    exec(compile(core, CORE_PATH, "exec"), namespace)
    exec(compile(recipe, RECIPE_PATH, "exec"), namespace)
    return namespace["build_controls"], {
        "method": "execute only pinned original build_controls/constants and core.wrap AST",
        "selected_ast_sha256": hashlib.sha256((ast.dump(core) + ast.dump(recipe)).encode()).hexdigest(),
        "uses_archived_state_or_prior": False,
        "per_row_value_adjustment": False,
        "runtime_selection_by_replay_metric": False,
    }


def _array_records(values: dict) -> dict:
    return {key: {"sha256": array_sha256(value), "shape": list(value.shape),
                  "dtype": value.dtype.str, "hash_order": "C"} for key, value in values.items()}


def _validate_control_arrays(values: dict, expected_n: int) -> None:
    if set(values) != set(ARRAY_KEYS):
        raise ValueError("A2_CONTROL_SCHEMA")
    for key in ARRAY_KEYS:
        value = values[key]
        shape = (3,) if key == "x0" else (expected_n,)
        dtype = np.dtype("int64") if key == "pose_id" else np.dtype("float64")
        if value.shape != shape or value.dtype != dtype or not np.isfinite(value).all():
            raise ValueError("A2_CONTROL_SHAPE_DTYPE_OR_FINITE: " + key)
    t = values["t"]
    if expected_n < 2 or len(np.unique(values["pose_id"])) != expected_n:
        raise ValueError("A2_DUPLICATE_POSE_OR_EMPTY")
    if t[0] != 0.0 or not np.all(np.abs(np.diff(t) - 0.2) <= 1e-9):
        raise ValueError("A2_NOT_ORIGINAL_5HZ_GRID")
    if not np.array_equal(values["dt"], np.r_[0.0, np.diff(t)]):
        raise ValueError("A2_DT_TIME_MISMATCH")
    if values["ds"][0] != 0.0 or values["gy"][0] != 0.0:
        raise ValueError("A2_INITIAL_INCREMENT_NONZERO")


def _historical_identity(values: dict, expected: dict) -> dict:
    actual = {key: array_sha256(values[key]) for key in ("ds", "gy", "dt", "x0")}
    matches = {key: actual[key] == expected[key] for key in actual}
    if not all(matches[key] for key in ("gy", "dt", "x0")):
        raise ValueError("A2_NON_DS_HISTORICAL_HASH_MISMATCH")
    if matches["ds"]:
        raise ValueError("A2_EXPECTED_REMATERIALIZED_IDENTITY_CHANGED")
    return {"status": HISTORICAL_STATUS, "exact_historical_array_matches": matches,
            "expected_array_sha256": expected, "actual_array_sha256": actual}


def _runtime(*, enforce: bool) -> dict:
    runtime = {"python": platform.python_version(), "python_full": sys.version,
               "numpy": np.__version__, "system": platform.system(), "machine": platform.machine(),
               "thread_and_dispatch_environment": {key: os.environ.get(key) for key in
                   ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_CORETYPE", "NPY_DISABLE_CPU_FEATURES")},
               "numpy_build": np.show_config(mode="dicts")}
    if enforce:
        if (runtime["python"], runtime["numpy"], runtime["system"], runtime["machine"]) != ("3.12.14", "2.3.5", "Linux", "x86_64"):
            raise ValueError("A2_PRIMARY_MATERIALIZATION_RUNTIME_MISMATCH")
        env = runtime["thread_and_dispatch_environment"]
        if any(env[key] != "1" for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")) or any(env[key] for key in ("OPENBLAS_CORETYPE", "NPY_DISABLE_CPU_FEATURES")):
            raise ValueError("A2_PRIMARY_THREAD_OR_DISPATCH_SETTINGS_MISMATCH")
    return runtime


def materialize_controls(repo: Path, output: Path, *, command: list[str] | None = None) -> dict:
    """Prepare four new inputs; refuse existing destinations and all EKF work."""
    repo, output = Path(repo).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError("A2_NEW_OUTPUT_REQUIRED: " + str(output))
    if not output.is_relative_to(repo):
        raise ValueError("A2_OUTPUT_MUST_BE_IN_REPOSITORY")
    runtime = _runtime(enforce=True)
    sources = _source_records(repo)
    build_controls, recipe = _original_recipe(repo)
    historical = json.loads((repo / HISTORICAL_REGISTRY).read_bytes())["controls"]
    packet_manifest = json.loads((repo / PACKETS / "MANIFEST.json").read_bytes())
    prepared = []
    for route, n in ROUTE_ROWS.items():
        for bias in ("B0", "L2"):
            truth_name = f"evaluator_truth/{route}_{bias}_TRUTH.npz"
            truth_path = repo / PACKETS / truth_name
            truth = read_npz(truth_path, packet_manifest[truth_name]["sha256"])
            if truth["truth"].shape != (n, 3) or truth["truth"].dtype != np.dtype("float64") or not np.isfinite(truth["truth"]).all():
                raise ValueError("A2_TRUTH_SCHEMA")
            packets = {}
            for channel in ("Full", "Native_LoS"):
                name = f"algorithm_input/{route}_aB_m0_{bias}_{channel}.npz"
                arrays = read_npz(repo / PACKETS / name, packet_manifest[name]["sha256"])
                if not all(np.array_equal(arrays[key], truth[key]) for key in ("t", "pose_id")):
                    raise ValueError("A2_PACKET_TRUTH_JOIN")
                packets[channel] = {"file": (PACKETS / name).as_posix(), **packet_manifest[name]}
            key = f"{route}_aB_m0_{bias}_{SEED}"
            ds, gy, elapsed, x0 = build_controls(truth["t"], truth["truth"], bias, SEED)
            values = {name: np.ascontiguousarray(value) for name, value in
                      dict(ds=ds, gy=gy, dt=elapsed, x0=x0, t=truth["t"], pose_id=truth["pose_id"]).items()}
            _validate_control_arrays(values, n)
            if array_sha256(values["ds"]) != KNOWN_REMATERIALIZED_DS[route]:
                raise ValueError("A2_PREREGISTERED_PRIMARY_DS_HASH_MISMATCH")
            identity = _historical_identity(values, historical[key])
            entry = {"identity": IDENTITY, "route": route, "bias": bias, "seed": SEED, "n": n,
                     "time_min_s": float(values["t"][0]), "time_max_s": float(values["t"][-1]),
                     "max_delta_t_s": float(np.max(values["dt"])), "arrays": _array_records(values),
                     "historical_identity": identity,
                     "truth": {"file": truth_path.relative_to(repo).as_posix(), **packet_manifest[truth_name],
                               "arrays": _array_records({k: truth[k] for k in ("t", "pose_id", "truth")})},
                     "packets": packets}
            prepared.append((key, values, entry))
    # Complete validation precedes any output; subsequent files are exclusive.
    output.mkdir(parents=True, exist_ok=False)
    entries = {}
    for key, values, entry in prepared:
        path = output / (key + ".npz")
        with path.open("xb") as handle:
            np.savez_compressed(handle, **values)
        entry.update(file=path.relative_to(repo).as_posix(), sha256=sha256(path), size=path.stat().st_size)
        entries[key] = entry
    producers = {Path(__file__).resolve().relative_to(repo).as_posix(): sha256(Path(__file__).resolve())}
    cli = repo / "scripts/fp_sc_materialize_controls.py"
    if cli.is_file():
        producers[cli.relative_to(repo).as_posix()] = sha256(cli)
    registry = {"schema": SCHEMA, "identity": IDENTITY, "amendment_id": "FP-SC-001-E0-A2",
                "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "command": command or [],
                "status": "INPUTS_PREPARED_NOT_A_SCIENTIFIC_RUN", "historical_byte_identity_status": HISTORICAL_STATUS,
                "source_recipe_only": True, "ekf_executed": False, "archived_filter_states_used": False,
                "historical_registry": HISTORICAL_REGISTRY.as_posix(), "source_files": sources,
                "producer_sha256": producers, "recipe": recipe, "runtime": runtime,
                "entries": entries, "recursive_tolerance_unchanged": 1e-10,
                "discrete_mask_time_pose_mismatches_allowed": 0}
    _put_new(output / "REGISTRY.json", registry)
    return registry


def _read_control_entry(repo: Path, entry: dict, packet: dict) -> dict:
    path = _inside(repo, entry["file"])
    values = read_npz(path, entry["sha256"])
    if path.stat().st_size != entry["size"]:
        raise ValueError("A2_CONTROL_PAYLOAD_SIZE")
    _validate_control_arrays(values, entry["n"])
    if _array_records(values) != entry["arrays"]:
        raise ValueError("A2_CONTROL_ARRAY_IDENTITY")
    if not all(np.array_equal(values[key], packet[key]) for key in ("t", "pose_id")):
        raise ValueError("A2_CONTROL_PACKET_JOIN")
    if (entry["time_min_s"], entry["time_max_s"], entry["max_delta_t_s"]) != (float(values["t"][0]), float(values["t"][-1]), float(values["dt"].max())):
        raise ValueError("A2_CONTROL_TIME_METADATA")
    return values


def load_rematerialized_controls(repo: Path, route: str, bias: str, packet: dict, registry_path: Path) -> tuple[dict, dict]:
    """Load hash-bound A2 inputs; the run owner separately locks registry SHA."""
    repo = Path(repo).resolve()
    if route not in ROUTE_ROWS or bias not in ("B0", "L2"):
        raise ValueError("A2_SCOPE_R4_R5_B0_L2_SEED10_ONLY")
    registry_path = Path(registry_path)
    if not registry_path.is_absolute():
        registry_path = repo / registry_path
    payload(registry_path)
    registry = json.loads(registry_path.read_bytes())
    keys = {f"{r}_aB_m0_{b}_{SEED}" for r in ROUTE_ROWS for b in ("B0", "L2")}
    if registry["schema"] != SCHEMA or registry["identity"] != IDENTITY or set(registry["entries"]) != keys:
        raise ValueError("A2_REGISTRY_SCHEMA_OR_SCOPE")
    if registry["historical_byte_identity_status"] != HISTORICAL_STATUS or registry["source_recipe_only"] is not True or registry["ekf_executed"] is not False or registry["archived_filter_states_used"] is not False:
        raise ValueError("A2_REGISTRY_IDENTITY_CLAIM")
    if registry["recursive_tolerance_unchanged"] != 1e-10 or registry["discrete_mask_time_pose_mismatches_allowed"] != 0:
        raise ValueError("A2_REGISTRY_TOLERANCE_CHANGED")
    if registry["source_files"] != _source_records(repo):
        raise ValueError("A2_SOURCE_RECORDS_CHANGED")
    for relative, expected in registry["producer_sha256"].items():
        payload(_inside(repo, relative), expected)
    key = f"{route}_aB_m0_{bias}_{SEED}"
    entry = registry["entries"][key]
    if (entry["route"], entry["bias"], entry["seed"], entry["n"], entry["identity"]) != (route, bias, SEED, ROUTE_ROWS[route], IDENTITY):
        raise ValueError("A2_ENTRY_SCOPE_OR_IDENTITY")
    values = _read_control_entry(repo, entry, packet)
    if array_sha256(values["ds"]) != KNOWN_REMATERIALIZED_DS[route]:
        raise ValueError("A2_PREREGISTERED_PRIMARY_DS_HASH_MISMATCH")
    expected = json.loads((repo / HISTORICAL_REGISTRY).read_bytes())["controls"][key]
    historical_identity = _historical_identity(values, expected)
    if historical_identity != entry["historical_identity"]:
        raise ValueError("A2_HISTORICAL_IDENTITY_METADATA")
    if _array_records({name: values[name] for name in ("t", "pose_id")}) != {name: entry["truth"]["arrays"][name] for name in ("t", "pose_id")}:
        raise ValueError("A2_TRUTH_GRID_BINDING")
    provenance = {"kind": IDENTITY, "registry": str(registry_path.relative_to(repo)),
                  "registry_sha256": sha256(registry_path), "registry_key": key,
                  "file": entry["file"], "sha256": entry["sha256"], "array_identity": entry["arrays"],
                  "historical_identity": historical_identity,
                  "GT_use": "offline pinned original control materializer only; no truth loaded by this input helper"}
    return {name: values[name] for name in ("ds", "gy", "dt", "x0")}, provenance
