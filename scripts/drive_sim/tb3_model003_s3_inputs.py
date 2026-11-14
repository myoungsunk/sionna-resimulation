"""Paired per-packet RF observations and wheel controls for MODEL-003 S3.

The module consumes public timeline rows and clean channels supplied by the
caller. No estimator or experiment runner is invoked here.

``paired_observations(data, rows, obs, df, rules, snr_db=..., seeds=...)``
returns a mapping from output rule name to ``z`` arrays shaped
``(packets, seeds, 2)`` with columns raw range [m] and selected-tap signed
polarization ``s``. ``rules`` may be an iterable of S1 detector rule names,
or a mapping from chain labels (for example ``OR`` and ``O30``) to detector
rule names. One noisy CIR is made per timeline packet and seed; all requested
rules share it. Thus downstream arms, signs and bias levels can reuse exactly
the same RF draw.

``wheel_controls`` returns measured signed distance controls shaped
``(packets, seeds)``. It adds independent Gaussian noise with variance
``2e-5 * abs(ds)`` per packet and sensor seed, shared across signs/scenarios.
Measured gyro controls are supplied by the caller from the synthetic motion
helper; this function does not substitute truth yaw for gyro.
"""
from __future__ import annotations

import math
import operator
import random
from collections.abc import Iterable, Mapping

import numpy as np

from tb3_model003_s1_observation import (
    RULES as DETECTOR_RULES,
    channel_to_cir,
    range_candidates,
    signed_s_at_tap,
)


DEFAULT_SEEDS = tuple(range(20))
PACKET_BATCH = 32


def _seeds(values: Iterable[int]) -> tuple[int, ...]:
    result = tuple(operator.index(seed) for seed in values)
    if not result or len(set(result)) != len(result) or any(seed < 0 for seed in result):
        raise ValueError("seeds must be distinct nonnegative integers")
    return result


def _rule_map(rules) -> dict[str, str]:
    if isinstance(rules, Mapping):
        result = {str(label): str(rule) for label, rule in rules.items()}
    else:
        result = {str(rule): str(rule) for rule in rules}
    if not result or len(result) != len(set(result)):
        raise ValueError("At least one uniquely labelled ranging rule is required")
    if any(rule not in DETECTOR_RULES for rule in result.values()):
        raise ValueError("Unknown S1 detector rule in rules")
    return result


def _row_int(row, field: str) -> int:
    try:
        value = operator.index(row[field])
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Timeline row needs integer {field}") from exc
    if value < 0:
        raise ValueError(f"Timeline {field} must be nonnegative")
    return value


def paired_observations(data: Mapping, rows: Iterable[Mapping], obs, df: float, rules, *,
                        snr_db: float, seeds: Iterable[int] = DEFAULT_SEEDS) -> dict[str, np.ndarray]:
    """Create matched raw range/s observations for each packet and seed.

    The packet ``thermal_noise_seed`` and sensor seed index form an independent
    RNG key for each packet/seed. Rows are processed in fixed-size chunks to
    bound channel/CIR memory. ``data['full']`` is indexed by each row's
    ``rf_pose_id``; non-detections remain NaN in both output columns.
    """
    rows = tuple(rows)
    seeds = _seeds(seeds)
    rule_map = _rule_map(rules)
    if not rows:
        raise ValueError("Expected nonempty packet timeline rows")
    if not math.isfinite(float(df)) or float(df) <= 0 or not math.isfinite(float(snr_db)):
        raise ValueError("df and snr_db must be finite; df must be positive")
    channels = data.get("full")
    if channels is None or getattr(channels, "ndim", None) != 4:
        raise ValueError("data['full'] must be a batched RF channel array")
    pose_ids = [_row_int(row, "rf_pose_id") for row in rows]
    if max(pose_ids) >= len(channels):
        raise ValueError("Timeline rf_pose_id exceeds data['full']")
    thermal_seeds = [_row_int(row, "thermal_noise_seed") for row in rows]
    noise_var = float(obs.noise_var_from_snr(float(snr_db)))
    threshold = float(obs.detection_threshold(noise_var, n_taps=channels.shape[1] * 4))
    detector_names = tuple(dict.fromkeys(rule_map.values()))
    output = {label: np.full((len(rows), len(seeds), 2), np.nan, dtype=np.float64)
              for label in rule_map}

    for seed_index, seed in enumerate(seeds):
        for start in range(0, len(rows), PACKET_BATCH):
            stop = min(start + PACKET_BATCH, len(rows))
            cir_batch = []
            for packet in range(start, stop):
                rng = np.random.default_rng(np.random.SeedSequence([thermal_seeds[packet], seed]))
                cir_batch.append(channel_to_cir(
                    np.asarray(channels[pose_ids[packet]:pose_ids[packet] + 1]),
                    obs, noise_var=noise_var, rng=rng))
            cir = np.concatenate(cir_batch, axis=0)
            detected = range_candidates(cir, float(df), threshold=threshold, rules=detector_names)
            signed_by_rule = {
                rule: signed_s_at_tap(cir, candidate["tap"], candidate["detected"])
                for rule, candidate in detected.items()
            }
            for label, detector in rule_map.items():
                candidate = detected[detector]
                output[label][start:stop, seed_index, 0] = candidate["range_m"]
                output[label][start:stop, seed_index, 1] = signed_by_rule[detector]
    return output


def _signed_chord_distances(rows: tuple[Mapping, ...], geometry: Mapping) -> np.ndarray:
    """Use signed body-frame chord direction with timeline distance magnitude."""
    distance = np.asarray(geometry["distance_increment_m"], dtype=float)
    if distance.shape != (len(rows),) or not np.isfinite(distance).all() or np.any(distance < 0):
        raise ValueError("geometry distance_increment_m must be finite nonnegative packet values")
    if len(rows) < 1:
        raise ValueError("Expected timeline rows")
    signed = distance.copy()
    if all("truth_x_m" in row and "truth_y_m" in row and "truth_yaw_deg" in row for row in rows):
        xy = np.asarray([[float(row["truth_x_m"]), float(row["truth_y_m"])] for row in rows])
        yaw = np.radians(np.asarray([float(row["truth_yaw_deg"]) for row in rows]))
        if not np.isfinite(xy).all() or not np.isfinite(yaw).all():
            raise ValueError("Timeline truth position/yaw must be finite")
        modes = tuple(geometry.get("motion", (None,) * len(rows)))
        if len(modes) != len(rows):
            raise ValueError("geometry motion length does not match rows")
        for i in range(1, len(rows)):
            if modes[i] == "restart" or rows[i].get("stream") != rows[i-1].get("stream"):
                signed[i] = 0.0
                continue
            chord = xy[i] - xy[i-1]
            mid_yaw = yaw[i-1] + ((yaw[i] - yaw[i-1] + math.pi) % math.tau - math.pi) / 2.0
            forward = float(chord @ np.array([math.cos(mid_yaw), math.sin(mid_yaw)]))
            if distance[i] == 0.0 or abs(forward) <= 1e-12:
                signed[i] = 0.0 if distance[i] == 0.0 else distance[i]
            else:
                signed[i] = math.copysign(distance[i], forward)
    elif "signed_chord_ds_m" in geometry:
        signed = np.asarray(geometry["signed_chord_ds_m"], dtype=float)
        if signed.shape != (len(rows),) or not np.isfinite(signed).all():
            raise ValueError("signed_chord_ds_m must be finite and match rows")
    return signed


def wheel_controls(rows: Iterable[Mapping], geometry: Mapping, path_id: str, *,
                   seeds: Iterable[int] = DEFAULT_SEEDS) -> dict:
    """Add deterministic Sensor-v2 wheel-distance noise to signed chord ds.

    The returned ``distance_m`` array has shape ``(packets, seeds)``. A single
    packet/seed noise draw is reused across bias levels and signs. ``path_id``
    namespaces streams so unrelated paths do not reuse wheel noise.
    """
    rows = tuple(rows)
    seeds = _seeds(seeds)
    if not isinstance(path_id, str) or not path_id:
        raise ValueError("path_id must be a nonempty string")
    ds = _signed_chord_distances(rows, geometry)
    controls = np.empty((len(rows), len(seeds)), dtype=np.float64)
    for j, seed in enumerate(seeds):
        rng = random.Random(f"G1-MODEL-003/wheel/{path_id}/{seed}")
        for i, value in enumerate(ds):
            sigma = math.sqrt(2e-5 * abs(float(value)))
            controls[i, j] = float(value) + rng.gauss(0.0, sigma) if sigma else float(value)
    return dict(distance_m=controls, truth_signed_chord_m=ds, seeds=seeds,
                variance_model="2e-5 * abs(signed chord ds)", path_id=path_id)


def synthetic_self_check() -> dict:
    """Check packet/seed determinism, shared-rule CIR, chunking and reverse ds."""
    class SyntheticObservation:
        def noise_var_from_snr(self, snr_db):
            return 10.0 ** (-float(snr_db) / 10.0)

        def detection_threshold(self, noise_var, *, n_taps):
            return 0.0

        def cir_batch(self, h):
            return np.fft.ifft(h, axis=1)

    obs = SyntheticObservation()
    rng = np.random.default_rng(17)
    packet_count = PACKET_BATCH + 3
    channels = rng.normal(size=(packet_count, 16, 2, 2)) + 1j * rng.normal(size=(packet_count, 16, 2, 2))
    rows = [dict(rf_pose_id=i, thermal_noise_seed=1000+i, stream="P-C",
                 truth_x_m=float(i if i <= PACKET_BATCH else 2*PACKET_BATCH-i),
                 truth_y_m=0.0, truth_yaw_deg=0.0) for i in range(packet_count)]
    geometry = dict(distance_increment_m=[0.0] + [1.0] * (packet_count-1),
                    motion=["start"] + ["straight"] * (packet_count-1))
    first = paired_observations(dict(full=channels), rows, obs, 1.0,
                                {"OR": "O20", "O30": "O30"}, snr_db=30, seeds=range(3))
    second = paired_observations(dict(full=channels), rows, obs, 1.0,
                                 {"OR": "O20", "O30": "O30"}, snr_db=30, seeds=range(3))
    if not all(np.array_equal(first[key], second[key], equal_nan=True) for key in first):
        raise AssertionError("RF observations are not deterministic")
    reordered = paired_observations(dict(full=channels), rows[::-1], obs, 1.0,
                                    {"OR": "O20", "O30": "O30"}, snr_db=30, seeds=range(3))
    if not np.array_equal(first["OR"][::-1], reordered["OR"], equal_nan=True):
        raise AssertionError("RF draws depend on row/chunk ordering")
    wheel_a = wheel_controls(rows, geometry, "synthetic", seeds=range(3))
    wheel_b = wheel_controls(rows, geometry, "synthetic", seeds=range(3))
    if not np.array_equal(wheel_a["distance_m"], wheel_b["distance_m"]):
        raise AssertionError("Wheel controls are not deterministic")
    if wheel_a["truth_signed_chord_m"][-1] >= 0:
        raise AssertionError("Reverse chord did not produce negative wheel distance")
    return dict(status="PASS", packets=len(rows), chunk_size=PACKET_BATCH, seeds=3,
                output_shape=list(first["OR"].shape), reverse_ds=float(wheel_a["truth_signed_chord_m"][-1]))


if __name__ == "__main__":
    import json
    print(json.dumps(synthetic_self_check(), indent=2))
