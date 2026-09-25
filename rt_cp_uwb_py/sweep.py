from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .channel import build_channel
from .config import RtConfig, default_config
from .core import C0, Material, PathRecord, Surface, make_ideal_cp_antenna, make_ideal_lp_antenna, normalize
from .antennas import make_realistic_lp_antenna_ffd, make_realistic_patch_antenna_ffd
from .features import compute_rh_lh_cp16, extract_all_features
from .matlab_rng import matlab_mt19937_randn
from .materials import materials_library
from .scenes import make_room_abc_scene, make_single_slab_scene
from .trace import enumerate_paths


def _axis_angle_rotation(axis: np.ndarray, angle_rad: float) -> np.ndarray:
    a = normalize(np.asarray(axis, dtype=float).reshape(3))
    x, y, z = a
    K = np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]])
    return np.eye(3) + np.sin(angle_rad) * K + (1.0 - np.cos(angle_rad)) * (K @ K)


def _normalize_numeric(value: Any) -> int:
    try:
        if value is None or not np.isfinite(float(value)):
            return 0
        raw = int(round(float(value)))
    except Exception:
        return 0
    mod = 2**32 - 1
    seed = raw % mod
    if seed == 0 and raw != 0:
        seed = 1
    return int(seed)


def _hash_token(token: Any) -> int:
    if isinstance(token, (int, float, np.integer, np.floating)):
        return _normalize_numeric(token)
    txt = "|".join(str(x) for x in np.atleast_1d(token))
    if not txt:
        return 0
    value = 2166136261
    for b in txt.encode("utf-8"):
        value ^= b
        value = (value * 16777619) % (2**32 - 1)
    return value or 1


def compose_case_seed(case_id: Any, stage_id: Any = "", base_seed: Any = 0, replicate_id: Any = 0, component: Any = "") -> int:
    stage = str(stage_id or "")
    base = _normalize_numeric(base_seed)
    rep = _normalize_numeric(replicate_id)
    case_seed = _normalize_numeric(case_id)
    if not stage and base == 0 and rep == 0:
        return case_seed
    seed = 2166136261
    for word in [base, case_seed, rep, _hash_token(stage), _hash_token(component)]:
        seed ^= int(word)
        seed = (seed * 16777619) % (2**32 - 1)
        if seed == 0:
            seed = 1
    return int(seed)


def inject_snr(H: np.ndarray, snr_db: float | None, seed: int) -> np.ndarray:
    if snr_db is None or not np.isfinite(float(snr_db)):
        return H
    snr = float(snr_db)
    if snr >= 200:
        return H
    signal_power = float(np.mean(np.abs(H) ** 2))
    if signal_power <= 0:
        return H
    noise_power = signal_power / (10.0 ** (snr / 10.0))
    # Match +sweep/injectSnr.m: two consecutive MATLAB randn(stream, size(H))
    # calls from a local RandStream('mt19937ar') stream.
    shape = tuple(H.shape)
    n = int(np.prod(shape))
    noise_flat = matlab_mt19937_randn(seed, 2 * n)
    noise_real = noise_flat[:n].reshape(shape, order="F")
    noise_imag = noise_flat[n:].reshape(shape, order="F")
    noise = (noise_real + 1j * noise_imag) * np.sqrt(noise_power / 2.0)
    return H + noise


def _row_get(row: dict, key: str, default=None):
    val = row.get(key, default)
    if isinstance(val, float) and np.isnan(val):
        return default
    return val


def _row_index_hint(row: dict, key: str):
    val = _row_get(row, key, None)
    try:
        raw = float(val)
    except (TypeError, ValueError):
        return None
    return raw if np.isfinite(raw) and raw >= 1 else None


def _case_seed(row: dict, cfg: RtConfig, component: str) -> int:
    replicate_id = cfg.seed_replicate_id
    row_replicate = _row_get(row, "replicate_id", None)
    if row_replicate is not None:
        try:
            if np.isfinite(float(row_replicate)):
                replicate_id = row_replicate
        except Exception:
            pass

    stage_id = cfg.seed_stage_id
    row_stage = _row_get(row, "stage_id", None)
    if row_stage not in (None, ""):
        stage_id = row_stage

    base_seed = cfg.seed_base
    row_base = _row_get(row, "base_seed", None)
    if row_base is not None:
        try:
            if np.isfinite(float(row_base)):
                base_seed = row_base
        except Exception:
            pass

    return compose_case_seed(
        _row_get(row, "seed_case_id", _row_get(row, "case_id", 1)),
        stage_id,
        base_seed,
        replicate_id,
        component,
    )


def _material_from_row(row: dict) -> Material:
    kind = str(_row_get(row, "material_kind", _row_get(row, "kind", "dielectric")))
    name = str(_row_get(row, "dominant_wall_material", _row_get(row, "dominant_wall_material_cases_tbl", _row_get(row, "material_name", _row_get(row, "material", kind)))))
    eps_mult = float(_row_get(row, "eps_r_multiplier", _row_get(row, "eps_r_multiplier_cases_tbl", _row_get(row, "eps_r_multiplier_results_tbl", 1.0))))
    lib = materials_library()
    base = lib.get(name.lower(), Material(name=name, kind=kind, eps_r=4.0, tan_delta=0.01))
    return Material(
        name=name,
        kind=kind,
        eps_r=float(_row_get(row, "eps_r", _row_get(row, "eps_r_base", base.eps_r))) * eps_mult,
        tan_delta=float(_row_get(row, "tan_delta", base.tan_delta)),
        xpol_coupling_db=float(_row_get(row, "xpol_coupling_db", 35.0)),
    )


def _copy_material_with_overrides(mat: Material, eps_mult: float, xpol_db: float) -> Material:
    if mat.kind.lower() == "pec":
        return Material(
            name=mat.name,
            kind=mat.kind,
            pec_tm_sign=mat.pec_tm_sign,
            xpol_coupling_db=xpol_db,
            xpol_coupling_phase_deg=mat.xpol_coupling_phase_deg,
        )
    return Material(
        name=mat.name,
        kind=mat.kind,
        eps_r=max(1.0, float(mat.eps_r) * float(eps_mult)),
        tan_delta=mat.tan_delta,
        conductivity_s_m=mat.conductivity_s_m,
        xpol_coupling_db=xpol_db,
        xpol_coupling_phase_deg=mat.xpol_coupling_phase_deg,
        xpol_coupling_hv_db=mat.xpol_coupling_hv_db,
        xpol_coupling_hv_phase_deg=mat.xpol_coupling_hv_phase_deg,
        xpol_coupling_vh_db=mat.xpol_coupling_vh_db,
        xpol_coupling_vh_phase_deg=mat.xpol_coupling_vh_phase_deg,
    )


def _safe_normalize(vec: np.ndarray, fallback: np.ndarray) -> np.ndarray:
    try:
        return normalize(vec)
    except ValueError:
        return normalize(fallback)


EXPLICIT_CONDITION_GEOMETRY_MODES = {
    "explicit",
    "explicit_rt_surfaces_v1",
    "rt_condition_surfaces_v1",
    "explicit_rt_surfaces_v2",
    "explicit_rt_surfaces_v2_required",
    "rt_condition_surfaces_v2",
}


def _parse_xyz_field(value: Any) -> np.ndarray | None:
    try:
        parts = str(value).split(";")
        vals = [float(p) for p in parts[:3]]
    except Exception:
        return None
    if len(vals) != 3 or not all(np.isfinite(v) for v in vals):
        return None
    return np.asarray(vals, dtype=float)


def _condition_surface_name(row: dict, condition: str) -> str:
    explicit = str(_row_get(row, "rt_surface_names", "")).strip()
    if explicit and explicit.lower() not in {"nan", "none"}:
        return explicit if explicit.startswith("condition_") else f"condition_{explicit}"
    return f"condition_{condition}_panel"


def _condition_material(row: dict, condition: str) -> Material:
    lib = materials_library()
    material_id = str(_row_get(row, "rt_material_id", "")).strip().lower()
    if condition in {"metal_near", "side_reflector"} or material_id in {"pec_metal", "metal", "metal_pec"}:
        return lib["metal_pec"]
    if condition == "blockage" or material_id in {"lossy_blocker", "blocker", "blockage_panel"}:
        return Material(name="blockage_panel", eps_r=12.0, tan_delta=0.35, xpol_coupling_db=22.0)
    return lib["metal_pec"]


def _condition_normal(row: dict, fallback: np.ndarray) -> np.ndarray:
    axis = str(_row_get(row, "condition_object_normal_axis", "")).strip().lower()
    if axis == "x":
        return np.array([1.0, 0.0, 0.0])
    if axis == "y":
        return np.array([0.0, 1.0, 0.0])
    if axis == "z":
        return np.array([0.0, 0.0, 1.0])
    yaw_text = _row_get(row, "condition_object_yaw_deg", None)
    try:
        yaw = np.deg2rad(float(yaw_text))
    except Exception:
        yaw = None
    if yaw is not None and np.isfinite(yaw):
        return _safe_normalize(np.array([np.cos(yaw), np.sin(yaw), 0.0]), fallback)
    return fallback


def _condition_rect(
    surface_id: int,
    name: str,
    center: np.ndarray,
    normal: np.ndarray,
    half_u: float,
    half_v: float,
    material: Material,
) -> Surface:
    n = _safe_normalize(normal, np.array([1.0, 0.0, 0.0]))
    up = np.array([0.0, 0.0, 1.0])
    u = up - float(np.dot(up, n)) * n
    if np.linalg.norm(u) < 1e-8:
        u = np.array([0.0, 1.0, 0.0])
    return Surface(
        surface_id=surface_id,
        name=name,
        point=np.asarray(center, dtype=float).reshape(3),
        normal=n,
        u_axis=u,
        v_axis=np.cross(n, u),
        half_u=float(half_u),
        half_v=float(half_v),
        material=material,
    )


def _append_condition_geometry_v2(scene, row: dict, condition: str, next_id: int, fallback_normal: np.ndarray):
    center = _parse_xyz_field(_row_get(row, "condition_object_pose_xyz", ""))
    if center is None:
        return None
    bounds_valid = str(_row_get(row, "condition_object_bounds_valid", "true")).strip().lower()
    if bounds_valid in {"0", "false", "f", "no", "n"}:
        return None
    default_width = 0.8 if condition == "blockage" else 1.2
    default_height = 1.7 if condition == "blockage" else 1.5
    width = float(_row_get(row, "condition_object_width_m", default_width))
    height = float(_row_get(row, "condition_object_height_m", default_height))
    return _condition_rect(
        next_id,
        _condition_surface_name(row, condition),
        center,
        _condition_normal(row, fallback_normal),
        max(0.25, height / 2.0),
        max(0.20, width / 2.0),
        _condition_material(row, condition),
    )


def _append_condition_geometry(scene, row: dict, tx_pos: np.ndarray, rx_pos: np.ndarray):
    mode = str(_row_get(row, "condition_geometry_mode", "")).lower()
    if mode not in EXPLICIT_CONDITION_GEOMETRY_MODES:
        return scene

    condition = str(_row_get(row, "condition_id", "")).strip().lower().replace(" ", "_")
    if condition in {"", "clean", "none", "nan"}:
        return scene

    lib = materials_library()
    tx = np.asarray(tx_pos, dtype=float).reshape(3)
    rx = np.asarray(rx_pos, dtype=float).reshape(3)
    los = _safe_normalize(rx - tx, np.array([1.0, 0.0, 0.0]))
    up = np.array([0.0, 0.0, 1.0])
    lateral = np.cross(los, up)
    if np.linalg.norm(lateral) < 1e-8:
        lateral = np.cross(los, np.array([0.0, 1.0, 0.0]))
    lateral = _safe_normalize(lateral, np.array([0.0, 1.0, 0.0]))
    midpoint = 0.5 * (tx + rx)
    next_id = max((int(s.surface_id) for s in scene.surfaces), default=0) + 1

    if mode in {"explicit_rt_surfaces_v2", "explicit_rt_surfaces_v2_required", "rt_condition_surfaces_v2"}:
        surface = _append_condition_geometry_v2(scene, row, condition, next_id, -lateral)
        if surface is not None:
            return scene.__class__(tuple(scene.surfaces) + (surface,))

    default_width = 0.5 if condition == "blockage" else 1.2
    default_height = 0.7 if condition == "blockage" else 1.5
    width = float(_row_get(row, "condition_object_width_m", default_width))
    height = float(_row_get(row, "condition_object_height_m", default_height))
    metal = lib["metal_pec"]
    blockage = Material(name="blockage_panel", eps_r=12.0, tan_delta=0.35, xpol_coupling_db=22.0)

    if condition == "blockage":
        surface = _condition_rect(
            next_id,
            "condition_blockage_panel",
            midpoint,
            los,
            max(0.3, height / 2.0),
            max(0.25, width / 2.0),
            blockage,
        )
    elif condition == "metal_near":
        center = tx + 0.72 * (rx - tx) + 0.42 * lateral
        surface = _condition_rect(
            next_id,
            "condition_metal_near_panel",
            center,
            -lateral,
            max(0.25, 0.55 * height / 2.0),
            max(0.20, 0.65 * width / 2.0),
            metal,
        )
    elif condition == "side_reflector":
        center = midpoint + 0.80 * lateral
        surface = _condition_rect(
            next_id,
            "condition_side_reflector_panel",
            center,
            -lateral,
            max(0.35, height / 2.0),
            max(0.35, width / 2.0),
            metal,
        )
    else:
        return scene

    return scene.__class__(tuple(scene.surfaces) + (surface,))


def _blockage_diffraction_proxy_path(scene, tx_pos: np.ndarray, rx_pos: np.ndarray) -> PathRecord | None:
    blockers = [s for s in scene.surfaces if str(s.name).startswith("condition_") and "blockage_panel" in str(s.name)]
    if not blockers:
        return None
    blocker = blockers[0]
    tx = np.asarray(tx_pos, dtype=float).reshape(3)
    rx = np.asarray(rx_pos, dtype=float).reshape(3)
    direct = rx - tx
    los = _safe_normalize(direct, np.array([1.0, 0.0, 0.0]))
    up = np.array([0.0, 0.0, 1.0])
    lateral = np.cross(los, up)
    if np.linalg.norm(lateral) < 1e-8:
        lateral = np.cross(los, np.array([0.0, 1.0, 0.0]))
    lateral = _safe_normalize(lateral, np.array([0.0, 1.0, 0.0]))
    via = blocker.point + lateral * (float(blocker.half_v) + 0.35)
    via = via + up * min(0.15, max(0.0, float(blocker.half_u)))
    length = float(np.linalg.norm(via - tx) + np.linalg.norm(rx - via))
    if not np.isfinite(length) or length <= 1e-9:
        return None
    return PathRecord(
        points=(tx, via, rx),
        surface_ids=(int(blocker.surface_id),),
        surface_names=("condition_blockage_diffraction_proxy",),
        materials=(blocker.material,),
        bounce_count=1,
        path_length_m=length,
        delay_s=length / C0,
        launch_dir=normalize(via - tx),
        arrival_dir=normalize(rx - via),
        incidence_angles_rad=(0.0,),
        normals=(blocker.normal,),
        blocked=False,
        valid=True,
    )


def _apply_stage2_room_variants(scene, row: dict):
    lib = materials_library()
    dominant_name = str(_row_get(row, "dominant_wall_material", _row_get(row, "dominant_wall_material_cases_tbl", "drywall"))).lower()
    dominant = lib.get(dominant_name, lib["drywall"])
    dominant_eps = _row_get(row, "dominant_wall_eps_r", _row_get(row, "dominant_wall_eps_r_cases_tbl", None))
    dominant_tan = _row_get(row, "dominant_wall_tan_delta", _row_get(row, "dominant_wall_tan_delta_cases_tbl", None))
    if dominant_eps is not None or dominant_tan is not None:
        dominant = Material(
            name=dominant.name,
            kind=dominant.kind,
            eps_r=float(dominant_eps) if dominant_eps is not None else dominant.eps_r,
            tan_delta=float(dominant_tan) if dominant_tan is not None else dominant.tan_delta,
            conductivity_s_m=dominant.conductivity_s_m,
            xpol_coupling_db=dominant.xpol_coupling_db,
            xpol_coupling_phase_deg=dominant.xpol_coupling_phase_deg,
            pec_tm_sign=dominant.pec_tm_sign,
        )
    eps_mult = float(_row_get(row, "eps_r_multiplier", _row_get(row, "eps_r_multiplier_cases_tbl", _row_get(row, "eps_r_multiplier_results_tbl", 1.0))))
    xpol_db = float(_row_get(row, "xpol_coupling_db", 30.0))
    surfaces = []
    for surf in scene.surfaces:
        base = dominant if str(surf.name).startswith("wall_") else surf.material
        surfaces.append(Surface(
            surface_id=surf.surface_id,
            name=surf.name,
            point=surf.point,
            normal=surf.normal,
            u_axis=surf.u_axis,
            v_axis=surf.v_axis,
            half_u=surf.half_u,
            half_v=surf.half_v,
            material=_copy_material_with_overrides(base, eps_mult, xpol_db),
        ))
    return scene.__class__(tuple(surfaces))


def _positions_from_row(row: dict) -> tuple[np.ndarray, np.ndarray]:
    tx_keys = ("tx_x_m", "tx_y_m", "tx_z_m")
    rx_keys = ("rx_x_m", "rx_y_m", "rx_z_m")
    if all(k in row for k in tx_keys + rx_keys):
        return np.array([float(row[k]) for k in tx_keys]), np.array([float(row[k]) for k in rx_keys])
    anchor_keys = ("anchor_x", "anchor_y", "anchor_z")
    tag_keys = ("tag_x", "tag_y", "tag_z")
    if all(k in row for k in anchor_keys + tag_keys):
        return np.array([float(row[k]) for k in anchor_keys]), np.array([float(row[k]) for k in tag_keys])
    dist = float(_row_get(row, "tx_rx_dist_m", _row_get(row, "distance_m", 3.0)))
    tx_slab = float(_row_get(row, "tx_slab_dist_m", 1.0))
    lateral = max(0.5, dist / 2.0)
    return np.array([-tx_slab, -lateral, 1.5]), np.array([-tx_slab, lateral, 1.5])


def _find_patch_ffd_paths() -> tuple[Path, Path] | None:
    root = Path(__file__).resolve().parents[1]
    candidates = [
        (root / "data" / "patch_patterns" / "patch_rhcp.ffd", root / "data" / "patch_patterns" / "patch_lhcp.ffd"),
        (root / "RHCP_new_6G7G_11pts.ffd", root / "LHCP_new_6G7G_11pts.ffd"),
    ]
    for rhcp, lhcp in candidates:
        if rhcp.exists() and lhcp.exists():
            return rhcp, lhcp
    return None


def _row_requests_cp_ffd(row: dict) -> bool:
    """Single definition of 'this row asked for the FFD antenna'.

    Shared by the antenna builder and the branch-convention resolver so the two
    cannot disagree about whether FFD is in use.
    """
    marker = " ".join(
        str(_row_get(row, key, ""))
        for key in ("antenna_type", "antenna_model", "antenna_model_status", "source_lineage")
    ).lower()
    return "patch_ffd" in marker or "full_ffd" in marker or "cp_rh_lh" in marker


def _make_cp_antenna_for_row(row: dict, position: np.ndarray, boresight: np.ndarray, h_axis: np.ndarray | None, handedness: str):
    if _row_requests_cp_ffd(row):
        paths = _find_patch_ffd_paths()
        if paths is None:
            # Previously this fell through to the ideal antenna with no warning,
            # while _cp_branch_convention_for_row kept returning the FFD
            # convention -- a result could claim an FFD antenna it never loaded.
            raise FileNotFoundError(
                "row requests the CP FFD antenna but no RHCP/LHCP pattern pair was "
                "found; searched data/patch_patterns/patch_{rhcp,lhcp}.ffd and "
                "{RHCP,LHCP}_new_6G7G_11pts.ffd under the project root. Refusing to "
                "substitute the ideal antenna silently."
            )
        return make_realistic_patch_antenna_ffd(position, boresight, paths[0], paths[1], h_axis=h_axis, handedness=handedness)
    return make_ideal_cp_antenna(position, boresight, h_axis=h_axis, handedness=handedness)


def antenna_provenance(*antennas) -> dict:
    """What was actually built, for the record.

    No shipped artifact used to state which antenna pattern a result rested on,
    so the claim could only be re-derived by re-running. This makes it reportable.
    """
    cfg_ = default_config()
    out: dict = {"use_ffd": [], "pattern_files": [],
                 "measured_pol_basis_deg": float(cfg_.measured_pol_basis_deg),
                 "measured_pol_basis_source": str(cfg_.measured_pol_basis_source)}
    for a in antennas:
        out["use_ffd"].append(bool(getattr(a, "use_ffd", False)))
        pd_ = getattr(a, "pattern_data", None) or {}
        out["pattern_files"].append(
            {k: str(v) for k, v in pd_.items() if str(k).endswith("_file")}
        )
    out["all_use_ffd"] = bool(out["use_ffd"]) and all(out["use_ffd"])
    return out


def _make_lp_antenna_for_row(row: dict, position: np.ndarray, boresight: np.ndarray, h_axis: np.ndarray | None):
    marker = " ".join(
        str(_row_get(row, key, ""))
        for key in ("lp_antenna_model_status", "antenna_type", "antenna_model", "source_lineage")
    ).lower()
    if "full_ffd" in marker or "lp_xy" in marker:
        x_path = Path(row.get("lp_copol_gain_pattern_file", "")) if row.get("lp_copol_gain_pattern_file") else None
        y_path = Path(row.get("lp_crosspol_gain_pattern_file", "")) if row.get("lp_crosspol_gain_pattern_file") else None
        if x_path is None or y_path is None or not x_path.exists() or not y_path.exists():
            # Diagonal feeds, matching RtConfig: the measured antenna's linear
            # ports are at psi = 42.58 deg, not x/y (Y1f, C1b, Y2a).  Rows made
            # on another machine carry that machine's absolute paths, so the
            # config fallback stays allowed -- but only toward the *same files*
            # (basename match).  Substituting a different pattern, or dropping
            # to the ideal antenna after the row asked for FFD, must fail loudly
            # (F-LP1; the CP side ran ideal unnoticed this way, P-10a).
            cfg_ = default_config()
            cx = cfg_.project_root / cfg_.lp_copol_gain_pattern_file
            cy = cfg_.project_root / cfg_.lp_crosspol_gain_pattern_file
            if x_path is not None and y_path is not None and (
                    x_path.name != cx.name or y_path.name != cy.name):
                raise FileNotFoundError(
                    f"row requests LP FFD patterns {x_path.name!r}/{y_path.name!r} which do "
                    f"not exist here, and the config fallback {cx.name!r}/{cy.name!r} is a "
                    "different antenna; refusing to substitute silently")
            x_path, y_path = cx, cy
        if not (x_path.exists() and y_path.exists()):
            raise FileNotFoundError(
                f"row requests the LP FFD antenna but no pattern pair exists (looked for "
                f"{x_path} and {y_path}); refusing to substitute the ideal antenna silently")
        return make_realistic_lp_antenna_ffd(position, boresight, x_path, y_path, h_axis=h_axis)
    return make_ideal_lp_antenna(position, boresight, h_axis=h_axis)


def _cp_branch_convention_for_row(row: dict, configured: str) -> str:
    """Resolve CP branch authority from antenna provenance without sign repair."""
    value = str(configured).strip()
    if value == "auto":
        # P-7 (2026-08-07): 안테나별 분기를 제거한다. core.py rx_wave_to_port 의 ideal
        # 분기가 켤레를 써서 원편파 라벨을 뒤집던 것이 원인이었고, 그것을 고친 뒤로는
        # ideal·FFD 가 **같은 규약**을 쓴다. `_rx_opposite_tx` 는 그 버그를 상쇄하던
        # 보정값이었지 물리 규약이 아니다. 동결 corpus 재현용으로만 남긴다.
        return "direct_compatible_rx_same_tx"
    if value not in {"direct_compatible_rx_opposite_tx", "direct_compatible_rx_same_tx"}:
        raise ValueError(f"unsupported CP branch convention: {value}")
    return value


def run_one_case(case_row: dict | pd.Series, cfg: RtConfig | None = None, return_aux: bool = False,
                 swap_same_rev: bool = False):
    cfg = cfg or default_config()
    row = case_row.to_dict() if hasattr(case_row, "to_dict") else dict(case_row)
    cp_branch_convention = _cp_branch_convention_for_row(row, cfg.cp_branch_convention)
    case_id = _row_get(row, "case_id", 1)
    mat = _material_from_row(row)
    tx_pos, rx_pos = _positions_from_row(row)
    room_type = _row_get(row, "room_type", _row_get(row, "room_type_cases_tbl", _row_get(row, "room_type_results_tbl", None)))
    is_room_case = room_type not in ("", None)
    if is_room_case:
        room_size = (
            float(_row_get(row, "room_size_l_m", 8.0)),
            float(_row_get(row, "room_size_w_m", 6.0)),
            float(_row_get(row, "room_size_h_m", 3.0)),
        )
        scene = _apply_stage2_room_variants(make_room_abc_scene(room_type=str(room_type), room_size=room_size, material=None), row)
    else:
        scene = make_single_slab_scene(mat, slab_size_m=float(_row_get(row, "slab_size_m", 5.0)))
    scene = _append_condition_geometry(scene, row, tx_pos, rx_pos)
    _use_lp = cfg.polarization_mode.upper() == "LP"
    if is_room_case:
        tx_bore_raw = np.array(
            [
                float(_row_get(row, "tx_boresight_x", 0.0)),
                float(_row_get(row, "tx_boresight_y", 0.0)),
                float(_row_get(row, "tx_boresight_z", -1.0)),
            ]
        )
        tx_bore = normalize(tx_bore_raw)
        tx_h = np.array([1.0, 0.0, 0.0])
        if abs(float(np.dot(tx_h, tx_bore))) > 0.95:
            tx_h = np.array([0.0, 1.0, 0.0])
        tx_h = normalize(tx_h - float(np.dot(tx_h, tx_bore)) * tx_bore)
        rx_bore = np.array([0.0, 0.0, 1.0])
        yaw = np.deg2rad(float(_row_get(row, "rx_azimuth_deg", 0.0)))
        R_yaw = _axis_angle_rotation(rx_bore, yaw)
        rx_h = normalize(R_yaw @ np.array([1.0, 0.0, 0.0]))
        rx_tilt = np.deg2rad(float(_row_get(row, "rx_tilt_deg", 0.0)))
        if abs(rx_tilt) > 0.0:
            # Optional pose-dataset contract: pitch the complete tag antenna
            # frame about its yaw-rotated horizontal axis.  The default
            # rx_tilt_deg=0 path is algebraically identical to the frozen C6
            # room implementation.
            R_tilt = _axis_angle_rotation(rx_h, rx_tilt)
            rx_bore = normalize(R_tilt @ rx_bore)
        rx_v = normalize(np.cross(rx_bore, rx_h))
        if _use_lp:
            tx_ant = _make_lp_antenna_for_row(row, tx_pos, tx_bore, tx_h)
            rx_ant = _make_lp_antenna_for_row(row, rx_pos, rx_bore, rx_h)
        else:
            tx_ant = _make_cp_antenna_for_row(row, tx_pos, tx_bore, tx_h, cfg.tx_handedness)
            rx_ant = _make_cp_antenna_for_row(row, rx_pos, rx_bore, rx_h, cfg.tx_handedness)
    else:
        # Boresight direction: use theta override if provided (measured case geometry)
        # Otherwise default to line-of-sight direction
        theta_tx_deg = _row_get(row, "theta_tx_deg", None)
        theta_rx_deg = _row_get(row, "theta_rx_deg", None)

        if theta_tx_deg is not None and theta_rx_deg is not None:
            # Explicit pointing angles (measured specular-pointing geometry).
            # theta is an AZIMUTH swung from the LoS axis toward the plate, which
            # sits at -y. Rotating in elevation instead aims the antenna at the
            # ceiling: at theta_tx = 75 deg the boresight would be 96.6% vertical
            # and end up 79.5 deg off the plate, i.e. worse than not rotating.
            # The convention is pinned by the data, not assumed -- in the D1350
            # block d/2 == r, so the plate lies at exactly 45 deg azimuth from
            # both antennas, and the sweep's (theta_rx, theta_tx) = (45, 45) case
            # reproduces the plate direction exactly under the formula below.
            theta_tx_rad = np.deg2rad(float(theta_tx_deg))
            theta_rx_rad = np.deg2rad(float(theta_rx_deg))

            # TX looks along +x, RX along -x; both swing toward -y by theta.
            tx_bore = normalize(np.array([np.cos(theta_tx_rad), -np.sin(theta_tx_rad), 0.0]))
            rx_bore = normalize(np.array([-np.cos(theta_rx_rad), -np.sin(theta_rx_rad), 0.0]))
        else:
            # Default: direct line-of-sight
            tx_bore = normalize(rx_pos - tx_pos)
            rx_bore = normalize(tx_pos - rx_pos)

        rx_h = None
        rx_v = None
        if _use_lp:
            tx_ant = _make_lp_antenna_for_row(row, tx_pos, tx_bore, None)
            rx_ant = _make_lp_antenna_for_row(row, rx_pos, rx_bore, None)
        else:
            tx_ant = _make_cp_antenna_for_row(row, tx_pos, tx_bore, None, cfg.tx_handedness)
            rx_ant = _make_cp_antenna_for_row(row, rx_pos, rx_bore, None, cfg.tx_handedness)
    _ant_prov = antenna_provenance(tx_ant, rx_ant)
    paths = enumerate_paths(scene, tx_pos, rx_pos, int(_row_get(row, "rt_max_bounce", cfg.rt_max_bounce)))
    used_blockage_diffraction_proxy = False
    if not paths and str(_row_get(row, "condition_geometry_mode", "")).lower() in EXPLICIT_CONDITION_GEOMETRY_MODES:
        proxy = _blockage_diffraction_proxy_path(scene, tx_pos, rx_pos)
        if proxy is not None:
            paths = [proxy]
            used_blockage_diffraction_proxy = True
    if not paths:
        out = {"case_id": case_id, "failed": True, "error_msg": "no_paths"}
        return (out, {}) if return_aux else out
    H = build_channel(paths, tx_ant, rx_ant, cfg.freqs)
    H_noisy = inject_snr(H, float(_row_get(row, "snr_db", 999.0)), _case_seed(row, cfg, "noise_awgn"))
    idx_fp_hint = _row_index_hint(row, "idx_fp") if cfg.replay_fp_hints else None
    idx_same_hint = _row_index_hint(row, "cp16_idx_same_fp") if cfg.replay_fp_hints else None
    idx_rev_hint = _row_index_hint(row, "cp16_idx_rev_fp") if cfg.replay_fp_hints else None
    feats = extract_all_features(
        H_noisy,
        cfg.freqs,
        cfg.window_type,
        tx_handedness=cfg.tx_handedness,
        rx_port_order=cfg.rx_port_order,
        tx_port_order=cfg.tx_port_order,
        branch_convention=cp_branch_convention,
        idx_fp_hint_1b=idx_fp_hint,
    )
    if not _use_lp:
        feats.update(
            compute_rh_lh_cp16(
                H_noisy,
                cfg.freqs,
                cfg.window_type,
                tx_handedness=cfg.tx_handedness,
                rx_port_order=cfg.rx_port_order,
                tx_port_order=cfg.tx_port_order,
                branch_convention=cp_branch_convention,
                idx_same_hint_1b=idx_same_hint,
                idx_rev_hint_1b=idx_rev_hint,
                swap_same_rev=swap_same_rev,
            )
        )
    bounce_counts = [p.bounce_count for p in paths]
    has_los_path = any(p.bounce_count == 0 for p in paths)
    is_los = bool(_row_get(row, "is_los", has_los_path))
    is_nlos = bool(_row_get(row, "is_nlos", not is_los))
    feats.update({
        "case_id": case_id,
        "failed": False,
        "error_msg": "",
        "num_paths": len(paths),
        "bounce_count_min": min(bounce_counts),
        "bounce_count_max": max(bounce_counts),
        "has_los_path": has_los_path,
        "is_los": is_los,
        "is_nlos": is_nlos,
        "tx_rx_dist_m": float(np.linalg.norm(rx_pos - tx_pos)),
        "material_kind": mat.kind,
        "polarization_mode": cfg.polarization_mode,
        "tx_hand": cfg.tx_handedness,
        "tx_port_order": ",".join(cfg.tx_port_order),
        "rx_port_order": ",".join(cfg.rx_port_order),
        "cp_branch_convention": cp_branch_convention,
        # S3 (2026-08-08): the artifact must state which antenna produced it --
        # the 40-room corpus ran ideal for months because nothing recorded this.
        "prov_use_ffd_tx": bool(_ant_prov["use_ffd"][0]),
        "prov_use_ffd_rx": bool(_ant_prov["use_ffd"][1]),
        "prov_all_use_ffd": bool(_ant_prov["all_use_ffd"]),
        "prov_antenna_patterns": ";".join(
            Path(v).name for pf in _ant_prov["pattern_files"] for v in pf.values()) or "ideal",
        "rx_azimuth_deg": float(_row_get(row, "rx_azimuth_deg", 0.0)),
        "rx_tilt_deg": float(_row_get(row, "rx_tilt_deg", 0.0)),
        "condition_geometry_mode": str(_row_get(row, "condition_geometry_mode", "")),
        "n_condition_surfaces": int(sum(str(s.name).startswith("condition_") for s in scene.surfaces)),
        "used_blockage_diffraction_proxy": bool(used_blockage_diffraction_proxy),
        "replay_fp_hints": bool(cfg.replay_fp_hints),
    })
    if rx_h is not None and rx_v is not None:
        feats.update({
            "rx_h_global_x": float(rx_h[0]),
            "rx_h_global_y": float(rx_h[1]),
            "rx_h_global_z": float(rx_h[2]),
            "rx_v_global_x": float(rx_v[0]),
            "rx_v_global_y": float(rx_v[1]),
            "rx_v_global_z": float(rx_v[2]),
            "rx_bore_global_x": float(rx_bore[0]),
            "rx_bore_global_y": float(rx_bore[1]),
            "rx_bore_global_z": float(rx_bore[2]),
        })
    # tx_ant/rx_ant are exposed so downstream diagnostics can evaluate the SAME
    # antenna objects the channel was built with (e.g. directional_gain_linear_f
    # at a traced ray direction) instead of rebuilding them and risking a
    # different boresight/handedness convention. Additive only: existing keys
    # are unchanged.
    aux = {"H": H_noisy, "paths": paths, "tx_pos": tx_pos, "rx_pos": rx_pos, "scene": scene,
           "tx_ant": tx_ant, "rx_ant": rx_ant, "tx_boresight": tx_bore, "rx_boresight": rx_bore,
           "antenna_provenance": antenna_provenance(tx_ant, rx_ant)}
    return (feats, aux) if return_aux else feats


def run_sweep_batch(cases: pd.DataFrame, cfg: RtConfig | None = None, verbose: bool = True) -> pd.DataFrame:
    rows = []
    for idx, (_, row) in enumerate(cases.iterrows(), start=1):
        try:
            rows.append(run_one_case(row, cfg))
        except Exception as exc:
            rows.append({"case_id": row.get("case_id", idx), "failed": True, "error_msg": str(exc)})
        if verbose and (idx % 50 == 0 or idx == len(cases)):
            print(f"[{idx}/{len(cases)}] complete")
    feat = pd.DataFrame(rows)
    if "case_id" in cases.columns and "case_id" in feat.columns:
        return cases.merge(feat, on="case_id", how="left", suffixes=("", "_py"))
    return pd.concat([cases.reset_index(drop=True), feat.reset_index(drop=True)], axis=1)


def design_lhs_sweep(n_cases: int = 100, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = int(n_cases)
    return pd.DataFrame({
        "case_id": np.arange(1, n + 1),
        "seed_case_id": np.arange(1, n + 1),
        "tx_slab_dist_m": rng.uniform(0.5, 2.0, n),
        "rx_slab_dist_m": rng.uniform(0.5, 2.5, n),
        "eps_r": rng.uniform(2.5, 7.0, n),
        "tan_delta": rng.uniform(0.001, 0.08, n),
        "snr_db": rng.uniform(20.0, 50.0, n),
    })


def design_stage2_cases(n_cases: int = 900, seed: int = 2) -> pd.DataFrame:
    cases = design_lhs_sweep(n_cases, seed)
    rooms = np.array(["A", "B", "C"])
    cases["room_type"] = rooms[(np.arange(len(cases)) % len(rooms))]
    return cases


def design_stage1_recovery_mini_cases(n_cases: int = 30, seed: int = 101) -> pd.DataFrame:
    return design_lhs_sweep(n_cases, seed)


def design_stage2_recovery_mini_cases(n_cases: int = 30, seed: int = 202) -> pd.DataFrame:
    return design_stage2_cases(n_cases, seed)


def struct_array_to_table(rows) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def read_case_json(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def write_dict_csv(row: dict, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        writer.writeheader()
        writer.writerow(row)
