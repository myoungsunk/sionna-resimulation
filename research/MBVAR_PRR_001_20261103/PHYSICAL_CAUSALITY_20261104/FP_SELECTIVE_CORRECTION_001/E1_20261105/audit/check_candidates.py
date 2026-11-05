"""Separately authored scalar reference for FP-SC-001 E1-01.

Reviewer role: SAME_SESSION_SEPARATE_REVIEWER, not an external audit.
This reference is derived from the preregistered candidate specification;
it does not import the production candidate generator or selector.
Importing this file reads no RF corpus and writes no scientific results.
"""
from __future__ import annotations

import argparse
import ast
import csv
import datetime as dt
import gzip
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from typing import Any

if __name__ == "__main__":
    for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[variable] = "1"

import numpy as np


ROLE = "SAME_SESSION_SEPARATE_REVIEWER_NOT_EXTERNAL"
N_TAPS = 1028
EPS = np.finfo(np.float64).eps
PRIMARY_PARAMETERS = {
    "eta_prominence": 0.06,
    "local_leading_edge_amplitude_fraction": 0.30,
    "neighbor_radius_taps": 1,
    "candidate_min_fraction_of_local_peak": 0.15,
    "minimum_noise_sigma": 3.0,
    "packet_union_bound_pfa": 0.001,
    "numeric_floor_epsilon_multiplier": 64,
    "max_candidates_for_usable_pool": 64,
    "per_bin_complex_noise_variance": 0.0,
}


def digest_file(path: Path) -> str:
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write_json_new(path: Path, value: Any) -> None:
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")


def assert_primary_parameters(config: dict) -> None:
    for key, expected in PRIMARY_PARAMETERS.items():
        if config[key] != expected:
            raise ValueError("CHECKER_SPEC_PARAMETER_CHANGED: " + key)


def amplitude_noise_floor(variance_h: float, taps: int = N_TAPS) -> float:
    if not math.isfinite(variance_h) or variance_h < 0.0:
        raise ValueError("CHECKER_NOISE_VARIANCE")
    variance_c = 6.0 * variance_h
    return max(3.0 * math.sqrt(variance_c),
               math.sqrt(variance_c * math.log(2.0 * taps / 0.001)))


def original_raw_fields(cir: np.ndarray) -> dict:
    """Scalar first crossing; nonfinite input is explicitly undefined."""
    values = np.asarray(cir, dtype=np.complex128)
    if values.ndim != 2 or values.shape[1] != 2 or len(values) < 3:
        raise ValueError("CHECKER_CIR_SHAPE")
    if not np.isfinite(values).all():
        return {"tap": None, "rx": None, "peak": None, "valid": False,
                "s": None, "denominator": None, "reason": "NONFINITE_CIR"}
    magnitudes = np.abs(values)
    peaks = [float(np.max(magnitudes[:, port])) for port in (0, 1)]
    # Source argmax selects the first NaN and the first exact finite tie.
    port = 0 if math.isnan(peaks[0]) else (1 if math.isnan(peaks[1]) or peaks[1] > peaks[0] else 0)
    peak = peaks[port]
    tap = 0
    for index in range(len(values)):
        if magnitudes[index, port] >= 0.30 * peak:
            tap = index
            break
    with np.errstate(invalid="ignore", over="ignore", divide="ignore"):
        power = np.abs(values[tap]) ** 2
        denominator = float(power[0] + power[1])
        ratio = float((power[0] - power[1]) / denominator) if denominator > 0 else math.nan
    finite = bool(np.isfinite(values).all() and np.isfinite(magnitudes).all())
    numeric = 64.0 * EPS * peak if math.isfinite(peak) and peak > 0 else 0.0
    valid = bool(finite and peak > numeric and denominator > 0 and math.isfinite(denominator) and math.isfinite(ratio))
    return {"tap": tap, "rx": port, "peak": peak, "valid": valid, "s": ratio,
            "denominator": denominator, "magnitudes": magnitudes,
            "reason": "VALID" if valid else "NO_SIGNAL_OR_INVALID_DENOMINATOR"}


def scalar_lobes(amplitude: list[float], port: int, global_peak: float,
                 noise_floor: float) -> list[dict]:
    """Enumerate maximal plateaus, then independently scan basins and edges."""
    n = len(amplitude)
    lobes = []
    start = 0
    while start < n:
        end = start
        height = amplitude[start]
        while end + 1 < n and amplitude[end + 1] == height:
            end += 1
        left_lower = start == 0 or amplitude[start - 1] < height
        right_lower = end == n - 1 or amplitude[end + 1] < height
        strict_neighbor = (start > 0 and amplitude[start - 1] < height) or (end + 1 < n and amplitude[end + 1] < height)
        if left_lower and right_lower and strict_neighbor:
            boundary = start == 0 or end == n - 1
            record = {"port": port, "peak_index": start, "plateau_end": end,
                      "peak_amplitude": height, "boundary": boundary,
                      "significant": False, "resolved": False, "edge_tap": None,
                      "generated_taps": [], "candidate_amplitude_floor": None, "reason": None}
            left_limit = start
            while left_limit > 0 and amplitude[left_limit - 1] <= height:
                left_limit -= 1
            right_limit = end
            while right_limit + 1 < n and amplitude[right_limit + 1] <= height:
                right_limit += 1
            # Strict updates while scanning away retain the nearest tied minimum.
            left_min = start
            for index in range(start - 1, left_limit - 1, -1):
                if amplitude[index] < amplitude[left_min]:
                    left_min = index
            right_min = end
            for index in range(end + 1, right_limit + 1):
                if amplitude[index] < amplitude[right_min]:
                    right_min = index
            prominence = 0.0 if boundary else height - max(amplitude[left_min], amplitude[right_min])
            left_local = start
            while left_local > 0 and amplitude[left_local - 1] <= amplitude[left_local]:
                left_local -= 1
            right_local = end
            while right_local + 1 < n and amplitude[right_local + 1] <= amplitude[right_local]:
                right_local += 1
            numeric = 64.0 * EPS * global_peak
            significant = not boundary and height >= max(noise_floor, numeric) and prominence >= max(noise_floor, 0.06 * global_peak)
            resolved = significant and amplitude[left_local] < 0.30 * height
            record.update(prominence=prominence, left_prominence_minimum=left_min,
                          right_prominence_minimum=right_min, left_local_valley=left_local,
                          right_local_valley=right_local, significant=bool(significant), resolved=bool(resolved))
            if boundary:
                record["reason"] = "BOUNDARY_PEAK_NOT_CANDIDATE"
            elif height < max(noise_floor, numeric):
                record["reason"] = "BELOW_ABSOLUTE_SUPPORT"
            elif prominence < max(noise_floor, 0.06 * global_peak):
                record["reason"] = "BELOW_PROMINENCE"
            elif not resolved:
                record["reason"] = "UNRESOLVED_LOCAL_LEADING_EDGE"
            else:
                edge = next(index for index in range(left_local, start + 1) if amplitude[index] >= 0.30 * height)
                threshold = max(noise_floor, numeric, 0.15 * height)
                taps = [index for index in range(edge - 1, edge + 2)
                        if left_local <= index <= start and amplitude[index] >= threshold]
                record.update(edge_tap=edge, generated_taps=taps, candidate_amplitude_floor=threshold,
                              reason="SUPPORTED_LOBE" if taps else "NO_SUPPORTED_EDGE_TAP")
            lobes.append(record)
        start = end + 1
    return lobes


def scalar_candidate_pools(cir: np.ndarray, *, noise_variance_h: float = 0.0) -> dict:
    """Independent candidate taps/support. No labels, IDs, priors or history."""
    raw = original_raw_fields(cir)
    noise = amplitude_noise_floor(noise_variance_h, len(cir))
    modes = ("STRONGEST_ONLY", "TWO_PORT_UNION")
    if not raw["valid"]:
        return {"raw": raw, "noise_floor": noise, "lobes": [],
                "pools": {mode: {"taps": [], "supported_taps": [], "support": {}, "overflow": False, "groups": []} for mode in modes}}
    lobes = []
    for port in (0, 1):
        lobes.extend(scalar_lobes(raw["magnitudes"][:, port].tolist(), port, raw["peak"], noise))
    pools = {}
    for mode in modes:
        support: dict[int, list[tuple[int, int]]] = {}
        for lobe in lobes:
            if mode == "STRONGEST_ONLY" and lobe["port"] != raw["rx"]:
                continue
            for tap in lobe["generated_taps"]:
                support.setdefault(tap, []).append((lobe["port"], lobe["peak_index"]))
        supported = sorted(support)
        taps = sorted(set(supported) | {raw["tap"]})
        eligible = [lobe for lobe in lobes if lobe["generated_taps"] and (mode == "TWO_PORT_UNION" or lobe["port"] == raw["rx"])]
        pools[mode] = {"taps": taps, "supported_taps": supported,
                       "support": {tap: sorted(sources) for tap, sources in support.items()},
                       "overflow": len(taps) > 64, "groups": basin_components(eligible)}
    if not set(pools[modes[0]]["taps"]).issubset(pools[modes[1]]["taps"]):
        raise AssertionError("CHECKER_STRONGEST_NOT_SUBSET")
    return {"raw": raw, "noise_floor": noise, "lobes": lobes, "pools": pools}


def basin_components(lobes: list[dict]) -> list[list[str]]:
    """Exact connected components, including transitive cross-port overlap."""
    adjacency = {index: set() for index in range(len(lobes))}
    for left, a in enumerate(lobes):
        for right, b in enumerate(lobes[:left]):
            if min(a["right_local_valley"], b["right_local_valley"]) > max(a["left_local_valley"], b["left_local_valley"]):
                adjacency[left].add(right)
                adjacency[right].add(left)
    remaining = set(adjacency)
    components = []
    while remaining:
        todo = [min(remaining)]
        component = set()
        while todo:
            vertex = todo.pop()
            if vertex in component:
                continue
            component.add(vertex)
            todo.extend(adjacency[vertex] - component)
        remaining -= component
        components.append(component)
    def key(component):
        return min((lobes[i]["left_local_valley"], lobes[i]["right_local_valley"], lobes[i]["port"], lobes[i]["peak_index"]) for i in component)
    components.sort(key=key)
    return [sorted(f"rx{lobes[i]['port']}_peak{lobes[i]['peak_index']}" for i in component) for component in components]


def classify_availability(current: dict, reference: dict, mode: str) -> dict:
    raw = current["raw"]
    valid = bool(reference["valid"])
    pool = current["pools"][mode]
    pair_valid = valid and raw["valid"]
    delta = abs(raw["tap"] - reference["tap"]) if pair_valid else None
    supported = valid and reference["tap"] in pool["supported_taps"]
    return {"raw_tap": raw["tap"], "raw_rx": raw["rx"], "raw_valid": raw["valid"],
            "reference_tap": reference["tap"], "reference_valid": valid,
            "normal": pair_valid and delta == 0, "wrong": pair_valid and delta > 0,
            "large_error": pair_valid and delta >= 2, "one_tap_error": pair_valid and delta == 1,
            "unknown_reference": not valid, "original_invalid": valid and not raw["valid"],
            "candidate_count": len(pool["taps"]), "supported_count": len(pool["supported_taps"]),
            "overflow": pool["overflow"], "reference_in_all": valid and reference["tap"] in pool["taps"],
            "reference_in_supported": supported,
            "reference_usable": supported and not pool["overflow"] and raw["valid"],
            "raw_preserved": raw["tap"] in pool["taps"] if raw["valid"] else not pool["taps"]}


def error_episodes(rows: list[dict]) -> list[dict]:
    """Evaluate runs after candidate generation; labels never enter generator."""
    result = []
    active = []
    def finish():
        if not active:
            return
        recalled = [bool(row["reference_usable"]) for row in active]
        longest = run = 0
        for event in recalled:
            run = 0 if event else run + 1
            longest = max(longest, run)
        result.append({"first_pose_id": active[0]["pose_id"], "last_pose_id": active[-1]["pose_id"],
                       "start_s": active[0]["t_s"], "end_s": active[-1]["t_s"],
                       "n_packets": len(active), "n_recalled": sum(recalled),
                       "recall": sum(recalled) / len(recalled), "all_recalled": all(recalled),
                       "any_recalled": any(recalled), "longest_missing_run": longest})
        active.clear()
    for row in rows:
        if not row["large_error"]:
            finish()
            continue
        if active and (row["pose_id"] != active[-1]["pose_id"] + 1 or row["t_s"] - active[-1]["t_s"] > 0.4):
            finish()
        active.append(row)
    finish()
    return result


def review_causality(candidate_path: Path, observation_path: Path) -> dict:
    """Read-only AST dependency review, explicitly distinct from RF testing.

    Candidate numerical results are never obtained by importing this source.
    This checks the complete small generator module and the separately pinned
    original first_path_batch dependency. It is not an external formal proof.
    """
    tree = ast.parse(Path(candidate_path).read_text(encoding="utf-8"))
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    findings = []
    expected_interfaces = {"generate_pools": {"cir", "config"}, "generate_candidates": {"cir", "mode", "config"}}
    for name, expected in expected_interfaces.items():
        if name not in functions:
            findings.append("MISSING_ENTRY_POINT: " + name)
            continue
        args = functions[name].args
        actual = {arg.arg for arg in args.posonlyargs + args.args + args.kwonlyargs}
        if actual != expected or args.vararg is not None or args.kwarg is not None:
            findings.append("UNEXPECTED_ENTRY_ARGUMENTS: " + name)
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    config = classes.get("CandidateConfig")
    frozen = config is not None and any(isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name)
        and decorator.func.id == "dataclass" and any(k.arg == "frozen" and isinstance(k.value, ast.Constant) and k.value.value is True for k in decorator.keywords)
        for decorator in config.decorator_list)
    if not frozen:
        findings.append("CONFIG_NOT_FROZEN_DATACLASS")
    denied_names = {"truth", "reference", "prior", "posterior", "route", "seed", "history", "future", "gt"}
    denied_calls = {"open", "eval", "exec", "compile", "__import__", "globals", "locals", "getattr", "setattr", "input"}
    denied_attributes = {"load", "save", "savez", "savez_compressed", "read_text", "read_bytes", "write_text", "write_bytes", "random", "default_rng", "standard_normal"}
    call_names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            findings.append("STATEFUL_GLOBAL_OR_NONLOCAL")
        if isinstance(node, ast.Name) and node.id.lower() in denied_names:
            findings.append("DISALLOWED_GENERATOR_NAME: " + node.id)
        if isinstance(node, ast.Call):
            text = ast.unparse(node.func)
            call_names.add(text)
            if isinstance(node.func, ast.Name) and node.func.id in denied_calls:
                findings.append("DYNAMIC_OR_IO_CALL: " + text)
            if isinstance(node.func, ast.Attribute) and node.func.attr in denied_attributes:
                findings.append("IO_OR_RANDOM_CALL: " + text)
        if isinstance(node, ast.Import):
            if any(alias.name.split(".")[0] not in {"hashlib", "json", "math", "numpy"} for alias in node.names):
                findings.append("UNREVIEWED_IMPORT: " + ast.unparse(node))
        if isinstance(node, ast.ImportFrom):
            if node.module not in {"__future__", "dataclasses", "typing", "qclean_uwb.drivesim"}:
                findings.append("UNREVIEWED_IMPORT: " + ast.unparse(node))
    source = ast.parse(Path(observation_path).read_text(encoding="utf-8"))
    first_path = [node for node in source.body if isinstance(node, ast.FunctionDef) and node.name == "first_path_batch"]
    if len(first_path) != 1:
        findings.append("ORIGINAL_DETECTOR_DEPENDENCY_MISSING")
    else:
        for node in ast.walk(first_path[0]):
            if isinstance(node, (ast.Global, ast.Nonlocal)):
                findings.append("ORIGINAL_DETECTOR_STATEFUL")
            if isinstance(node, ast.Name) and node.id.lower() in denied_names:
                findings.append("ORIGINAL_DETECTOR_DISALLOWED_NAME: " + node.id)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in denied_attributes:
                findings.append("ORIGINAL_DETECTOR_IO_OR_RANDOM")
    return {"role": ROLE, "method": "source-only AST/API/dependency review; production candidate function was not imported",
            "candidate_source_sha256": digest_file(candidate_path), "original_detector_source_sha256": digest_file(observation_path),
            "checked_functions": sorted(functions), "checked_entry_interfaces": {key: sorted(value) for key, value in expected_interfaces.items()},
            "immutable_config": frozen, "module_call_targets": sorted(call_names),
            "local_label_name_review": "_groups.labels is a locally constructed component-number map, not evaluator labels",
            "passed": not findings, "findings": sorted(set(findings)),
            "scope": "CIR-only single-packet API, immutable config, no label/prior/route/history parameter, no explicit stateful/IO/random dependency",
            "limits": "Static review plus separately tested scalar semantics; no external audit, no formal proof, and no real-corpus parity executed by this function"}


def independent_cir(spectrum: np.ndarray) -> np.ndarray:
    values = np.asarray(spectrum, dtype=np.complex128)
    if values.shape != (257, 2) or not np.isfinite(values).all():
        raise ValueError("CHECKER_SPECTRUM_SCHEMA")
    window = np.array([0.5 * (1.0 - math.cos(2.0 * math.pi * index / 256.0)) for index in range(257)])
    result = np.empty((1028, 2), dtype=np.complex128)
    for port in (0, 1):
        padded = np.zeros(1028, dtype=np.complex128)
        padded[:257] = values[:, port] * window
        result[:, port] = np.fft.ifft(padded) * 257.0
    return result


def locked_corpus(repo: Path):
    """Read all declared spectra; evaluator labels are not generator inputs."""
    physical = repo / "research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104"
    rf = repo / "results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C"
    frequencies = np.load(rf / "freqs_hz.npy", allow_pickle=False)
    if not np.array_equal(frequencies, 6_250_400_000.0 + np.arange(257) * 1_950_000.0):
        raise ValueError("CHECKER_FREQUENCY_GRID")
    for route, n in (("R2", 979), ("R4", 742), ("R5", 1415)):
        p = physical / f"C1/C1A_001/FROZEN_PACKETS/algorithm_input/{route}_aB_m0_B0_Full.npz"
        with np.load(p, allow_pickle=False) as archive:
            ids, times = archive["pose_id"], archive["t"]
        if ids.shape != (n,) or times.shape != (n,) or ids.dtype != np.dtype("int64") or not np.all(np.diff(ids) > 0) or not np.all(np.diff(times) > 0):
            raise ValueError("CHECKER_LOCKED_POSE_TIME_SCHEMA")
        full = np.load(rf / f"FULL_RF/H_{route}_aB_m0.npy", mmap_mode="r", allow_pickle=False)
        native = np.load(rf / f"H_LoS_{route}_aB_m0.npy", mmap_mode="r", allow_pickle=False)
        for pose, timestamp in zip(ids, times):
            pair = {"Full": independent_cir(full[int(pose), :, :, 0]),
                    "Native_LoS": independent_cir(native[int(pose), :, :, 0])}
            for channel in ("Full", "Native_LoS"):
                meta = {"packet_uid": f"dynamic:{route}:{int(pose)}:{channel}", "corpus": "dynamic", "route": route,
                        "coordinate": None, "condition_id": None, "yaw_deg": None, "pose_id": int(pose),
                        "t_s": float(timestamp), "channel": channel}
                yield meta, pair[channel], pair["Native_LoS"]
    g4 = physical / "C3/G4_001/RUN_001"
    conditions = json.loads((g4 / "CONDITIONS.json").read_bytes())
    if len(conditions) != 24 or len({record["condition_id"] for record in conditions}) != 24 or len({record["coordinate"] for record in conditions}) != 6:
        raise ValueError("CHECKER_G4_SCOPE")
    for record in conditions:
        cid = record["condition_id"]
        if Path(cid).name != cid:
            raise ValueError("CHECKER_UNSAFE_G4_ID")
        with np.load(g4 / cid / "FIELDS_AND_WINDOWS.npz", allow_pickle=False) as archive:
            pair = {"Full": independent_cir(archive["full_spectrum"]),
                    "Native_LoS": independent_cir(archive["direct_spectrum"])}
        for channel in ("Full", "Native_LoS"):
            meta = {"packet_uid": f"static_g4:{cid}:{channel}", "corpus": "static_g4", "route": None,
                    "coordinate": record["coordinate"], "condition_id": cid, "yaw_deg": float(record["yaw_deg"]),
                    "pose_id": None, "t_s": None, "channel": channel}
            yield meta, pair[channel], pair["Native_LoS"]


def csv_rows(path: Path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", newline="") as handle:
        yield from csv.DictReader(handle)


def csv_value(text: str, expected: Any):
    if expected is None or isinstance(expected, float) and not math.isfinite(expected):
        return None if text in ("", "None", "null", "nan") else text
    if isinstance(expected, (bool, np.bool_)):
        if text not in ("True", "False", "1", "0"):
            raise ValueError("CHECKER_INVALID_BOOLEAN: " + text)
        return text in ("True", "1")
    if isinstance(expected, (int, np.integer)):
        return int(text)
    if isinstance(expected, (float, np.floating)):
        return float(text)
    return text


class Comparisons:
    def __init__(self):
        self.checked = 0
        self.mismatches = 0
        self.examples = []

    def equal(self, context, actual, expected, *, numerical=False):
        self.checked += 1
        if numerical and actual is not None and expected is not None:
            try:
                okay = math.isfinite(float(actual)) and math.isfinite(float(expected)) and abs(float(actual) - float(expected)) <= 1e-12 * max(1.0, abs(float(expected)))
            except (TypeError, ValueError):
                okay = False
        else:
            okay = actual == expected
        if not okay:
            self.mismatches += 1
            if len(self.examples) < 100:
                self.examples.append({"context": context, "actual": actual, "expected": expected})

    def fields(self, context, actual, expected):
        for key, wanted in expected.items():
            value = actual.get(key, "__MISSING__")
            if isinstance(value, str) and not isinstance(wanted, str):
                try:
                    value = csv_value(value, wanted)
                except (ValueError, TypeError):
                    pass
            if isinstance(wanted, float) and not math.isfinite(wanted):
                wanted = None
            self.equal(context + ":" + key, value, wanted, numerical=isinstance(wanted, float))

    def record(self):
        return {"comparisons": self.checked, "mismatches": self.mismatches, "examples_first_100": self.examples,
                "floating_evidence_tolerance": "abs(a-b)<=1e-12*max(1,abs(reference)); all decisions/IDs/counts exact",
                "passed": self.mismatches == 0}


def build_log_index(connection: sqlite3.Connection, run: Path) -> dict:
    connection.execute("CREATE TABLE candidate (uid TEXT, mode TEXT, tap INTEGER, item TEXT, PRIMARY KEY(uid,mode,tap))")
    connection.execute("CREATE TABLE lobe (uid TEXT, lid TEXT, item TEXT, PRIMARY KEY(uid,lid))")
    counts = {}
    for label, filename, statement, unpack in (
        ("candidate", "CANDIDATES.csv.gz", "INSERT INTO candidate VALUES (?,?,?,?)",
         lambda r: (r["packet_uid"], r["mode"], int(r["tap"]), json.dumps(r, separators=(",", ":")))),
        ("lobe", "LOBE_RECORDS.csv.gz", "INSERT INTO lobe VALUES (?,?,?)",
         lambda r: (r["packet_uid"], r["lobe_id"], json.dumps(r, separators=(",", ":"))))):
        number = 0
        for row in csv_rows(run / filename):
            connection.execute(statement, unpack(row))
            number += 1
        connection.commit()
        counts[label] = number
        print("AUDIT_LOG_INDEX", label, number, flush=True)
    return counts


def compare_lobes(checks: Comparisons, uid: str, computed: dict, logged: list[dict]) -> int:
    by_id = {row["lobe_id"]: row for row in logged}
    expected_ids = {f"rx{lobe['port']}_peak{lobe['peak_index']}" for lobe in computed["lobes"]}
    checks.equal(uid + ":lobe_ids", sorted(by_id), sorted(expected_ids))
    per_port = {0: 0, 1: 0}
    for lobe in computed["lobes"]:
        lid = f"rx{lobe['port']}_peak{lobe['peak_index']}"
        number = per_port[lobe["port"]]
        per_port[lobe["port"]] += 1
        if lid not in by_id:
            continue
        wanted = {"rx": lobe["port"], "port_peak_number": number, "peak_tap": lobe["peak_index"],
                  "plateau_end": lobe["plateau_end"], "boundary": lobe["boundary"], "peak_amplitude": lobe["peak_amplitude"],
                  "prominence": lobe["prominence"], "left_prominence_minimum": lobe["left_prominence_minimum"],
                  "right_prominence_minimum": lobe["right_prominence_minimum"], "left_local_valley": lobe["left_local_valley"],
                  "right_local_valley": lobe["right_local_valley"], "edge_tap": lobe["edge_tap"],
                  "eligible": bool(lobe["generated_taps"]), "reason": lobe["reason"],
                  "candidate_amplitude_floor": lobe["candidate_amplitude_floor"]}
        checks.fields(uid + ":" + lid, by_id[lid], wanted)
        checks.equal(uid + ":" + lid + ":taps", json.loads(by_id[lid]["candidate_taps_json"]), lobe["generated_taps"])
    return len(computed["lobes"])


def compare_candidates(checks: Comparisons, uid: str, mode: str, cir: np.ndarray, computed: dict, logged: list[dict]) -> int:
    pool = computed["pools"][mode]
    by_tap = {int(row["tap"]): row for row in logged}
    checks.equal(uid + ":" + mode + ":candidate_taps", sorted(by_tap), pool["taps"])
    lobes = {(lobe["port"], lobe["peak_index"]): lobe for lobe in computed["lobes"]}
    groups = {lid: number for number, component in enumerate(pool["groups"]) for lid in component}
    for tap in pool["taps"]:
        if tap not in by_tap:
            continue
        row = by_tap[tap]
        sources = pool["support"].get(tap, [])
        lids = [f"rx{port}_peak{peak}" for port, peak in sources]
        powers = np.abs(cir[tap]) ** 2
        denominator = float(powers.sum())
        ratio = float((powers[0] - powers[1]) / denominator) if denominator > 0 else None
        wanted = {"is_raw": tap == computed["raw"]["tap"], "supported": bool(sources),
                  "power_plus": float(powers[0]), "power_minus": float(powers[1]), "denominator": denominator,
                  "signed_s": ratio, "polarization_valid": denominator > 0 and math.isfinite(denominator) and ratio is not None and math.isfinite(ratio)}
        context = uid + ":" + mode + ":tap" + str(tap)
        checks.fields(context, row, wanted)
        for key, expected in (("support_ports_json", sorted({port for port, _ in sources})),
                              ("lobe_ids_json", sorted(lids)), ("group_ids_json", sorted({groups[lid] for lid in lids}))):
            checks.equal(context + ":" + key, sorted(json.loads(row[key])), expected)
        records = json.loads(row["support_records_json"])
        lookup = {(int(record["rx"]), int(record["peak_tap"])): record for record in records}
        checks.equal(context + ":support_record_ids", sorted(lookup), sorted(sources))
        checks.equal(context + ":support_record_unique", len(lookup), len(records))
        for port, peak in sources:
            if (port, peak) not in lookup:
                continue
            lobe = lobes[(port, peak)]
            lid = f"rx{port}_peak{peak}"
            wanted = {"rx": port, "lobe_id": lid, "group_id": groups[lid], "peak_tap": peak,
                      "edge_tap": lobe["edge_tap"], "peak_amplitude": lobe["peak_amplitude"],
                      "prominence": lobe["prominence"], "tap_amplitude": float(abs(cir[tap, port])),
                      "candidate_amplitude_floor": lobe["candidate_amplitude_floor"]}
            checks.fields(context + ":support", lookup[(port, peak)], wanted)
    return len(pool["taps"])


COUNT_FLAGS = ("raw_valid", "reference_valid", "normal", "wrong", "one_tap_error", "large_error", "original_invalid", "unknown_reference", "overflow", "reference_in_all", "reference_in_supported", "reference_usable", "raw_preserved")


def independent_counts(rows: list[dict]) -> dict:
    result = {"n_packet_mode_rows": len(rows)}
    for field in COUNT_FLAGS:
        result[field] = sum(1 for row in rows if row[field])
    for field in ("reference_in_all", "reference_in_supported", "reference_usable"):
        numerator = sum(1 for row in rows if row["large_error"] and row[field])
        result["large_error_" + field] = numerator
        result["large_error_" + field + "_recall"] = numerator / result["large_error"] if result["large_error"] else None
    result.update(large_error_status="OBSERVED" if result["large_error"] else "NOT_TESTED",
                  candidate_count_total=sum(row["candidate_count"] for row in rows),
                  candidate_count_max=max((row["candidate_count"] for row in rows), default=0),
                  supported_count_total=sum(row["supported_count"] for row in rows))
    return result


def compare_aggregates(checks: Comparisons, run: Path, rows: list[dict]) -> dict:
    summary = json.loads((run / "SUMMARY.json").read_bytes())
    static = json.loads((run / "STATIC_COORDINATE_SUMMARY.json").read_bytes())
    cells, populations, coordinates = {}, {}, {}
    for row in rows:
        cells.setdefault((row["corpus"], row["route"], row["channel"], row["mode"]), []).append(row)
        populations.setdefault((row["corpus"], row["channel"], row["mode"]), []).append(row)
        if row["corpus"] == "static_g4":
            coordinates.setdefault((row["coordinate"], row["channel"], row["mode"]), []).append(row)
    for label, groups, fields, actual_rows in (("cells", cells, ("corpus", "route", "channel", "mode"), summary["cells"]),
        ("populations", populations, ("corpus", "channel", "mode"), summary["populations"]),
        ("static", coordinates, ("coordinate", "channel", "mode"), static)):
        lookup = {tuple(item[field] for field in fields): item for item in actual_rows}
        checks.equal(label + ":group_count", len(lookup), len(groups))
        checks.equal(label + ":unique", len(lookup), len(actual_rows))
        for key, members in groups.items():
            checks.equal(label + ":key_present:" + repr(key), key in lookup, True)
            if key in lookup:
                checks.fields(label + ":" + repr(key), lookup[key], independent_counts(members))
                if label == "static":
                    checks.equal(label + ":condition_ids:" + repr(key), sorted(lookup[key]["condition_ids"]), sorted(row["condition_id"] for row in members))
    primary = independent_counts(populations[("dynamic", "Full", "TWO_PORT_UNION")])
    routes = {route: independent_counts(cells[("dynamic", route, "Full", "TWO_PORT_UNION")]) for route in ("R2", "R4", "R5")}
    checks.fields("summary_primary", summary["primary_dynamic_full_two_port_union"], primary)
    for route, counts in routes.items():
        checks.fields("summary_primary_" + route, summary["primary_by_route"][route], counts)
    recall = primary["large_error_reference_usable_recall"]
    overall = recall is not None and recall >= .95
    stratified = all(value["large_error_reference_usable_recall"] >= .95 for value in routes.values() if value["large_error"])
    status = "INCONCLUSIVE_NO_LARGE_ERRORS" if recall is None else "OBSERVED_THRESHOLD_MET" if overall and stratified else "NOT_SUPPORTED_STRATIFIED" if overall else "OBSERVED_THRESHOLD_NOT_MET"
    observed = {"threshold": .95, "status": status, "overall_threshold_met": overall, "nonempty_route_thresholds_met": stratified, "statistical_support": "DESCRIPTIVE_ONLY"}
    checks.fields("observed_gate", summary["observed_gate"], observed)
    checks.fields("claim_gates", summary, {"E1_02_E5_GO": False, "E2_GO": False, "external_independent_accept": False})
    episodes = []
    for key, members in cells.items():
        if key[0] != "dynamic":
            continue
        ordered = sorted(members, key=lambda row: row["pose_id"])
        for number, episode in enumerate(error_episodes(ordered)):
            episodes.append({"episode_id": f"{key[1]}:{key[2]}:{key[3]}:{number}", "route": key[1], "channel": key[2], "mode": key[3],
                             "start_pose_id": episode["first_pose_id"], "end_pose_id": episode["last_pose_id"],
                             "start_t_s": episode["start_s"], "end_t_s": episode["end_s"],
                             **{field: episode[field] for field in ("n_packets", "n_recalled", "recall", "all_recalled", "any_recalled", "longest_missing_run")}})
    actual = list(csv_rows(run / "EPISODES.csv"))
    lookup = {row["episode_id"]: row for row in actual}
    checks.equal("episodes_unique", len(lookup), len(actual))
    checks.equal("episodes_count", len(actual), len(episodes))
    for episode in episodes:
        checks.fields(episode["episode_id"], lookup.get(episode["episode_id"], {}), episode)
    episode_summary = {"count": len(episodes), "all_recalled": sum(e["all_recalled"] for e in episodes),
                       "any_recalled": sum(e["any_recalled"] for e in episodes),
                       "longest_missing_run": max((e["longest_missing_run"] for e in episodes), default=0)}
    checks.fields("episode_summary", summary["episodes"], episode_summary)
    by_packet, paired = {}, {}
    for row in rows:
        by_packet.setdefault(row["packet_uid"], {})[row["mode"]] = row
    labels = ("both_usable", "only_union_usable", "only_strongest_usable", "neither_usable")
    for pair in by_packet.values():
        strong, union = pair["STRONGEST_ONLY"], pair["TWO_PORT_UNION"]
        key = (union["corpus"], union["route"], union["channel"])
        item = paired.setdefault(key, {"waveforms": 0, "large_errors": 0, **{name: 0 for name in labels}, **{"large_" + name: 0 for name in labels}})
        item["waveforms"] += 1
        label = {(True, True): "both_usable", (False, True): "only_union_usable", (True, False): "only_strongest_usable", (False, False): "neither_usable"}[(bool(strong["reference_usable"]), bool(union["reference_usable"]))]
        item[label] += 1
        if union["large_error"]:
            item["large_errors"] += 1
            item["large_" + label] += 1
    actual_pairs = {(item["corpus"], item["route"], item["channel"]): item for item in summary["paired_availability"]}
    checks.equal("paired_availability_group_count", len(actual_pairs), len(paired))
    for key, expected in paired.items():
        checks.fields("paired_availability:" + repr(key), actual_pairs.get(key, {}), expected)
    return {"primary": primary, "primary_by_route": routes, "observed_gate": observed,
            "episodes": episodes, "episode_summary": episode_summary,
            "paired_availability": [{"key": list(key), **value} for key, value in paired.items()],
            "cells": [{"key": list(key), **independent_counts(value)} for key, value in cells.items()]}


def audit_run(repo: Path, run: Path, output: Path, lock_path: Path, approval_path: Path) -> dict:
    repo, run, output = Path(repo).resolve(), Path(run).resolve(), Path(output).resolve()
    sys.path.insert(0, str(repo / "src"))
    # The shared gate authorizes the stage and verifies identities; it supplies
    # no candidate computations or scientific acceptance to this reviewer.
    from qclean_uwb.fp_sc.e1_contracts import verify_e1_lock
    gate = verify_e1_lock(repo, lock_path, approval_path)
    lock = json.loads(Path(lock_path).read_bytes())
    spec = json.loads((repo / lock["policy_spec_file"]).read_bytes())
    assert_primary_parameters(spec["fixed_generator"])
    if output.exists():
        raise FileExistsError("CHECKER_NEW_OUTPUT_REQUIRED")
    manifest = json.loads((run / "RUN_MANIFEST.json").read_bytes())
    if manifest.get("status") != "COMPLETED_PENDING_SEPARATE_RESULT_REVIEW" or manifest.get("actual_waveforms") != 6320 or manifest.get("actual_packet_mode_rows") != 12640:
        raise ValueError("CHECKER_RUN_NOT_COMPLETE")
    if manifest.get("execution_lock_sha256") != digest_file(lock_path) or manifest.get("approval_sha256") != digest_file(approval_path):
        raise ValueError("CHECKER_RUN_LOCK_BINDING")
    for manifest_key, lock_key in (("input_lock_sha256", "input_lock_file"), ("environment_lock_sha256", "environment_file"),
                                  ("policy_spec_sha256", "policy_spec_file"), ("code_lock_sha256", "code_lock_file")):
        if manifest.get(manifest_key) != digest_file(repo / lock[lock_key]):
            raise ValueError("CHECKER_RUN_DOCUMENT_BINDING: " + manifest_key)
    artifacts = json.loads((run / "ARTIFACT_HASHES.json").read_bytes())
    for relative, expected in artifacts.items():
        if Path(relative).is_absolute() or ".." in Path(relative).parts or digest_file(run / relative) != expected:
            raise ValueError("CHECKER_RESULT_ARTIFACT_DRIFT: " + relative)
    ledger = json.loads((run / "FAILURE_LEDGER.json").read_bytes())
    if ledger["failures"] or ledger["excluded_input_rows"] != 0:
        raise ValueError("CHECKER_FAILED_OR_EXCLUDED_INPUTS")
    coverage = {}
    for row in csv_rows(run / "PACKET_CANDIDATE_COVERAGE.csv"):
        key = (row["packet_uid"], row["mode"])
        if key in coverage:
            raise ValueError("CHECKER_DUPLICATE_PACKET_MODE")
        coverage[key] = row
    if len(coverage) != 12640:
        raise ValueError("CHECKER_COVERAGE_ROW_COUNT")
    output.mkdir(parents=True, exist_ok=False)
    checks = Comparisons()
    causality = review_causality(repo / "src/qclean_uwb/fp_sc/candidates.py", repo / "src/qclean_uwb/drivesim/observation.py")
    write_json_new(output / "CODE_CAUSALITY_REVIEW.json", causality)
    rows, seen, waveform_count = [], set(), 0
    candidate_count = lobe_count = 0
    with tempfile.TemporaryDirectory(prefix="fp_sc_e1_review_") as temporary:
        connection = sqlite3.connect(str(Path(temporary) / "logs.sqlite"))
        log_counts = build_log_index(connection, run)
        for meta, cir, reference_cir in locked_corpus(repo):
            computed = scalar_candidate_pools(cir)
            reference = original_raw_fields(reference_cir)  # evaluator after candidate generation
            uid = meta["packet_uid"]
            lobes = [json.loads(item[0]) for item in connection.execute("SELECT item FROM lobe WHERE uid=?", (uid,))]
            lobe_count += compare_lobes(checks, uid, computed, lobes)
            for mode in ("STRONGEST_ONLY", "TWO_PORT_UNION"):
                key = (uid, mode)
                seen.add(key)
                calculated = {**meta, "mode": mode, **classify_availability(computed, reference, mode)}
                checks.fields(uid + ":" + mode, coverage.get(key, {}), calculated)
                raw = computed["raw"]
                peak = raw["peak"]
                checks.fields(uid + ":" + mode + ":raw_evidence", coverage.get(key, {}),
                    {"raw_peak": peak, "raw_denominator": raw["denominator"], "raw_signed_s": raw["s"],
                     "raw_range_m": raw["tap"] * 299792458.0 / (1028 * 1_950_000.0) if raw["tap"] is not None else None,
                     "noise_amplitude_floor": computed["noise_floor"],
                     "numeric_amplitude_floor": 64.0 * EPS * peak if peak is not None else None})
                logged = [json.loads(item[0]) for item in connection.execute("SELECT item FROM candidate WHERE uid=? AND mode=?", key)]
                candidate_count += compare_candidates(checks, uid, mode, cir, computed, logged)
                rows.append(calculated)
            waveform_count += 1
            if waveform_count % 250 == 0:
                print("AUDIT_CANDIDATE_WAVEFORMS", waveform_count, "mismatches", checks.mismatches, flush=True)
        connection.close()
    checks.equal("exact_packet_mode_ids", sorted(seen), sorted(coverage))
    checks.equal("waveform_count", waveform_count, 6320)
    checks.equal("all_candidate_log_rows", log_counts["candidate"], candidate_count)
    checks.equal("all_lobe_log_rows", log_counts["lobe"], lobe_count)
    aggregates = compare_aggregates(checks, run, rows)
    write_json_new(output / "RECOMPUTED_AGGREGATES.json", aggregates)
    write_json_new(output / "NUMERICAL_COMPARISONS.json", checks.record())
    with (output / "RECOMPUTED_PACKET_COVERAGE.csv").open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    verdict = {"schema": "FP_SC_E1_01_SEPARATE_RESULT_REVIEW_V1", "role": ROLE,
               "status": "PASS_CANDIDATE_AVAILABILITY_REPRODUCTION" if checks.mismatches == 0 and causality["passed"] else "FAIL_CANDIDATE_AVAILABILITY_REPRODUCTION",
               "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "checker_sha256": digest_file(Path(__file__)),
               "production_run_manifest_sha256": digest_file(run / "RUN_MANIFEST.json"),
               "production_artifact_index_sha256": digest_file(run / "ARTIFACT_HASHES.json"),
               "execution_lock_sha256": digest_file(lock_path), "policy_spec_sha256": digest_file(repo / lock["policy_spec_file"]),
               "input_lock_sha256": digest_file(repo / lock["input_lock_file"]),
               "environment_lock_sha256": digest_file(repo / lock["environment_file"]),
               "verified_gate": gate, "waveforms_recomputed": waveform_count, "packet_mode_rows_recomputed": len(rows),
               "candidate_rows_recomputed": candidate_count, "lobe_rows_recomputed": lobe_count,
               "comparison_summary": checks.record(), "observed_gate": aggregates["observed_gate"],
               "external_independent_accept": False, "E1_02_E5_GO": False, "E2_GO": False,
               "limits": "Same-session separate implementation, shared NumPy FFT runtime. Scalar lobe/edge/support decisions and all corpus/denominator/episode rows recomputed. Stored pool_hash digest and wording-only raw/pool reason fields are not numerical proof; artifact hashes bind them. No selector or EKF validation, no IID inference."}
    write_json_new(output / "E1_RESULT_REVIEW.json", verdict)
    write_json_new(output / "ARTIFACT_HASHES.json", {p.name: digest_file(p) for p in sorted(output.iterdir()) if p.is_file()})
    print("AUDIT_E1_DONE", verdict["status"], "mismatches", checks.mismatches, flush=True)
    return verdict


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--approval", type=Path, required=True)
    args = parser.parse_args()
    result = audit_run(args.repo, args.run, args.output, args.lock, args.approval)
    if result["status"].startswith("FAIL"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
