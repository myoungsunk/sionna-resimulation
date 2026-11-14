"""Deterministic RF-free motion inputs for G1-MODEL-003 DR and paired EKF arms.

Sources: SPEC_B_NEW_RT_KO §§2.1–2.3 and S2-F, Sensor-v2 white gyro noise,
and G1_SWEEP_HEADING_FLOOR_20261113/SPEC_KO.md §5.1 (Allan-bag hold drift).
"""

import json
import math
import operator
import random


DEFAULT_SEEDS = tuple(range(20))
SIGNS = (-1, 1)
BIAS_DEG_PER_S = {"B0": 0.0, "L0": 0.01, "L1": 0.05, "L2": 0.20}
WHITE_NOISE_DEG_PER_SQRT_S = 0.015
TB3_SCALE = {"TB3_r1.3.1": 0.0085, "TB3_r2.1.0": 0.0020}
TB3_HOLD_DRIFT_DEG_PER_S = 0.0005


def _wrap(angle):
    return (angle + math.pi) % math.tau - math.pi


def geometry_from_rows(rows):
    """Read one ordered frozen path, or TEACH followed by one REPEAT stream.

    The input mappings may contain other timeline fields. Signed net turn is
    derived from consecutive truth yaws; total angular travel comes from the
    integrated absolute-turn column (which retains sub-packet reversals).
    A TEACH to REPEAT restart changes the truth origin and has zero motion.
    The elapsed clock continues and the DR error state is carried through it.
    """
    geometry = dict(elapsed_s=[], distance_increment_m=[], signed_yaw_increment_rad=[],
                    angular_travel_rad=[], motion=[])
    previous = None
    for row in rows:
        case = row["case"]
        stream = row["stream"]
        index = int(row["stream_sequence"])
        elapsed = float(row["t_s"])
        yaw = math.radians(float(row["truth_yaw_deg"]))
        yaw_travel = math.radians(float(row["abs_yaw_increment_deg"]))
        distance = float(row["distance_increment_m"])
        if not all(math.isfinite(value) for value in (elapsed, yaw, yaw_travel, distance)):
            raise ValueError("Expected finite timeline geometry")
        if yaw_travel < 0 or distance < 0:
            raise ValueError("Expected nonnegative integrated timeline motion")
        restart = previous is not None and stream != previous[1]
        if previous is None or restart:
            if index != 0 or distance != 0 or yaw_travel != 0:
                raise ValueError("A timeline stream must start at row 0 with zero motion")
            if restart and (previous[1] != "TEACH" or not (stream == "REPEAT" or stream.startswith("REPEAT_PE_"))):
                raise ValueError("Only TEACH to REPEAT can share an elapsed clock")
            signed_yaw = 0.0
        else:
            if index != previous[2] + 1:
                raise ValueError("Timeline stream rows must be contiguous in order")
            signed_yaw = _wrap(yaw - previous[3])
        if previous is not None and (case != previous[0] or elapsed <= previous[4]):
            raise ValueError("A motion path requires one case and increasing timeline timestamps")
        geometry["elapsed_s"].append(elapsed)
        geometry["distance_increment_m"].append(distance)
        geometry["signed_yaw_increment_rad"].append(signed_yaw)
        geometry["angular_travel_rad"].append(yaw_travel)
        geometry["motion"].append("restart" if restart else row["motion"])
        previous = case, stream, index, yaw, elapsed
    return geometry


def generate_motion(elapsed_s, distance_increment_m, signed_yaw_increment_rad, motion, *,
                    path_id, seeds=DEFAULT_SEEDS, angular_travel_rad=None):
    """Return per-scenario DR errors and measured gyro increments, in radians.

    Each scenario maps to nested lists shaped (packet, seed, sign); the sign
    axis is (-1, +1). Use the same path_id across anchor cases of the same path.
    Sensor noise is a single deterministic Gaussian stream per (path_id, seed),
    shared across scenarios and signs. White angle noise has standard deviation
    N√dt and gyro bias has zero random walk. Starting heading error is zero.

    Elapsed time covers the interval ending at each packet after the first.
    TB3 turn error accumulates k times absolute angular travel with a fixed sign.
    TB3 drift uses the interval's right-end motion label 'hold', matching the
    frozen dwell packet counts. The administrative restart gets neither turning
    error nor hold drift. White noise and any Sensor-v2 bias use elapsed time.
    TB3 b_eq reports the turn-only contribution in deg/s as specified in §2.3.
    """
    time = tuple(elapsed_s)
    distance = tuple(distance_increment_m)
    signed_yaw = tuple(signed_yaw_increment_rad)
    modes = tuple(motion)
    travel = tuple(map(abs, signed_yaw)) if angular_travel_rad is None else tuple(angular_travel_rad)
    seeds = tuple(operator.index(seed) for seed in seeds)
    if not isinstance(path_id, str) or not path_id or not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("Expected a path identifier and distinct integer seeds")
    if len(time) < 2 or any(len(values) != len(time) for values in (distance, signed_yaw, travel, modes)):
        raise ValueError("Expected one elapsed time, distance, yaw and motion label per packet")
    if any(not math.isfinite(value) for values in (time, distance, signed_yaw, travel) for value in values):
        raise ValueError("Expected finite motion inputs")
    delta_t = (0.0, *(b - a for a, b in zip(time, time[1:])))
    if any(dt <= 0 for dt in delta_t[1:]):
        raise ValueError("Elapsed time must be strictly increasing")
    if any(step < 0 for step in distance) or any(step < 0 for step in travel):
        raise ValueError("Expected nonnegative distance and angular travel increments")
    if any(abs(net) > total + 1e-10 for net, total in zip(signed_yaw, travel, strict=True)):
        raise ValueError("Signed net turn cannot exceed total angular travel")
    if any(distance[i] != 0 or travel[i] != 0 or signed_yaw[i] != 0
           for i, mode in enumerate(modes) if i == 0 or mode == "restart"):
        raise ValueError("Initial and restart packets must have zero motion")

    hold_time = tuple(dt if mode == "hold" else 0.0 for dt, mode in zip(delta_t, modes, strict=True))
    noise_scale = [math.radians(WHITE_NOISE_DEG_PER_SQRT_S) * math.sqrt(dt) for dt in delta_t]
    noise = [[0.0] for _ in seeds]
    for seed, increments in zip(seeds, noise, strict=True):
        rng = random.Random(f"G1-MODEL-003/gyro/{path_id}/{seed}")
        increments.extend(rng.gauss(0.0, scale) for scale in noise_scale[1:])

    magnitude = {name: [math.radians(rate) * dt for dt in delta_t]
                 for name, rate in BIAS_DEG_PER_S.items()}
    for name, k in TB3_SCALE.items():
        hold_drift = math.radians(TB3_HOLD_DRIFT_DEG_PER_S)
        magnitude[name] = [k * angle + hold_drift * hold
                           for angle, hold in zip(travel, hold_time, strict=True)]

    heading_errors, gyro_increments = {}, {}
    for name, bias_increments in magnitude.items():
        accumulated = [[0.0, 0.0] for _ in seeds]
        heading_errors[name] = heading = []
        gyro_increments[name] = gyro = []
        for packet, (turn, bias_increment) in enumerate(zip(signed_yaw, bias_increments, strict=True)):
            packet_gyro, packet_heading = [], []
            for seed_index, common_noise in enumerate(noise):
                increment = [common_noise[packet] + sign * bias_increment for sign in SIGNS]
                for i, value in enumerate(increment):
                    accumulated[seed_index][i] += value
                packet_gyro.append([turn + value for value in increment])
                packet_heading.append([_wrap(value) for value in accumulated[seed_index]])
            gyro.append(packet_gyro)
            heading.append(packet_heading)

    duration = time[-1] - time[0]
    yaw_travel_deg = math.degrees(math.fsum(travel))
    return dict(heading_error_rad=heading_errors, gyro_increment_rad=gyro_increments, seeds=seeds, signs=SIGNS,
                equivalent_bias_deg_per_s={name: k * yaw_travel_deg / duration for name, k in TB3_SCALE.items()},
                elapsed_duration_s=duration, angular_travel_deg=yaw_travel_deg, hold_duration_s=math.fsum(hold_time))


def self_check():
    """Exercise signs and shared noise, absolute turn, hold, restart and wrapping."""
    rows = [
        dict(case="synthetic", stream=stream, stream_sequence=i, t_s=t, truth_yaw_deg=yaw,
             abs_yaw_increment_deg=travel, distance_increment_m=d, motion=mode)
        for stream, i, t, yaw, travel, d, mode in (
            ("TEACH", 0, 0.0, 170.0, 0.0, 0.0, "start"),
            ("TEACH", 1, 0.2, -170.0, 20.0, 0.0, "sweep"),
            ("TEACH", 2, 0.4, -175.0, 7.0, 0.0, "sweep"),
            ("TEACH", 3, 0.6, -175.0, 0.0, 0.0, "hold"),
            ("REPEAT", 0, 0.8, 0.0, 0.0, 0.0, "align"),
            ("REPEAT", 1, 1.0, 0.0, 0.0, 0.016, "straight"),
        )
    ]
    geometry = geometry_from_rows(rows)
    result = generate_motion(**geometry, path_id="synthetic")
    if result != generate_motion(**geometry, path_id="synthetic"):
        raise AssertionError("Motion replay changed for identical path and seeds")
    assert result["seeds"] == DEFAULT_SEEDS and result["signs"] == SIGNS
    assert geometry["motion"][4] == "restart" and geometry["distance_increment_m"][4] == 0.0

    def near(actual, expected):
        if not math.isclose(actual, expected, abs_tol=1e-12, rel_tol=0):
            raise AssertionError((actual, expected))

    def split(pair):
        return (pair[1] + pair[0]) / 2.0, (pair[1] - pair[0]) / 2.0

    for i, expected in enumerate((0, 20, -5, 0, 0, 0)):
        near(math.degrees(geometry["signed_yaw_increment_rad"][i]), expected)
    for seed_index in range(len(result["seeds"])):
        heading = result["heading_error_rad"]
        b0 = heading["B0"][-1][seed_index]
        near(b0[0], b0[1])
        for level, rate in BIAS_DEG_PER_S.items():
            center, spread = split(heading[level][-1][seed_index])
            near(center, b0[0])
            near(math.degrees(spread), rate)
        for name, scale in TB3_SCALE.items():
            center, spread = split(heading[name][-1][seed_index])
            near(center, b0[0])
            near(math.degrees(spread), scale * 27 + 0.2 * TB3_HOLD_DRIFT_DEG_PER_S)
            near(result["equivalent_bias_deg_per_s"][name], scale * 27)
            near(split(result["gyro_increment_rad"][name][4][seed_index])[1], 0.0)
            near(split(heading[name][4][seed_index])[1], split(heading[name][3][seed_index])[1])
    if generate_motion(**geometry, path_id="other_path")["heading_error_rad"]["B0"] == result["heading_error_rad"]["B0"]:
        raise AssertionError("Distinct path identifiers produced identical white noise")

    wrapped = generate_motion([0, 1000], [0, 0], [0, 0], ["start", "hold"], path_id="wrap", seeds=[5])
    common = wrapped["heading_error_rad"]["B0"][1][0][0]
    for sign, value in zip(SIGNS, wrapped["heading_error_rad"]["L2"][1][0], strict=True):
        near(value, _wrap(common + sign * math.radians(200)))
    return dict(status="PASS", seed_count=len(DEFAULT_SEEDS), signs=SIGNS,
                turn_travel_deg=result["angular_travel_deg"], hold_duration_s=result["hold_duration_s"],
                equivalent_bias_deg_per_s=result["equivalent_bias_deg_per_s"])


if __name__ == "__main__":
    print(json.dumps(self_check(), indent=2, allow_nan=False))
