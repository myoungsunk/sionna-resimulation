"""FP-SC-001 E1-01: pure current-CIR candidate construction, no selection.

No GT, reference channel, route, seed, prior, history or posterior is accepted.
The two pool modes reuse exactly the same per-port lobe analysis.  A candidate
is a supported leading-edge sample, not an independently resolved RF path.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from typing import Any

import numpy as np

from qclean_uwb.drivesim import observation


MODES = ("STRONGEST_ONLY", "TWO_PORT_UNION")


@dataclass(frozen=True)
class CandidateConfig:
    eta_prominence: float = 0.06
    leading_edge_fraction: float = 0.30
    neighbor_radius_taps: int = 1
    local_candidate_fraction: float = 0.15
    minimum_noise_sigma: float = 3.0
    packet_pfa: float = 0.001
    numeric_epsilon_multiplier: float = 64.0
    maximum_usable_candidates: int = 64
    noise_var_per_bin: float = 0.0
    denominator_floor: float = 0.0

    def validate(self) -> None:
        values = asdict(self)
        if not all(np.isfinite(v) for v in values.values()):
            raise ValueError("NONFINITE_CONFIG")
        if not 0 < self.eta_prominence <= 1 or not 0 < self.leading_edge_fraction < 1:
            raise ValueError("INVALID_PROMINENCE_OR_EDGE_FRACTION")
        if not 0 < self.local_candidate_fraction <= self.leading_edge_fraction:
            raise ValueError("INVALID_LOCAL_SUPPORT_FRACTION")
        if self.neighbor_radius_taps != 1:
            raise ValueError("THIS_FAMILY_REQUIRES_ONE_TAP_NEIGHBORS")
        if self.minimum_noise_sigma < 0 or not 0 < self.packet_pfa < 1:
            raise ValueError("INVALID_NOISE_RULE")
        if self.numeric_epsilon_multiplier <= 0 or self.maximum_usable_candidates < 1:
            raise ValueError("INVALID_NUMERIC_OR_OVERFLOW_RULE")
        if self.noise_var_per_bin < 0 or self.denominator_floor < 0:
            raise ValueError("NEGATIVE_NOISE_OR_DENOMINATOR_FLOOR")


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _peaks(a: np.ndarray) -> list[tuple[int, int]]:
    """Interior maximal plateaus, returning earliest/latest peak index."""
    peaks = []
    i = 1
    while i < len(a) - 1:
        if a[i] > a[i - 1]:
            end = i
            while end + 1 < len(a) and a[end + 1] == a[i]:
                end += 1
            if end < len(a) - 1 and a[end] > a[end + 1]:
                peaks.append((i, end))
            i = end + 1
        else:
            i += 1
    return peaks


def _peak_geometry(a: np.ndarray, first: int, last: int) -> dict[str, Any]:
    height = float(a[first])
    left_limit = first
    while left_limit > 0 and a[left_limit - 1] <= height:
        left_limit -= 1
    right_limit = last
    while right_limit + 1 < len(a) and a[right_limit + 1] <= height:
        right_limit += 1
    left_values = a[left_limit:first + 1]
    right_values = a[last:right_limit + 1]
    left_min = float(left_values.min())
    right_min = float(right_values.min())
    # Closest minimum on ties, as distinct from the local monotone valley.
    left_prominence_index = left_limit + int(np.flatnonzero(left_values == left_min)[-1])
    right_prominence_index = last + int(np.flatnonzero(right_values == right_min)[0])
    left_local = first
    while left_local > 0 and a[left_local - 1] <= a[left_local]:
        left_local -= 1
    right_local = last
    while right_local + 1 < len(a) and a[right_local + 1] <= a[right_local]:
        right_local += 1
    return {
        "peak_tap": first, "plateau_end": last, "peak_amplitude": height,
        "prominence": height - max(left_min, right_min),
        "left_prominence_minimum": left_prominence_index,
        "right_prominence_minimum": right_prominence_index,
        "left_local_valley": left_local, "right_local_valley": right_local,
    }


def _port_lobes(a: np.ndarray, rx: int, global_peak: float, noise_floor: float,
                numeric_floor: float, config: CandidateConfig) -> list[dict[str, Any]]:
    records = []
    minimum_prominence = max(noise_floor, config.eta_prominence * global_peak)
    peaks = [(first, last, False) for first, last in _peaks(a)]
    first_end = 0
    while first_end + 1 < len(a) and a[first_end + 1] == a[0]:
        first_end += 1
    if first_end + 1 < len(a) and a[first_end] > a[first_end + 1]:
        peaks.append((0, first_end, True))
    last_start = len(a) - 1
    while last_start > 0 and a[last_start - 1] == a[-1]:
        last_start -= 1
    if last_start > 0 and a[last_start] > a[last_start - 1]:
        peaks.append((last_start, len(a) - 1, True))
    for number, (first, last, boundary) in enumerate(sorted(peaks)):
        record = {"lobe_id": f"rx{rx}_peak{first}", "rx": rx, "port_peak_number": number,
                  **_peak_geometry(a, first, last), "edge_tap": None,
                  "candidate_taps": [], "boundary": boundary, "eligible": False, "reason": None}
        peak = record["peak_amplitude"]
        if boundary:
            record["reason"] = "BOUNDARY_PEAK_NOT_CANDIDATE"
        elif peak < max(noise_floor, numeric_floor):
            record["reason"] = "BELOW_ABSOLUTE_SUPPORT"
        elif record["prominence"] < minimum_prominence:
            record["reason"] = "BELOW_PROMINENCE"
        elif a[record["left_local_valley"]] >= config.leading_edge_fraction * peak:
            record["reason"] = "UNRESOLVED_LOCAL_LEADING_EDGE"
        else:
            low = record["left_local_valley"]
            hits = np.flatnonzero(a[low:first + 1] >= config.leading_edge_fraction * peak)
            if not len(hits):
                raise RuntimeError("INTERNAL_EDGE_SEARCH_FAILURE")
            edge = low + int(hits[0])
            record["edge_tap"] = edge
            candidate_floor = max(noise_floor, numeric_floor, config.local_candidate_fraction * peak)
            record["candidate_amplitude_floor"] = float(candidate_floor)
            record["candidate_taps"] = [int(n) for n in (edge - 1, edge, edge + 1)
                                         if low <= n <= first and a[n] >= candidate_floor]
            record["eligible"] = bool(record["candidate_taps"])
            record["reason"] = "SUPPORTED_LOBE" if record["eligible"] else "NO_SUPPORTED_EDGE_TAP"
        records.append(record)
    return records


def _groups(lobes: list[dict[str, Any]]) -> dict[str, int]:
    """Connected components of strictly overlapping local basin interiors."""
    usable = [record for record in lobes if record["eligible"]]
    parent = list(range(len(usable)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, left in enumerate(usable):
        for j in range(i):
            right = usable[j]
            if max(left["left_local_valley"], right["left_local_valley"]) < min(left["right_local_valley"], right["right_local_valley"]):
                parent[find(i)] = find(j)
    def component_key(root: int) -> tuple[int, int, int, int]:
        return min((record["left_local_valley"], record["right_local_valley"], record["rx"], record["peak_tap"])
                   for i, record in enumerate(usable) if find(i) == root)

    roots = sorted({find(i) for i in range(len(usable))}, key=component_key)
    labels = {root: i for i, root in enumerate(roots)}
    return {record["lobe_id"]: labels[find(i)] for i, record in enumerate(usable)}


def _pool(mode: str, cir: np.ndarray, raw: dict[str, Any], lobes: list[dict[str, Any]],
          config: CandidateConfig, noise_floor: float, numeric_floor: float) -> dict[str, Any]:
    ports = [raw["rx"]] if mode == "STRONGEST_ONLY" else [0, 1]
    selected_lobes = [record for record in lobes if record["rx"] in ports]
    groups = _groups(selected_lobes)
    by_tap: dict[int, dict[str, Any]] = {}
    for lobe in selected_lobes:
        for tap in lobe["candidate_taps"]:
            row = by_tap.setdefault(tap, {"tap": tap, "is_raw": tap == raw["tap"],
                                         "supported": True, "support_records": []})
            row["support_records"].append({
                "rx": lobe["rx"], "lobe_id": lobe["lobe_id"], "group_id": groups[lobe["lobe_id"]],
                "peak_tap": lobe["peak_tap"], "edge_tap": lobe["edge_tap"],
                "peak_amplitude": lobe["peak_amplitude"], "prominence": lobe["prominence"],
                "tap_amplitude": float(abs(cir[tap, lobe["rx"]])),
                "candidate_amplitude_floor": lobe["candidate_amplitude_floor"],
            })
    if raw["valid"]:
        by_tap.setdefault(raw["tap"], {"tap": raw["tap"], "is_raw": True,
                                       "supported": False, "support_records": []})
    else:
        # A source index from zero signal is metadata, not a fabricated candidate.
        by_tap.clear()
    candidates = []
    for tap, row in sorted(by_tap.items()):
        powers = np.abs(cir[tap]) ** 2
        den = float(powers.sum())
        valid_s = bool(np.isfinite(powers).all() and den > config.denominator_floor)
        row.update(power_plus=float(powers[0]), power_minus=float(powers[1]), denominator=den,
                   signed_s=float((powers[0] - powers[1]) / den) if valid_s else None,
                   polarization_valid=valid_s,
                   support_ports=sorted({s["rx"] for s in row["support_records"]}),
                   lobe_ids=sorted({s["lobe_id"] for s in row["support_records"]}),
                   group_ids=sorted({s["group_id"] for s in row["support_records"]}))
        if not valid_s:
            row["supported"] = False
        candidates.append(row)
    overflow = len(candidates) > config.maximum_usable_candidates
    result = {
        "mode": mode, "raw": raw, "candidates": candidates,
        "candidate_taps": [record["tap"] for record in candidates],
        "supported_taps": [record["tap"] for record in candidates if record["supported"]],
        "lobes": selected_lobes, "noise_amplitude_floor": noise_floor,
        "numeric_amplitude_floor": numeric_floor, "overflow": overflow,
        "usable": bool(raw["valid"] and not overflow),
        "status": "ORIGINAL_INVALID" if not raw["valid"] else "OVERFLOW" if overflow else "CANDIDATES_GENERATED",
        "config": asdict(config),
    }
    result["pool_hash"] = _digest(result)
    return result


def generate_pools(cir: np.ndarray, config: CandidateConfig = CandidateConfig()) -> dict[str, dict[str, Any]]:
    """Return both pure CIR-only pools, preserving all rejected/invalid evidence.

    The generator never replaces a tap.  Invalid nonfinite input produces empty
    pools and an explicit status; malformed array shape/dtype raises an error.
    Corpus runners may fail closed on any unexpected nonfinite source payload.
    """
    config.validate()
    c = np.asarray(cir)
    if c.shape != (1028, 2) or not np.iscomplexobj(c):
        raise ValueError("EXPECTED_COMPLEX_CIR_1028_BY_2")
    if not np.isfinite(c).all():
        invalid = {"tap": None, "rx": None, "valid": False, "reason": "NONFINITE_CIR"}
        return {mode: {"mode": mode, "raw": invalid.copy(), "candidates": [], "candidate_taps": [],
                       "supported_taps": [], "lobes": [], "overflow": False, "usable": False,
                       "status": "NONFINITE_CIR", "config": asdict(config),
                       "pool_hash": _digest({"mode": mode, "status": "NONFINITE_CIR", "config": asdict(config)})}
                for mode in MODES}
    a = np.abs(c)
    peak = float(a.max())
    raw_obs = observation.first_path_batch(c[None], 1_950_000.0)
    rx = int(a.max(axis=0).argmax())
    tap = int(raw_obs["index"][0])
    den = float(raw_obs["power"][0].sum())
    v_c = 6.0 * config.noise_var_per_bin
    noise_floor = max(config.minimum_noise_sigma * math.sqrt(v_c),
                      math.sqrt(v_c * math.log(2 * 1028 / config.packet_pfa)))
    numeric_floor = config.numeric_epsilon_multiplier * np.finfo(float).eps * peak
    raw_valid = bool(peak > 0 and peak >= max(noise_floor, numeric_floor)
                     and den > config.denominator_floor and np.isfinite(raw_obs["s"][0]))
    raw = {"tap": tap, "rx": rx, "valid": raw_valid, "peak": peak, "denominator": den,
           "signed_s": float(raw_obs["s"][0]) if np.isfinite(raw_obs["s"][0]) else None,
           "range_m": float(raw_obs["range_m"][0]),
           "reason": "VALID_CLEAN_OR_DECLARED_SUPPORT" if raw_valid else "NO_VALID_ORIGINAL_SUPPORT"}
    lobes = []
    if raw_valid:
        for port in (0, 1):
            lobes.extend(_port_lobes(a[:, port], port, peak, noise_floor, numeric_floor, config))
    result = {mode: _pool(mode, c, raw, lobes, config, noise_floor, numeric_floor) for mode in MODES}
    if not set(result["STRONGEST_ONLY"]["candidate_taps"]).issubset(result["TWO_PORT_UNION"]["candidate_taps"]):
        raise RuntimeError("STRONGEST_POOL_NOT_SUBSET_OF_UNION")
    return result


def generate_candidates(cir: np.ndarray, *, mode: str = "TWO_PORT_UNION",
                        config: CandidateConfig = CandidateConfig()) -> dict[str, Any]:
    if mode not in MODES:
        raise ValueError("UNKNOWN_CANDIDATE_MODE")
    return generate_pools(cir, config)[mode]
