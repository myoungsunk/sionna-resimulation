from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np

from .core import normalize
from .designed_stress import DS1Config, build_path_records, buildability_metrics, make_geometry, material_table


DEFAULT_WALL_HEIGHT_M = 2.40
DEFAULT_AIR_PADDING_M = 0.75


@dataclass(frozen=True)
class DS1HfssCase:
    case_id: str
    source_rank: int
    variant: str
    material_key: str
    material_name: str
    material_kind: str
    eps_r: float
    tan_delta: float
    D_m: float
    u: float
    actual_u: float
    actual_delta_d_m: float
    u_preservation_error_m: float
    u_preservation_pass: bool
    s_m: float
    theta_deg: float
    rho: float
    wall_tilt_deg: float
    at_asymmetry_frac: float
    at_normal_offset_m: float
    anchor_xyz_m: tuple[float, float, float]
    tag_xyz_m: tuple[float, float, float]
    reflector_xyz_m: tuple[float, float, float]
    wall_normal_xyz: tuple[float, float, float]
    wall_tangent_xyz: tuple[float, float, float]
    wall_width_m: float
    wall_height_m: float
    wall_thickness_m: float
    direct_length_m: float
    reflected_length_m: float
    specular_endpoint_margin_m: float
    hfss_auto_plate_width_m: float
    fixture_fresnel_radius_m: float
    fixture_plate_span_m: float
    buildability_pass: bool
    buildability_status: str
    buildability_reasons: str
    geometry_solver_status: str
    reflection_valid: bool
    solver_role: str = "HFSS_CAD_SCAFFOLD_NOT_SOLVED"


def load_target_rows(target_csv: Path) -> list[dict[str, str]]:
    with target_csv.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def build_hfss_cases_from_targets(
    target_csv: Path,
    max_cases: int = 10,
    include_phase2_variants: bool = False,
    config: DS1Config | None = None,
) -> list[DS1HfssCase]:
    cfg = config or DS1Config()
    mats = material_table()
    rows = load_target_rows(target_csv)
    cases: list[DS1HfssCase] = []
    for row in rows[: max(int(max_cases), 0)]:
        rank = int(float(row.get("rank", len(cases) + 1)))
        material_key = str(row.get("m") or row.get("material") or row.get("material_key") or "")
        if material_key not in mats:
            raise KeyError(f"unknown DS1 material in target row: {material_key!r}")
        D_m = _row_float(row, "D", "D_m")
        u = _row_float(row, "u")
        wall_tilt_deg = _row_float(row, "wall_tilt_deg", default=0.0)
        at_asymmetry_frac = _row_float(row, "at_asymmetry_frac", default=0.0)
        geom = make_geometry(
            material_key,
            mats[material_key],
            D_m,
            u,
            cfg.bandwidth_hz,
            cfg.frequency_hz,
            wall_tilt_deg=wall_tilt_deg,
            at_asymmetry_frac=at_asymmetry_frac,
        )
        cases.append(case_from_geometry(geom, rank, _target_variant(row)))
        if include_phase2_variants:
            for wall_tilt in cfg.phase2_wall_tilts_deg:
                if abs(float(wall_tilt) - wall_tilt_deg) <= 1.0e-12:
                    continue
                tilted = make_geometry(
                    material_key,
                    mats[material_key],
                    D_m,
                    u,
                    cfg.bandwidth_hz,
                    cfg.frequency_hz,
                    wall_tilt_deg=float(wall_tilt),
                    at_asymmetry_frac=at_asymmetry_frac,
                )
                cases.append(case_from_geometry(tilted, rank, f"wall_tilt_{_signed_token(float(wall_tilt))}deg"))
            for asym in cfg.phase2_at_asymmetry_frac:
                if abs(float(asym) - at_asymmetry_frac) <= 1.0e-12:
                    continue
                asymmetric = make_geometry(
                    material_key,
                    mats[material_key],
                    D_m,
                    u,
                    cfg.bandwidth_hz,
                    cfg.frequency_hz,
                    wall_tilt_deg=wall_tilt_deg,
                    at_asymmetry_frac=float(asym),
                )
                cases.append(case_from_geometry(asymmetric, rank, f"at_asym_{_signed_token(float(asym))}"))
    return cases


def case_from_geometry(geometry, source_rank: int, variant: str) -> DS1HfssCase:
    direct, reflected = build_path_records(geometry)
    build = buildability_metrics(geometry)
    anchor = np.asarray(direct.points[0], dtype=float)
    tag = np.asarray(direct.points[1], dtype=float)
    reflector = np.asarray(reflected.points[1], dtype=float)
    wall_normal = normalize(np.asarray(reflected.normals[0], dtype=float))
    wall_tangent = normalize(np.cross(np.asarray([0.0, 0.0, 1.0], dtype=float), wall_normal))
    material = geometry.material
    width = max(2.0, float(geometry.D_m) + 2.0 * float(geometry.s_m) + 1.0)
    thickness = wall_thickness_m(geometry.material_key)
    case_id = f"DS1_R{int(source_rank):02d}_{_safe_name(geometry.geometry_id)}_{_safe_name(variant)}"
    return DS1HfssCase(
        case_id=case_id,
        source_rank=int(source_rank),
        variant=str(variant),
        material_key=geometry.material_key,
        material_name=material.name,
        material_kind=material.kind,
        eps_r=float(material.eps_r),
        tan_delta=float(material.tan_delta),
        D_m=float(geometry.D_m),
        u=float(geometry.u),
        actual_u=float(build["actual_u"]),
        actual_delta_d_m=float(build["actual_delta_d_m"]),
        u_preservation_error_m=float(build["u_preservation_error_m"]),
        u_preservation_pass=str(build["u_preservation_pass"]).lower() == "true",
        s_m=float(geometry.s_m),
        theta_deg=float(geometry.theta_deg),
        rho=float(geometry.rho),
        wall_tilt_deg=float(geometry.wall_tilt_deg),
        at_asymmetry_frac=float(geometry.at_asymmetry_frac),
        at_normal_offset_m=float(geometry.at_normal_offset_m),
        anchor_xyz_m=_vec3(anchor),
        tag_xyz_m=_vec3(tag),
        reflector_xyz_m=_vec3(reflector),
        wall_normal_xyz=_vec3(wall_normal),
        wall_tangent_xyz=_vec3(wall_tangent),
        wall_width_m=float(width),
        wall_height_m=DEFAULT_WALL_HEIGHT_M,
        wall_thickness_m=float(thickness),
        direct_length_m=float(direct.path_length_m),
        reflected_length_m=float(reflected.path_length_m),
        specular_endpoint_margin_m=float(build["specular_endpoint_margin_m"]),
        hfss_auto_plate_width_m=float(build["hfss_auto_plate_width_m"]),
        fixture_fresnel_radius_m=float(build["fixture_fresnel_radius_m"]),
        fixture_plate_span_m=float(build["fixture_plate_span_m"]),
        buildability_pass=str(build["buildability_pass"]).lower() == "true",
        buildability_status=str(build["buildability_status"]),
        buildability_reasons=str(build["buildability_reasons"]),
        geometry_solver_status=str(build["geometry_solver_status"]),
        reflection_valid=bool(reflected.valid),
    )


def write_hfss_case_artifacts(output_root: Path, cases: Iterable[DS1HfssCase], source_run_root: Path, command_line: str) -> list[Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    case_list = list(cases)
    csv_path = output_root / "ds1_hfss_case_spec.csv"
    json_path = output_root / "ds1_hfss_case_spec.json"
    manifest_path = output_root / "ds1_hfss_cad_manifest.json"

    write_case_csv(csv_path, case_list)
    json_path.write_text(json.dumps([asdict(case) for case in case_list], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": "DS1_HFSS_CAD_MANIFEST.v1",
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "command_line": command_line,
        "source_run_root": str(source_run_root),
        "case_count": len(case_list),
        "outputs": [str(csv_path), str(json_path)],
        "claim_boundary": [
            "CAD scaffold for Ansys/HFSS scene generation",
            "not solved unless an AEDT project is created and analyzed",
            "not full-wave channel evidence until antenna/ports/mesh/convergence and S21 export are verified",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return [csv_path, json_path, manifest_path]


def write_case_csv(path: Path, cases: list[DS1HfssCase]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [flatten_case(case) for case in cases]
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def flatten_case(case: DS1HfssCase) -> dict[str, object]:
    row = asdict(case)
    for key in ("anchor_xyz_m", "tag_xyz_m", "reflector_xyz_m", "wall_normal_xyz", "wall_tangent_xyz"):
        x, y, z = row.pop(key)
        prefix = key.replace("_xyz_m", "").replace("_xyz", "")
        row[f"{prefix}_x_m"] = x
        row[f"{prefix}_y_m"] = y
        row[f"{prefix}_z_m"] = z
    return row


def create_aedt_projects(
    cases: Iterable[DS1HfssCase],
    output_root: Path,
    aedt_version: str = "2024.1",
    non_graphical: bool = True,
    overwrite: bool = False,
) -> list[Path]:
    from ansys.aedt.core import Hfss

    case_list = list(cases)
    if not case_list:
        return []
    project_dir = output_root / "aedt_projects"
    project_dir.mkdir(parents=True, exist_ok=True)
    project_path = project_dir / f"DS1_HFSS_CAD_{len(case_list):03d}cases.aedt"
    if project_path.exists() and not overwrite:
        raise FileExistsError(project_path)
    first = case_list[0]
    hfss = Hfss(
        project=str(project_path),
        design=_design_name(first),
        solution_type="DrivenModal",
        version=aedt_version,
        non_graphical=non_graphical,
        new_desktop=True,
        close_on_exit=True,
        remove_lock=True,
    )
    try:
        for idx, case in enumerate(case_list):
            design = _design_name(case)
            if idx > 0:
                hfss.insert_design(design, solution_type="DrivenModal")
            else:
                hfss.set_active_design(design)
            _populate_hfss_design(hfss, case)
            hfss.save_project()
    finally:
        hfss.release_desktop(close_projects=True, close_desktop=True)
    return [project_path]


def _populate_hfss_design(hfss, case: DS1HfssCase) -> None:
    hfss.modeler.model_units = "meter"
    material_name = _ensure_hfss_wall_material(hfss, case)
    _create_airbox(hfss, case)
    wall = _create_wall_slab(hfss, case, material_name)
    if case.material_kind.lower() == "pec":
        try:
            hfss.assign_perfect_e(wall.name, name=f"PEC_{case.case_id}")
        except Exception:
            pass
    hfss.modeler.create_sphere(case.anchor_xyz_m, 0.035, name="TX_anchor_marker", material="vacuum")
    hfss.modeler.create_sphere(case.tag_xyz_m, 0.035, name="RX_tag_marker", material="vacuum")
    hfss.modeler.create_sphere(case.reflector_xyz_m, 0.025, name="Specular_reflection_marker", material="vacuum")
    hfss.modeler.create_polyline([case.anchor_xyz_m, case.tag_xyz_m], name="direct_path_reference", material="vacuum", non_model=True)
    hfss.modeler.create_polyline(
        [case.anchor_xyz_m, case.reflector_xyz_m, case.tag_xyz_m],
        name="single_reflection_path_reference",
        material="vacuum",
        non_model=True,
    )
    normal_end = tuple(float(a) + 0.35 * float(b) for a, b in zip(case.reflector_xyz_m, case.wall_normal_xyz))
    hfss.modeler.create_polyline([case.reflector_xyz_m, normal_end], name="wall_normal_reference", material="vacuum", non_model=True)


def _ensure_hfss_wall_material(hfss, case: DS1HfssCase) -> str:
    if case.material_kind.lower() == "pec":
        return "pec"
    name = f"DS1_{_safe_name(case.material_key)}"
    keys = {str(key).lower() for key in getattr(hfss.materials, "material_keys", [])}
    if name.lower() not in keys:
        mat = hfss.materials.add_material(name)
        mat.permittivity = case.eps_r
        mat.dielectric_loss_tangent = case.tan_delta
    return name


def _create_wall_slab(hfss, case: DS1HfssCase, material_name: str):
    origin = [-case.wall_width_m / 2.0, -case.wall_thickness_m / 2.0, -case.wall_height_m / 2.0]
    sizes = [case.wall_width_m, case.wall_thickness_m, case.wall_height_m]
    wall = hfss.modeler.create_box(origin, sizes, name="finite_wall_slab", material=material_name)
    wall.rotate("Z", case.wall_tilt_deg)
    wall.move(list(case.reflector_xyz_m))
    return wall


def _create_airbox(hfss, case: DS1HfssCase):
    points = np.asarray([case.anchor_xyz_m, case.tag_xyz_m, case.reflector_xyz_m], dtype=float)
    lo = points.min(axis=0) - DEFAULT_AIR_PADDING_M
    hi = points.max(axis=0) + DEFAULT_AIR_PADDING_M
    lo[2] = min(lo[2], -case.wall_height_m / 2.0 - DEFAULT_AIR_PADDING_M)
    hi[2] = max(hi[2], case.wall_height_m / 2.0 + DEFAULT_AIR_PADDING_M)
    sizes = hi - lo
    air = hfss.modeler.create_box(_vec3(lo), _vec3(sizes), name="radiation_airbox", material="vacuum")
    try:
        hfss.assign_radiation_boundary_to_objects(air.name, name="Rad_Airbox")
    except Exception:
        pass
    return air


def wall_thickness_m(material_key: str) -> float:
    key = str(material_key).lower()
    if "glass" in key:
        return 0.010
    if "concrete" in key:
        return 0.150
    if "metal" in key or "pec" in key:
        return 0.002
    if "absorber" in key:
        return 0.050
    return 0.012


def _vec3(values: Iterable[float]) -> tuple[float, float, float]:
    vals = [float(v) for v in values]
    if len(vals) != 3:
        raise ValueError("expected three values")
    return (vals[0], vals[1], vals[2])


def _safe_name(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(text))


def _row_float(row: dict[str, str], *names: str, default: float | None = None) -> float:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return float(value)
    if default is not None:
        return float(default)
    raise KeyError("missing numeric field: " + " or ".join(names))


def _target_variant(row: dict[str, str]) -> str:
    generator = str(row.get("generator_type") or "").strip()
    if generator:
        return generator
    wall_tilt = _row_float(row, "wall_tilt_deg", default=0.0)
    asym = _row_float(row, "at_asymmetry_frac", default=0.0)
    if abs(wall_tilt) > 1.0e-12:
        return f"wall_tilt_{_signed_token(wall_tilt)}deg"
    if abs(asym) > 1.0e-12:
        return f"at_asym_{_signed_token(asym)}"
    return "baseline"


def _design_name(case: DS1HfssCase) -> str:
    return _safe_name(case.case_id)[:80]


def _signed_token(value: float) -> str:
    prefix = "p" if float(value) >= 0.0 else "m"
    return prefix + f"{abs(float(value)):.3f}".replace(".", "p").rstrip("0").rstrip("p")
