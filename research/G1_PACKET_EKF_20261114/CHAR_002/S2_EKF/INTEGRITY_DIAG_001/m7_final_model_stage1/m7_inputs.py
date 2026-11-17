"""Frozen offline M7 sensor inputs; importing this module creates no evidence.

generate_inputs requires a hash-pinned source, input_generation GO, and explicit
paired gyro ARW coefficients. Candidate NPZs contain only KEYS. Synthetic truth
and sensor latents are confined to generation/checking and offline_latents/.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import types

import numpy as np

KEYS = ("t", "pose_id", "P0", "z", "muMB", "muBASE", "R", "D", "ds", "gy", "dt", "x0")
ROUTES = ("R2", "R4", "R5")
CONDITIONS = ("B0", "L2_GYRO_ARW")
INPUT_ALIASES = {"L2_GYRO_ARW_Q_B0_STRESS": "L2_GYRO_ARW"}
EXPECTED_COUNT = len(CONDITIONS) * 20 * len(ROUTES)
PASSES = {"R2": 2, "R4": 1, "R5": 3}
FIXED = ("t", "pose_id", "P0", "z", "muMB", "muBASE", "R", "D", "ds", "dt", "x0")
TOL = 1e-10


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def checked(record):
    path = Path(record["path"]).resolve()
    if sha(path) != record["sha256"]:
        raise ValueError(f"Hash mismatch: {path}")
    return path


def arrays(path):
    with np.load(path, allow_pickle=False) as data:
        return {key: data[key].copy() for key in data.files}


def write_new(path, payload):
    with Path(path).open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")


def _records(node):
    if isinstance(node, dict):
        if {"path", "sha256"} <= node.keys():
            checked(node)
        else:
            for value in node.values():
                _records(value)
    elif isinstance(node, list):
        for value in node:
            _records(value)


def _sensor(assets):
    """Load the two pinned modules in isolation from other qclean_uwb imports."""
    prefix = "_m7_frozen_sensor"
    package = types.ModuleType(prefix)
    package.__path__ = []
    sys.modules[prefix] = package
    for name in ("sensors", "sensor_v2"):
        record = assets[f"src/qclean_uwb/drivesim/{name}.py"]
        path = checked(record)
        spec = importlib.util.spec_from_file_location(f"{prefix}.{name}", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    return module


def paired_configs(sensor, noise):
    """Keep the frozen B0 configuration; replace only gyro N in its L2 pair."""
    b0 = sensor.SensorV2Config(level=1, condition="noise_pair", common_scale=0.,
                              bias_rw_rad_s_sqrt_s=0.)
    n0, n2 = noise["b0_N_deg_sqrt_s"], noise["l2_N_deg_sqrt_s"]
    if not all(isinstance(n, (int, float)) and not isinstance(n, bool) and math.isfinite(n)
               for n in (n0, n2)):
        raise ValueError("Gyro ARW coefficients must be finite numeric values")
    if n0 != .015 or n2 != .060:
        raise ValueError("Frozen M7 gyro ARW coefficients are .015 and .060 deg/sqrt(s)")
    if not math.isclose(math.radians(n0), b0.gyro_N_rad_sqrt_s, rel_tol=0., abs_tol=1e-15):
        raise ValueError("B0 ARW must retain the pinned source default for seed10 parity")
    # Level .05/.20 coefficients are disabled gyro bias, not white noise.
    l2 = replace(b0, gyro_N_rad_sqrt_s=math.radians(n2))
    if {key for key in asdict(b0) if asdict(b0)[key] != asdict(l2)[key]} != {"gyro_N_rad_sqrt_s"}:
        raise ValueError("Only gyro_N may differ between the paired sensor configurations")
    return b0, l2


def resolve_input(index, condition, seed, route):
    """Stress reuses the exact L2 path/hash; it never creates a third input set."""
    if condition not in (*CONDITIONS, *INPUT_ALIASES):
        raise ValueError(f"Unknown replay condition: {condition}")
    if type(seed) is not int or seed not in range(10, 30) or route not in ROUTES:
        raise ValueError("Input request is outside the frozen seed/route grid")
    return index[INPUT_ALIASES.get(condition, condition)][str(seed)][route]


def _configuration(contract):
    if (contract["seeds"] != list(range(10, 30))
            or any(type(seed) is not int for seed in contract["seeds"])
            or contract["conditions"] != list(CONDITIONS)):
        raise ValueError("M7 requires seeds 10-29 and B0/L2_GYRO_ARW in frozen order")
    if contract.get("input_aliases", INPUT_ALIASES) != INPUT_ALIASES:
        raise ValueError("Stress must alias the existing L2 inputs")
    if contract.get("authorization", {}).get("input_generation") != "GO":
        raise ValueError("Frozen contract does not authorize input_generation GO")
    sources = contract["sources"]
    own = [record for record in sources if Path(record["path"]).resolve() == Path(__file__).resolve()]
    if len(own) != 1:
        raise ValueError("Root contract must pin this exact m7_inputs.py once")
    _records(sources)
    _records(contract["model_assets"])
    _records(contract["governance"])
    policy_names = {Path(record["path"]).name for record in contract["governance"]}
    if not {"COMMON_CONTRACT.md", "ROLE_IMPLEMENTER.md"} <= policy_names:
        raise ValueError("Missing frozen COMMON_CONTRACT/ROLE_IMPLEMENTER")
    scope = contract.get("scope", {})
    for key, expected in (("anchor", "B"), ("mount_deg", 0.), ("rf", "Full"), ("bias", "B0")):
        if key in scope and scope[key] != expected:
            raise ValueError(f"Unexpected {key} scope")
    if "routes" in scope and scope["routes"] != list(ROUTES):
        raise ValueError("Unexpected route scope")
    cells = {cell["route"]: cell for cell in contract["cells"]}
    if len(contract["cells"]) != 3 or set(cells) != set(ROUTES):
        raise ValueError("Exactly one frozen M6 cell per R2/R4/R5 is required")
    archive = contract.get("m5_online_packets", contract.get("online_packets"))
    if archive is None or any(str(seed) not in archive for seed in range(11, 15)):
        raise ValueError("Frozen M5 online_packets for seeds 11-14 are required")
    evaluators = contract["evaluator_inputs"]
    for route in ROUTES:
        checked(cells[route]["online"])
        path = checked(evaluators[route])
        if path.name != f"{route}_evaluator.npz" or path.parent.name != "inputs":
            raise ValueError("Use separate published gm_theta_m6/inputs evaluator files")
        if evaluators[route]["sha256"] != cells[route]["evaluator"]["sha256"]:
            raise ValueError("Published truth differs from frozen M6 evaluator")
        for seed in range(11, 15):
            checked(archive[str(seed)][route])
    sensor = _sensor(contract["model_assets"])
    b0, l2 = paired_configs(sensor, contract["paired_gyro_noise"])
    return cells, evaluators, archive, sensor, b0, l2


def _close(actual, expected):
    np.testing.assert_allclose(actual, expected, atol=TOL, rtol=0.)
    return float(np.max(np.abs(np.asarray(actual) - np.asarray(expected)), initial=0.))


def _packet(packet):
    if set(packet) != set(KEYS):
        raise ValueError("Candidate contains missing/extra keys, potentially evaluator fields")
    for key in KEYS:
        if packet[key].dtype.kind not in "biuf" or not np.isfinite(packet[key]).all():
            raise ValueError(f"Non-numeric/nonfinite candidate field: {key}")
    n = len(packet["t"])
    if packet["x0"].shape != (4,) or packet["P0"].shape != (4, 4):
        raise ValueError("Invalid initial state/covariance shape")
    if any(packet[key].shape[0] != n for key in KEYS if key not in ("P0", "x0")):
        raise ValueError("Packet fields have inconsistent length")


def _pass_count(truth, t):
    offset = truth[:, 0] - 10.
    times = []
    for i in np.flatnonzero(offset[:-1] * offset[1:] <= 0.):
        if offset[i] == offset[i + 1]:
            raise ValueError("Ambiguous passage at x=10 m")
        time = float(t[i] - offset[i] * (t[i + 1] - t[i]) / (offset[i + 1] - offset[i]))
        if not times or times[-1] != time:
            times.append(time)
    return len(times)


def _route_inputs(cell, evaluator):
    reference = arrays(checked(cell["online"]))
    # Whitelist copies ensure no evaluator metadata can enter candidate packets.
    reference = {key: reference[key] for key in KEYS}
    _packet(reference)
    evaluation = arrays(checked(evaluator))
    for key in ("t", "pose_id"):
        np.testing.assert_array_equal(reference[key], evaluation[key])
    truth = evaluation["truth"]
    if truth.shape != (len(reference["t"]), 3) or not np.isfinite(truth).all():
        raise ValueError("Malformed synthetic truth")
    if _pass_count(truth, reference["t"]) != PASSES[cell["route"]]:
        raise ValueError("Frozen route passage count differs")
    return reference, truth


def _initial(sensor, truth, seed):
    x0 = truth[0] + sensor.rng(seed, "initial").standard_normal(3) * [.1, .1, math.radians(5.)]
    x0[2] = (x0[2] + math.pi) % (2 * math.pi) - math.pi
    return np.r_[x0, 0.], np.diag([.1**2, .1**2, math.radians(5.)**2, math.radians(.1)**2])


def _check_pair(b0, l2, reference, truth, latent, seed, route, archive, sensor, cfg):
    _packet(b0)
    _packet(l2)
    errors = {}
    for key in FIXED:
        np.testing.assert_array_equal(b0[key], l2[key])
    for key in ("t", "pose_id", "z", "muMB", "muBASE", "R", "D"):
        np.testing.assert_array_equal(b0[key], reference[key])
    x0, p0 = _initial(sensor, truth, seed)
    np.testing.assert_array_equal(b0["x0"], x0)
    np.testing.assert_array_equal(b0["P0"], p0)
    if seed == 10:
        for key in KEYS:
            errors[f"seed10_{key}"] = _close(b0[key], reference[key])
    elif seed <= 14:
        old = arrays(checked(archive[str(seed)][route]))
        for key in ("ds", "gy", "dt"):
            errors[f"M5_{key}"] = _close(b0[key], old[key])
    dt = np.r_[0., np.diff(b0["t"])]
    np.testing.assert_array_equal(b0["dt"], dt)
    # Independent arithmetic oracle for the pinned gyro RNG and white-noise law.
    draw = sensor.rng(seed, "gyro").standard_normal(len(dt))
    white = draw * cfg.gyro_N_rad_sqrt_s * np.sqrt(dt)
    white[0] = 0.
    clean = np.r_[0., (np.diff(truth[:, 2]) + np.pi) % (2 * np.pi) - np.pi]
    errors["B0_white_oracle"] = _close(b0["gy"] - clean, white)
    errors["L2_white_oracle"] = _close(l2["gy"] - clean, 4 * white)
    errors["paired_white_4x"] = _close(l2["gy"] - clean, 4 * (b0["gy"] - clean))
    for key in ("B0_true_bias_rad_s", "L2_true_bias_rad_s"):
        np.testing.assert_array_equal(latent[key], np.zeros_like(dt))
    for key, expected in (("t", b0["t"]), ("gyro_clean", clean),
                          ("B0_white", b0["gy"] - clean), ("L2_white", l2["gy"] - clean)):
        _close(latent[key], expected)
    return dict(status="PASS", max_abs_errors=errors, passage_count=PASSES[route],
                initial_seed=seed, initial_stream="initial", true_bias_exact_zero=True,
                paired_controls_rf_initial_exact_equal=True, candidate_keys=list(KEYS))


def check_inputs(contract_path, output_dir):
    """Readback self-check; uses only frozen input references and separate truth."""
    contract = read(contract_path)
    cells, evaluators, archive, sensor, cfg, _ = _configuration(contract)
    root = Path(output_dir).resolve()
    index = read(root / "INPUT_INDEX.json")
    if read(root / "INPUT_ALIASES.json") != INPUT_ALIASES:
        raise ValueError("Stress alias metadata differs from the frozen L2 reuse rule")
    if set(index) != set(CONDITIONS):
        raise ValueError("Unexpected indexed conditions")
    result = {}
    for condition in CONDITIONS:
        if set(index[condition]) != {str(s) for s in contract["seeds"]}:
            raise ValueError("Missing/extra indexed seeds")
        if any(set(routes) != set(ROUTES) for routes in index[condition].values()):
            raise ValueError("Missing/extra indexed routes")
    for route in ROUTES:
        reference, truth = _route_inputs(cells[route], evaluators[route])
        initial_offsets = []
        for seed in contract["seeds"]:
            packets = []
            for condition in CONDITIONS:
                record = index[condition][str(seed)][route]
                expected = root / "inputs" / condition / f"seed{seed}" / f"{route}_online.npz"
                if Path(record["path"]).resolve() != expected:
                    raise ValueError("Indexed packet escaped its fixed output location")
                packets.append(arrays(checked(record)))
            if resolve_input(index, "L2_GYRO_ARW_Q_B0_STRESS", seed, route) is not index["L2_GYRO_ARW"][str(seed)][route]:
                raise ValueError("Stress must resolve to the original L2 path/hash record")
            latent = arrays(root / "offline_latents" / f"seed{seed}" / f"{route}_gyro.npz")
            result[f"{route}/seed{seed}"] = _check_pair(
                *packets, reference, truth, latent, seed, route, archive, sensor, cfg)
            initial_offsets.append(packets[0]["x0"] - np.r_[truth[0], 0.])
        if len({tuple(x) for x in initial_offsets}) != len(contract["seeds"]):
            raise ValueError("Repeated initial offsets across distinct seeds")
    return dict(status="PASS_SELF_CHECK", candidate_count=EXPECTED_COUNT, pairs=result,
                input_aliases=INPUT_ALIASES,
                scope="offline synthetic input invariants; no EKF or independent audit")


def generate_inputs(contract_path, output_dir):
    """Generate 120 paired packets after Mother freezes this source and GO."""
    contract_path = Path(contract_path).resolve()
    contract = read(contract_path)
    cells, evaluators, archive, sensor, cfg, cfg_l2 = _configuration(contract)
    root = Path(output_dir).resolve()
    for name in ("inputs", "offline_latents", "INPUT_INDEX.json", "INPUT_ALIASES.json", "INPUT_CHECKS.json",
                 "INPUT_GENERATION_RECEIPT.json"):
        if (root / name).exists():
            raise FileExistsError(f"Preserve existing evidence: {root / name}")
    root.mkdir(parents=True, exist_ok=True)
    receipt = dict(started_utc=datetime.now(timezone.utc).isoformat(),
                   command=[sys.executable, *sys.argv], python=sys.version, numpy=np.__version__,
                   contract=dict(path=str(contract_path), sha256=sha(contract_path)),
                   source=dict(path=str(Path(__file__).resolve()), sha256=sha(__file__)),
                   governance=contract["governance"], model_assets=contract["model_assets"],
                   sensor_config={"B0": cfg.manifest(), "L2_GYRO_ARW": cfg_l2.manifest()},
                   gyro_noise=dict(coefficient_unit="deg/sqrt(s)", increment_unit="rad",
                                   B0_N_deg_sqrt_s=.015, L2_N_deg_sqrt_s=.060,
                                   B0_N_rad_sqrt_s=cfg.gyro_N_rad_sqrt_s,
                                   L2_N_rad_sqrt_s=cfg_l2.gyro_N_rad_sqrt_s,
                                   paired_white_ratio=4, increment_variance_ratio=16),
                   input_aliases=INPUT_ALIASES, input_conditions=list(CONDITIONS),
                   grid=dict(seeds=contract["seeds"], routes=list(ROUTES), expected_count=EXPECTED_COUNT),
                   filter_Q="Not applied by input generator; stress reuses L2 input and changes replay Q only",
                   claim_scope="same frozen RF; independently seeded sensor/initial draws; synthetic only")
    index = {condition: {str(seed): {} for seed in contract["seeds"]} for condition in CONDITIONS}
    outputs = {}
    try:
        for route in ROUTES:
            reference, truth = _route_inputs(cells[route], evaluators[route])
            ds, angle = sensor.motion_increments(reference["t"], truth, convention="legacy-euler")
            for seed in contract["seeds"]:
                controls, latent0 = sensor.generate(reference["t"], ds, angle, cfg, seed)
                controls2, latent2 = sensor.generate(reference["t"], ds, angle, cfg_l2, seed)
                for key in controls:
                    if key != "dtheta_gyro":
                        np.testing.assert_array_equal(controls[key], controls2[key])
                x0, p0 = _initial(sensor, truth, seed)
                b0 = {key: reference[key].copy() for key in KEYS}
                b0.update(ds=controls["ds_odom"], gy=controls["dtheta_gyro"], dt=controls["dt_s"], x0=x0, P0=p0)
                l2 = {key: b0[key].copy() for key in KEYS}
                l2["gy"] = controls2["dtheta_gyro"]
                latent = dict(t=b0["t"], gyro_clean=angle, B0_white=b0["gy"] - angle,
                              L2_white=l2["gy"] - angle,
                              B0_true_bias_rad_s=latent0["true_bias_rad_s"],
                              L2_true_bias_rad_s=latent2["true_bias_rad_s"])
                _check_pair(b0, l2, reference, truth, latent, seed, route, archive, sensor, cfg)
                for condition, packet in zip(CONDITIONS, (b0, l2)):
                    path = root / "inputs" / condition / f"seed{seed}" / f"{route}_online.npz"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open("xb") as handle:
                        np.savez_compressed(handle, **packet)
                    record = dict(path=str(path), sha256=sha(path))
                    index[condition][str(seed)][route] = record
                    outputs[path.relative_to(root).as_posix()] = record["sha256"]
                path = root / "offline_latents" / f"seed{seed}" / f"{route}_gyro.npz"
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("xb") as handle:
                    np.savez_compressed(handle, **latent)
                outputs[path.relative_to(root).as_posix()] = sha(path)
        write_new(root / "INPUT_INDEX.json", index)
        write_new(root / "INPUT_ALIASES.json", INPUT_ALIASES)
        checks = check_inputs(contract_path, root)
        write_new(root / "INPUT_CHECKS.json", checks)
        for name in ("INPUT_INDEX.json", "INPUT_ALIASES.json", "INPUT_CHECKS.json"):
            outputs[name] = sha(root / name)
        receipt.update(status="PASS_EXECUTION", exit_code=0, candidate_count=EXPECTED_COUNT)
    except BaseException as exc:
        receipt.update(status="FAIL_EXECUTION", exit_code=1, error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        receipt.update(finished_utc=datetime.now(timezone.utc).isoformat(), outputs=outputs)
        write_new(root / "INPUT_GENERATION_RECEIPT.json", receipt)
    return index


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "check"))
    parser.add_argument("contract", type=Path)
    parser.add_argument("output_dir", type=Path)
    arguments = parser.parse_args()
    if arguments.command == "generate":
        generate_inputs(arguments.contract, arguments.output_dir)
    else:
        print(json.dumps(check_inputs(arguments.contract, arguments.output_dir), indent=2))
