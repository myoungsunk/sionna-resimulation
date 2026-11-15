"""Export the near-delay contributions from the same Method B trace used for H."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from qclean_uwb.drivesim import pattern_apply
from qclean_uwb.scenarios.corridor import ANCHOR_ROTATION, rot_z


C_M_S = 299792458.0
G8_RELATIVE_LIMIT = 1e-6


def tap_seconds(frequencies_hz):
    """Exact CIR tap spacing of the frozen Hann IFFT with 4× zero padding."""
    frequencies = np.asarray(frequencies_hz, dtype=np.float64)
    if frequencies.ndim != 1 or len(frequencies) < 2 or not np.isfinite(frequencies).all():
        raise ValueError("Invalid RF frequency grid")
    steps = np.diff(frequencies)
    if steps[0] <= 0 or not np.all(np.abs(steps - steps[0]) < 1e-3):
        raise ValueError("RF frequency grid must increase uniformly")
    return 1.0 / (4 * len(frequencies) * steps[0])


def h_and_near_for_poses(
    trace, banks, poses, *, mount_deg=0.0, none_event=0, export_pose_ids=None,
    direct_coefficients=None,
):
    """Return conventional full H and near-path rows for one already-traced XY.

    The trace's interaction and object arrays are indexed by the canonical
    Method B path order along their first axis. Every supplied pose produces
    full H, and only export_pose_ids (all poses by default) get path rows.
    """
    if trace["status"] != "OK":
        raise ValueError(f"Unusable Method B trace: {trace['status']}")
    if len(banks) != 2 or not np.array_equal(banks[1].freqs_hz, banks[0].freqs_hz):
        raise ValueError("Expected both frozen LP port banks on one grid")
    freqs = np.asarray(banks[0].freqs_hz, dtype=np.float64)
    tap_s = tap_seconds(freqs)
    tau = np.asarray(trace["tau"], dtype=np.float64)
    angles = np.asarray(trace["ang"], dtype=np.float64)
    events = np.asarray(trace["interactions"])
    objects = np.asarray(trace["objects"])
    if (tau.ndim != 1 or angles.shape != (4, len(tau)) or events.ndim != 2
            or events.shape[0] != len(tau) or objects.shape != events.shape
            or not np.isfinite(tau).all() or not np.isfinite(angles).all() or np.any(tau < 0)):
        raise ValueError("Invalid canonical path geometry or interaction metadata")
    interaction_count = np.count_nonzero(events != none_event, axis=1)
    los = np.flatnonzero(interaction_count == 0)
    if len(los) != 1:
        raise ValueError("A direct LoS path is required and must be unique")

    # The 002 interval is closed. Use the exact frozen grid spacing and the
    # recorded float64 tau rather than rounding the distance cutoff to 0.299 m.
    tau_los = tau[los[0]]
    near = np.flatnonzero((tau >= tau_los) & (tau <= tau_los + 2 * tap_s))
    jones = pattern_apply.interp_jones(
        trace["jones"], trace["node_freq_hz"], freqs, present=trace.get("present"),
    )
    if jones.shape != (len(freqs), len(tau), 3, 3) or not np.isfinite(jones).all():
        raise ValueError("Invalid Method B Jones coefficients")
    theta_t, phi_t, theta_r, phi_r = angles
    tx_fields = np.stack([pattern_apply.field_world(bank, ANCHOR_ROTATION, theta_t, phi_t) for bank in banks])
    tx_near = tx_fields[:, :, near, :]
    jones_near = jones[:, near, :, :]
    pose_ids = np.array([pose["pose_id"] for pose in poses], dtype=np.int64)
    if len(pose_ids) == 0 or len(np.unique(pose_ids)) != len(pose_ids):
        raise ValueError("Expected unique pose IDs at the traced XY")
    if direct_coefficients is not None and (
        direct_coefficients.shape != (len(poses), len(freqs), 2, 2)
        or not np.isfinite(direct_coefficients).all()
    ):
        raise ValueError("Invalid native LoS port coefficients")
    selected_ids = set(pose_ids.tolist()) if export_pose_ids is None else set(export_pose_ids)
    if not selected_ids.issubset(pose_ids.tolist()):
        raise ValueError("An export pose ID does not belong to the traced XY")

    full = []
    coefficients = []
    exported = []
    phase = np.exp(-2j * np.pi * freqs[:, None] * tau[None, :])
    for index, pose in enumerate(poses):
        rotation = rot_z(float(pose["yaw_body_deg"] + mount_deg))
        rx_fields = np.stack([pattern_apply.field_world(bank, rotation, theta_r, phi_r) for bank in banks])
        if direct_coefficients is None:
            full.append(pattern_apply.channel_from_jones(jones, tau, freqs, rx_fields, tx_fields))
        else:
            # The LoS port evaluation and all reflected Method B contributions
            # are combined before the same array is used for H and export.
            per_path = np.einsum("rbni,bnij,tbnj->brtn", rx_fields, jones, tx_fields)
            per_path[..., los[0]] = direct_coefficients[index]
            full.append(np.einsum("brtn,bn->brt", per_path, phase))
        if pose["pose_id"] not in selected_ids:
            continue
        # Same contraction (and axis order) as channel_from_jones, before
        # applying the explicitly stored propagation phase for each path.
        if direct_coefficients is None:
            path_coefficients = np.einsum("rbni,bnij,tbnj->brtn", rx_fields[:, :, near, :], jones_near, tx_near)
        else:
            path_coefficients = per_path[..., near]
        coefficients.append(np.moveaxis(path_coefficients, -1, 0))
        exported.append(pose["pose_id"])
    full = np.stack(full)
    coefficients = np.concatenate(coefficients, axis=0) if coefficients else np.empty((0, len(freqs), 2, 2), complex)
    if not np.isfinite(full).all() or not np.isfinite(coefficients).all():
        raise ValueError("Nonfinite Method B channel or exported coefficient")
    near_aod = np.stack([phi_t[near], np.pi / 2 - theta_t[near]], axis=1)
    near_aoa = np.stack([phi_r[near], np.pi / 2 - theta_r[near]], axis=1)
    exported_count = len(exported)
    rows = dict(
        pose_id=np.repeat(np.asarray(exported, dtype=np.int64), len(near)),
        path_index=np.tile(near, exported_count),
        tau_s=np.tile(tau[near], exported_count),
        delay_m=np.tile(C_M_S * tau[near], exported_count),
        coefficients=coefficients,
        interaction_count=np.tile(interaction_count[near], exported_count),
        interactions=np.tile(events[near], (exported_count, 1)),
        objects=np.tile(objects[near], (exported_count, 1)),
        aod_az_el_rad=np.tile(near_aod, (exported_count, 1)),
        aoa_az_el_rad=np.tile(near_aoa, (exported_count, 1)),
        is_los=np.tile(near == los[0], exported_count),
    )
    return full, rows


def write_paths_near(directory, packs, frequencies_hz, interaction_codes, *, object_ids=None,
                     native_direct=False):
    """Write case-level PATHS_NEAR.npz and its schema from per-XY row packs."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    packs = list(packs)
    if not packs:
        raise ValueError("Expected at least one nonempty PATHS_NEAR pack")
    data = {field: np.concatenate([pack[field] for pack in packs]) for field in packs[0]}
    freqs = np.asarray(frequencies_hz, dtype=np.float64)
    tap_s = tap_seconds(freqs)
    if data["coefficients"].shape != (len(data["pose_id"]), len(freqs), 2, 2):
        raise ValueError("PATHS_NEAR coefficient shape differs from frequency and pose/path axes")
    path = directory / "PATHS_NEAR.npz"
    with path.open("xb") as stream:
        np.savez_compressed(stream, frequencies_hz=freqs, **data)
    schema = dict(
        schema_version=1,
        question_id="G1-RT-TB3-002",
        frequency_source="frozen Method B LP FFD bank",
        direct_coefficient_source=(
            "native Sionna LP field operations on the LoS segment found by F1"
            if native_direct else "frozen Method B path Jones and LP fields"
        ),
        near_interval_s="[tau_LoS, tau_LoS + 2 * tap_seconds], both endpoints included",
        tap_seconds=tap_s,
        near_width_m=2 * tap_s * C_M_S,
        propagation_speed_m_s=C_M_S,
        coefficient_axes=["pose_path_row", "frequency_bin", "rx_port", "tx_port"],
        rx_ports_deg=[45, -45],
        tx_ports_deg=[45, -45],
        channel_reconstruction="sum_p coefficients[p] * exp(-2*pi*j*frequencies_hz*tau_s[p])",
        fields=dict(
            pose_id="Physical pose identifier from the case pose table",
            path_index="Zero-based path index in the canonical trace for the pose's XY",
            tau_s="Float64 propagation delay in seconds used to reconstruct phase",
            delay_m="Propagation path length in meters, tau_s times c",
            coefficients="Complex end-to-end LP port coefficients at each H bin, before propagation phase",
            interaction_count="Number of non-padding events",
            interactions="Ordered solver interaction codes, padded to max_depth with NONE",
            objects="Ordered solver object IDs; entries with interaction NONE are padding",
            aod_az_el_rad="World-frame departure azimuth and elevation in radians",
            aoa_az_el_rad="World-frame arrival azimuth and elevation in radians",
            is_los="True for the unique path without interactions",
            frequencies_hz="Strictly increasing frequency grid in H bin order",
        ),
        interaction_codes=interaction_codes,
        object_ids=object_ids,
    )
    with (directory / "PATHS_NEAR_SCHEMA.json").open("x", encoding="utf-8") as stream:
        json.dump(schema, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return path


def check_g8(npz_path, h_los, pose_ids):
    """Reload PATHS_NEAR, resynthesize LoS, and compare every complex H_LoS entry."""
    ids = np.asarray(pose_ids, dtype=np.int64)
    h_los = np.asarray(h_los)
    if ids.ndim != 1 or len(ids) == 0 or len(np.unique(ids)) != len(ids):
        raise ValueError("Expected unique H_LoS pose IDs")
    with np.load(npz_path, allow_pickle=False) as data:
        freqs = data["frequencies_hz"]
        stored_ids = data["pose_id"]
        mask = data["is_los"]
        tau = data["tau_s"]
        coefficients = data["coefficients"]
    if (mask.shape != stored_ids.shape or mask.dtype != np.bool_ or tau.shape != stored_ids.shape
            or coefficients.shape != (len(stored_ids), len(freqs), 2, 2)
            or h_los.shape != (len(ids), len(freqs), 2, 2)
            or not np.isfinite(h_los).all() or not np.isfinite(tau).all()
            or not np.isfinite(coefficients).all()):
        raise ValueError("Invalid serialized near paths or H_LoS")
    unique_ids, counts = np.unique(stored_ids, return_counts=True)
    los_ids = stored_ids[mask]
    if not np.array_equal(unique_ids, np.sort(ids)) or not np.array_equal(np.sort(los_ids), unique_ids):
        raise ValueError("PATHS_NEAR must contain exactly one LoS row per expected pose")
    index_by_pose = dict(zip(los_ids.tolist(), np.flatnonzero(mask).tolist(), strict=True))
    indices = np.array([index_by_pose[pose_id] for pose_id in ids], dtype=np.int64)
    phase = np.exp(-2j * np.pi * freqs[None, :] * tau[indices, None])
    reconstructed = coefficients[indices] * phase[..., None, None]
    absolute = np.abs(reconstructed - h_los)
    reference = np.abs(h_los)
    relative = np.zeros_like(reference)
    np.divide(absolute, reference, out=relative, where=reference != 0)
    zero_mismatches = int(np.count_nonzero((reference == 0) & (absolute != 0)))
    peak_idx = np.unravel_index(relative.argmax(), relative.shape)
    max_relative = float(relative[peak_idx])
    finite = bool(np.isfinite(relative).all())
    key = dict(pose_id=int(ids[peak_idx[0]]), bin=int(peak_idx[1]),
               rx_port_index=int(peak_idx[2]), tx_port_index=int(peak_idx[3]))
    values, frequencies = np.unique(counts, return_counts=True)
    return dict(
        status="PASS" if finite and not zero_mismatches and max_relative < G8_RELATIVE_LIMIT else "FAIL",
        expected_pose_count=len(ids),
        validated_pose_count=len(los_ids),
        complex_entries=int(h_los.size),
        max_relative_error=max_relative if finite and not zero_mismatches else None,
        max_absolute_error=float(absolute.max()),
        worst_index=key if finite else None,
        zero_reference_mismatches=zero_mismatches,
        strict_relative_limit=G8_RELATIVE_LIMIT,
        near_count_histogram={str(value): int(count) for value, count in zip(values, frequencies, strict=True)},
        near_path_rows=int(len(stored_ids)),
    )
