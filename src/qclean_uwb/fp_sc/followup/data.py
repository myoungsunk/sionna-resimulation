"""Canonical payload adapter and optional, lossless archived-input export.

Exports perform joins/format checks only, no selector/filter/RT execution.
All input paths must be SHA-locked, all output directories must be new.
"""
from __future__ import annotations
from pathlib import Path
import json
import numpy as np
from .contracts import ContractError, rooted, sha256, verify_files, write_json
from .engine import OnlineCase
from .study import Evaluator

ONLINE_ARRAYS = ("Hrf", "t", "pose_id", "ds", "gy", "dt", "x0", "P0", "z", "muMB", "muBASE",
                 "R", "D", "prior", "Pprior")
TRACE_FIELDS = ("h", "H", "prior", "Pprior", "Reff", "K", "mask")
META = ("case_id", "route", "bias", "channel", "sensor_seed", "split", "noise_variance", "corpus", "environment_id")


def npz(path: Path) -> dict:
    with np.load(path, allow_pickle=False) as z:
        return {name: z[name] for name in z.files}


def _locked(root: Path, relative: str, lock: dict) -> Path:
    if relative not in lock:
        raise ContractError(f"PATH_ABSENT_FROM_INPUT_LOCK:{relative}")
    return rooted(root, relative)


def load_case(root: Path, spec: dict, input_lock: dict, adapter, *, detection_only=False):
    required = {"online_npz", "evaluator_npz", "expected_rows", "metadata"}
    if set(spec) != required:
        raise ContractError(f"CASE_SPEC_KEYS_MISMATCH:{set(spec)^required}")
    data = npz(_locked(root, spec["online_npz"], input_lock))
    truth = npz(_locked(root, spec["evaluator_npz"], input_lock))
    if set(spec["metadata"]) != set(META):
        raise ContractError("CASE_METADATA_KEYS_MISMATCH")
    if any(name not in data for name in ONLINE_ARRAYS):
        raise ContractError("CANONICAL_ONLINE_FIELD_MISSING")
    if len(data["t"]) != spec["expected_rows"]:
        raise ContractError("CANONICAL_CASE_ROWCOUNT_MISMATCH")
    for field in ("pose_id", "t"):
        if not np.array_equal(data[field], truth[field]):
            raise ContractError("EVALUATOR_JOIN_MISMATCH:"+field)
    extra = set(data)-set(ONLINE_ARRAYS)-{"trace_"+k for k in TRACE_FIELDS}-{"clean_Hrf"}
    if extra:
        raise ContractError("UNEXPECTED_ONLINE_ARRAYS:"+str(sorted(extra)))
    trace = {k: data["trace_"+k] for k in TRACE_FIELDS} if all("trace_"+k in data for k in TRACE_FIELDS) else None
    case = OnlineCase(**spec["metadata"], **{k: data[k] for k in ONLINE_ARRAYS},
                      baseline_trace=trace, clean_Hrf=data.get("clean_Hrf"))
    return case, Evaluator(case, truth["clean_H"], truth["truth"], adapter, detection_only=detection_only)


def export_archive(root: Path, spec: dict, output: Path) -> dict:
    """Materialize an explicitly registered old dataset into the new interface.

    Required source fields: packet, controls, trace, truth, full_H, los_H,
    frequencies, each mapping to a locked repo-relative path. For 3-state
    truth a registered true_gyro_bias array is required; no bias is guessed.
    """
    required = {"packet", "controls", "trace", "truth", "full_H", "los_H", "frequencies"}
    if set(spec["sources"]) != required or spec.get("control_origin") not in {"EXACT_ARCHIVE", "A2_REMATERIALIZED", "NEW_RECIPE_REALIZATION"}:
        raise ContractError("EXPORT_SOURCE_OR_CONTROL_PROVENANCE_MISSING")
    verify_files(root, spec["input_files"])
    paths = {k: _locked(root, p, spec["input_files"]) for k, p in spec["sources"].items()}
    packet, controls, trace, truth = (npz(paths[k]) for k in ("packet", "controls", "trace", "truth"))
    ids, t = packet["pose_id"], packet["t"]
    if ids.dtype.kind not in "iu" or len(set(ids.tolist())) != len(ids):
        raise ContractError("EXPORT_INVALID_IDS")
    for other in (trace, truth):
        if any(not np.array_equal(packet[k], other[k]) for k in ("pose_id", "t")):
            raise ContractError("EXPORT_SOURCE_JOIN_MISMATCH")
    frequencies = np.load(paths["frequencies"], allow_pickle=False)
    if not np.array_equal(frequencies, 6250400000.+1950000.*np.arange(257)):
        raise ContractError("EXPORT_FREQUENCY_GRID_MISMATCH")
    rf = {}
    for key in ("full_H", "los_H"):
        a = np.load(paths[key], mmap_mode="r", allow_pickle=False)
        if a.ndim != 4 or a.shape[1:3] != (257, 2) or a.shape[3] < 1 or ids.min() < 0 or ids.max() >= len(a):
            raise ContractError("EXPORT_RF_AXES_OR_POSE_ID_OUT_OF_RANGE")
        rf[key] = np.asarray(a[ids, :, :, 0])
    H = rf["full_H"] if spec["metadata"]["channel"] == "Full" else rf["los_H"]
    initial = controls["x0"]
    if initial.shape == (3,):
        initial = np.r_[initial, 0.]  # original estimated bias initialization, NOT GT.
    state_truth = truth["truth"]
    detection_only = spec.get('detection_only') is True
    if state_truth.shape == (len(t), 3) and not detection_only:
        if "true_gyro_bias" not in truth or truth["true_gyro_bias"].shape != (len(t),):
            raise ContractError("TRUTH_GYRO_BIAS_REQUIRED_FOR_4D_NEES")
        state_truth = np.column_stack((state_truth, truth["true_gyro_bias"]))
    online = dict(Hrf=H, clean_Hrf=H.copy(), t=t, pose_id=ids, x0=initial,
                  **{k: controls[k] for k in ("ds", "gy", "dt")},
                  **{k: packet[k] for k in ("P0", "z", "muMB", "muBASE", "R", "D")},
                  prior=trace["prior"], Pprior=trace["Pprior"],
                  **{"trace_"+k: trace[k] for k in TRACE_FIELDS})
    # Validate structure without loading any FFD observer or calculating a waveform.
    OnlineCase(**spec["metadata"], **{k: online[k] for k in ONLINE_ARRAYS},
               baseline_trace={k: trace[k] for k in TRACE_FIELDS}, clean_Hrf=H)
    allowed_truth = {(len(t), 4), (len(t), 3)} if detection_only else {(len(t), 4)}
    if state_truth.shape not in allowed_truth or not np.isfinite(state_truth).all():
        raise ContractError("EXPORT_TRUTH_SCHEMA")
    output.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(output/"online.npz", **online)
    np.savez_compressed(output/"evaluator.npz", clean_H=rf["los_H"], truth=state_truth, t=t, pose_id=ids)
    receipt = dict(status="FORMAT_EXPORT_ONLY_NO_SCIENCE", source_files=spec["input_files"],
                   source_metadata=spec["metadata"], control_origin=spec["control_origin"],
                   rows=len(t), detection_only=detection_only,
                   truth_columns=state_truth.shape[1], gyro_bias_not_invented=True,
                   arrays_unchanged_except_axis_selection_and_estimated_bias_initialization=True,
                   files={p.name: sha256(p) for p in output.iterdir() if p.is_file()})
    write_json(output/"EXPORT_RECEIPT.json", receipt)
    return receipt


def load_shadow_online_only(root: Path, spec: dict, input_lock: dict) -> OnlineCase:
    """Stage S1/S3 loader: no evaluator/GT/LoS file is opened or materialized."""
    if set(spec) != {"online_npz", "evaluator_npz", "expected_rows", "metadata"}:
        raise ContractError("SHADOW_CASE_SPEC_KEYS")
    rel = spec["online_npz"]
    verify_files(root, {rel: input_lock[rel]})
    values = npz(_locked(root, rel, input_lock))
    if set(spec["metadata"]) != set(META):
        raise ContractError("SHADOW_CASE_META_KEYS")
    if any(key not in values for key in ONLINE_ARRAYS):
        raise ContractError("SHADOW_ONLINE_REQUIRED_FIELDS")
    if len(values["t"]) != spec["expected_rows"]:
        raise ContractError("SHADOW_ONLINE_ROWCOUNT")
    extra = set(values)-set(ONLINE_ARRAYS)-{"trace_"+k for k in TRACE_FIELDS}-{"clean_Hrf"}
    if extra:
        raise ContractError("SHADOW_ONLINE_UNKNOWN_FIELDS:"+str(sorted(extra)))
    trace = {k:values["trace_"+k] for k in TRACE_FIELDS} if all(
        "trace_"+k in values for k in TRACE_FIELDS) else None
    return OnlineCase(**spec["metadata"], **{k:values[k] for k in ONLINE_ARRAYS},
                      baseline_trace=trace, clean_Hrf=values.get("clean_Hrf"))


def load_shadow_reference_after_s1(root: Path, spec: dict, input_lock: dict,
                                  *, expected_t: np.ndarray, expected_pose: np.ndarray) -> np.ndarray:
    """S2-only evaluator access; exact time/pose join and SHA-locked payload."""
    rel=spec["evaluator_npz"]
    verify_files(root,{rel:input_lock[rel]})
    value=npz(_locked(root,rel,input_lock))
    if not {"clean_H","t","pose_id"} <= set(value):
        raise ContractError("SHADOW_EVALUATOR_FIELDS")
    if not (np.array_equal(value["t"],expected_t) and
            np.array_equal(value["pose_id"],expected_pose)):
        raise ContractError("SHADOW_EVALUATOR_JOIN_MISMATCH")
    clean=value["clean_H"]
    if clean.shape != (len(expected_t),257,2) or not np.iscomplexobj(clean) or not np.isfinite(clean).all():
        raise ContractError("SHADOW_EVALUATOR_INVALID_CFR")
    return clean
