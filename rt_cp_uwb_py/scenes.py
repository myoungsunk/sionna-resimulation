from __future__ import annotations

import numpy as np

from .core import Material, Scene, Surface
from .materials import materials_library


def make_single_slab_scene(material: Material | None = None, slab_center=(0.0, 0.0, 0.0), slab_size_m: float = 5.0) -> Scene:
    mat = material or Material(name="concrete", eps_r=5.5, tan_delta=0.05)
    return Scene(
        surfaces=(
            Surface(
                surface_id=1,
                name="single_slab",
                point=np.asarray(slab_center, dtype=float),
                normal=np.array([1.0, 0.0, 0.0]),
                u_axis=np.array([0.0, 1.0, 0.0]),
                v_axis=np.array([0.0, 0.0, 1.0]),
                half_u=float(slab_size_m) / 2.0,
                half_v=float(slab_size_m) / 2.0,
                material=mat,
            ),
        )
    )


def _plane_axes(normal) -> tuple[np.ndarray, np.ndarray]:
    n = np.asarray(normal, dtype=float).reshape(3)
    n = n / np.linalg.norm(n)
    ref = np.array([0.0, 0.0, 1.0]) if abs(n[2]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = ref - float(np.dot(ref, n)) * n
    if np.linalg.norm(u) < 1e-9:
        ref = np.array([1.0, 0.0, 0.0])
        u = ref - float(np.dot(ref, n)) * n
    u = u / np.linalg.norm(u)
    v = np.cross(n, u)
    v = v / np.linalg.norm(v)
    return u, v


def make_room_abc_scene(room_type: str = "A", room_size=(5.0, 4.0, 3.0), material: Material | None = None) -> Scene:
    lib = materials_library()
    mat_wall = material or lib["drywall"]
    mat_floor = material or lib["concrete"]
    mat_ceil = material or lib["drywall"]
    lx, ly, lz = [float(x) for x in room_size]
    surfaces = []

    def add_rect(name, center, normal, dims, mat):
        u, v = _plane_axes(normal)
        surfaces.append(Surface(len(surfaces) + 1, name, np.array(center), np.array(normal), u, v, float(dims[0]) / 2.0, float(dims[1]) / 2.0, mat))

    def add_box(prefix, center, dims, mat):
        cx, cy, cz = [float(x) for x in center]
        dx, dy, dz = [float(x) for x in dims]
        add_rect(f"{prefix}_west", [cx - dx / 2.0, cy, cz], [-1, 0, 0], [dy, dz], mat)
        add_rect(f"{prefix}_east", [cx + dx / 2.0, cy, cz], [1, 0, 0], [dy, dz], mat)
        add_rect(f"{prefix}_south", [cx, cy - dy / 2.0, cz], [0, -1, 0], [dx, dz], mat)
        add_rect(f"{prefix}_north", [cx, cy + dy / 2.0, cz], [0, 1, 0], [dx, dz], mat)
        add_rect(f"{prefix}_top", [cx, cy, cz + dz / 2.0], [0, 0, 1], [dx, dy], mat)

    add_rect("floor", [lx / 2, ly / 2, 0], [0, 0, 1], [lx, ly], mat_floor)
    add_rect("ceiling", [lx / 2, ly / 2, lz], [0, 0, -1], [lx, ly], mat_ceil)
    add_rect("wall_west", [0, ly / 2, lz / 2], [1, 0, 0], [ly, lz], mat_wall)
    add_rect("wall_east", [lx, ly / 2, lz / 2], [-1, 0, 0], [ly, lz], mat_wall)
    add_rect("wall_south", [lx / 2, 0, lz / 2], [0, 1, 0], [lx, lz], mat_wall)
    add_rect("wall_north", [lx / 2, ly, lz / 2], [0, -1, 0], [lx, lz], mat_wall)

    rt = str(room_type or "A").upper()
    if rt == "B":
        add_rect("window_glass", [lx - 0.02, 0.55 * ly, 0.65 * lz], [-1, 0, 0], [1.4, 1.0], lib["glass"])
        add_rect("desk_top", [0.68 * lx, 0.62 * ly, 0.75], [0, 0, 1], [1.2, 0.7], lib["wood"])
        add_rect("desk_front", [0.95 * lx, 0.62 * ly, 0.375], [-1, 0, 0], [0.7, 0.75], lib["wood"])
    elif rt == "C":
        add_rect("window_glass", [lx - 0.02, 0.55 * ly, 0.65 * lz], [-1, 0, 0], [1.4, 1.0], lib["glass"])
        add_rect("desk_top", [0.68 * lx, 0.62 * ly, 0.75], [0, 0, 1], [1.2, 0.7], lib["wood"])
        add_rect("desk_front", [0.95 * lx, 0.62 * ly, 0.375], [-1, 0, 0], [0.7, 0.75], lib["wood"])
        add_rect("cabinet_front", [0.28 * lx, ly - 0.35, 0.9], [0, -1, 0], [0.8, 1.8], lib["metal_pec"])
        add_rect("cabinet_side", [0.18 * lx, ly - 0.65, 0.9], [1, 0, 0], [0.6, 1.8], lib["metal_pec"])
        add_rect("cabinet_top", [0.28 * lx, ly - 0.65, 1.8], [0, 0, 1], [0.8, 0.6], lib["metal_pec"])
        add_rect("wood_partition", [0.45 * lx, 0.28 * ly, 1.0], [0, 1, 0], [1.2, 2.0], lib["wood"])
    elif rt in {"HALL", "OPEN_HALL"}:
        column_w = min(0.25, 0.05 * min(lx, ly))
        margin_x = min(max(1.2, 0.15 * lx), 0.5 * lx)
        margin_y = min(max(1.2, 0.15 * ly), 0.5 * ly)
        for idx, (cx, cy) in enumerate([(x, y) for x in sorted({margin_x, lx - margin_x}) for y in sorted({margin_y, ly - margin_y})], start=1):
            add_box(f"hall_column_{idx}", [cx, cy, lz / 2.0], [column_w, column_w, lz], lib["concrete"])

    return Scene(tuple(surfaces))


def compute_single_bounce_geometry(tx_pos, rx_pos, surface: Surface | None = None) -> dict:
    surf = surface or make_single_slab_scene().surfaces[0]
    tx = np.asarray(tx_pos, dtype=float).reshape(3)
    rx = np.asarray(rx_pos, dtype=float).reshape(3)
    n = surf.normal
    image = tx - 2.0 * float(np.dot(tx - surf.point, n)) * n
    direction = rx - image
    denom = float(np.dot(direction, n))
    if abs(denom) < 1e-12:
        return {"valid": False, "reflection_point": np.full(3, np.nan), "path_length_m": np.nan}
    alpha = float(np.dot(surf.point - image, n) / denom)
    point = image + alpha * direction
    valid = 0.0 <= alpha <= 1.0 and surf.contains_point(point)
    return {
        "valid": bool(valid),
        "reflection_point": point,
        "path_length_m": float(np.linalg.norm(point - tx) + np.linalg.norm(rx - point)),
        "surface_name": surf.name,
    }


def generate_symmetric_boresight_geometry(distance_m: float = 3.0, z_m: float = 1.5) -> dict:
    tx = np.array([-distance_m / 2.0, 0.0, z_m])
    rx = np.array([distance_m / 2.0, 0.0, z_m])
    return {"tx_pos": tx, "rx_pos": rx, "tx_boresight": rx - tx, "rx_boresight": tx - rx}


def generate_room_tx_rx_grid(room_size=(8.0, 6.0, 3.0), nx: int = 3, ny: int = 3, z_m: float = 1.5):
    lx, ly, _ = [float(x) for x in room_size]
    xs = np.linspace(-0.35 * lx, 0.35 * lx, int(nx))
    ys = np.linspace(-0.35 * ly, 0.35 * ly, int(ny))
    rows = []
    case_id = 1
    for x in xs:
        for y in ys:
            rows.append({"case_id": case_id, "anchor_x": 0.0, "anchor_y": 0.0, "anchor_z": z_m, "tag_x": x, "tag_y": y, "tag_z": z_m})
            case_id += 1
    return rows
