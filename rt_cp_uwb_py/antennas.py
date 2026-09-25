from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import numpy as np


EPS = 1.0e-12


def _unit(vec: Iterable[float]) -> np.ndarray:
    arr = np.asarray(list(vec), dtype=float).reshape(3)
    norm = float(np.linalg.norm(arr))
    if norm <= 0.0:
        raise ValueError("direction vector must have nonzero norm")
    return arr / norm


def rotation_from_yaw_pitch_roll(yaw_deg: float, pitch_deg: float = 0.0, roll_deg: float = 0.0) -> np.ndarray:
    """Return a ZYX body-to-world rotation matrix for yaw/pitch/roll in degrees."""

    yaw = math.radians(float(yaw_deg))
    pitch = math.radians(float(pitch_deg))
    roll = math.radians(float(roll_deg))
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cr, sr = math.cos(roll), math.sin(roll)
    rz = np.array([[cy, -sy, 0.0], [sy, cy, 0.0], [0.0, 0.0, 1.0]], dtype=float)
    ry = np.array([[cp, 0.0, sp], [0.0, 1.0, 0.0], [-sp, 0.0, cp]], dtype=float)
    rx = np.array([[1.0, 0.0, 0.0], [0.0, cr, -sr], [0.0, sr, cr]], dtype=float)
    return rz @ ry @ rx


def validate_rotation_matrix(matrix: np.ndarray, atol: float = 1.0e-9) -> bool:
    arr = np.asarray(matrix, dtype=float).reshape(3, 3)
    return bool(np.allclose(arr.T @ arr, np.eye(3), atol=atol) and np.isclose(np.linalg.det(arr), 1.0, atol=atol))


def parse_mount_rotation(value: str | np.ndarray | None) -> np.ndarray:
    """Parse antenna mount rotation as yaw,pitch,roll degrees or a 3x3 matrix.

    The returned matrix maps antenna-local coordinates into the tag body frame.
    Empty values return identity.
    """

    if value is None:
        return np.eye(3)
    if isinstance(value, np.ndarray):
        arr = np.asarray(value, dtype=float).reshape(3, 3)
        if not validate_rotation_matrix(arr):
            raise ValueError("mount rotation matrix must be orthonormal with determinant +1")
        return arr
    text = str(value).strip()
    if not text:
        return np.eye(3)
    parts = [float(part.strip()) for part in text.replace(";", ",").split(",") if part.strip()]
    if len(parts) == 3:
        return rotation_from_yaw_pitch_roll(parts[0], parts[1], parts[2])
    if len(parts) == 9:
        arr = np.asarray(parts, dtype=float).reshape(3, 3)
        if not validate_rotation_matrix(arr):
            raise ValueError("mount rotation matrix must be orthonormal with determinant +1")
        return arr
    raise ValueError("mount rotation must be empty, yaw,pitch,roll, or nine matrix values")


def direction_world_to_tag_body(
    direction_world: Iterable[float],
    yaw_deg: float,
    pitch_deg: float = 0.0,
    roll_deg: float = 0.0,
) -> np.ndarray:
    body_to_world = rotation_from_yaw_pitch_roll(yaw_deg, pitch_deg, roll_deg)
    return body_to_world.T @ _unit(direction_world)


def direction_tag_body_to_antenna_mount(direction_tag_body: Iterable[float], mount_rotation: str | np.ndarray | None = None) -> np.ndarray:
    mount_to_tag = parse_mount_rotation(mount_rotation)
    return mount_to_tag.T @ _unit(direction_tag_body)


def direction_to_pattern_angles(direction_antenna: Iterable[float]) -> tuple[float, float]:
    vec = _unit(direction_antenna)
    theta = math.degrees(math.acos(float(np.clip(vec[2], -1.0, 1.0))))
    phi = math.degrees(math.atan2(float(vec[1]), float(vec[0])))
    return float(theta), float(phi)


def _wrap_phi_to_grid(phi_deg: float, grid: np.ndarray) -> float:
    lo = float(grid[0])
    hi = float(grid[-1])
    span = hi - lo
    if span >= 359.0:
        return float(((float(phi_deg) - lo) % 360.0) + lo)
    return float(np.clip(float(phi_deg), lo, hi))


def _bracket(grid: np.ndarray, value: float) -> tuple[int, int, float]:
    if len(grid) == 1:
        return 0, 0, 0.0
    clipped = float(np.clip(value, float(grid[0]), float(grid[-1])))
    hi = int(np.searchsorted(grid, clipped, side="right"))
    hi = min(max(hi, 1), len(grid) - 1)
    lo = hi - 1
    denom = float(grid[hi] - grid[lo])
    frac = 0.0 if abs(denom) <= EPS else (clipped - float(grid[lo])) / denom
    return lo, hi, float(frac)


@dataclass(frozen=True)
class ReceiverAntennaPattern:
    theta_deg: np.ndarray
    phi_deg: np.ndarray
    gain_db_grid: np.ndarray
    pol_mode: str = "unknown"
    frequency_hz: float | None = None
    source: str = "in_memory"
    normalization: str = "absolute_dbi"
    e_theta_grid: np.ndarray | None = None
    e_phi_grid: np.ndarray | None = None

    def __post_init__(self) -> None:
        theta = np.asarray(self.theta_deg, dtype=float)
        phi = np.asarray(self.phi_deg, dtype=float)
        grid = np.asarray(self.gain_db_grid, dtype=float)
        if grid.shape != (len(theta), len(phi)):
            raise ValueError(f"gain_db_grid shape {grid.shape} does not match theta/phi grid {(len(theta), len(phi))}")
        if np.any(np.diff(theta) < 0) or np.any(np.diff(phi) < 0):
            raise ValueError("theta_deg and phi_deg grids must be sorted ascending")
        object.__setattr__(self, "theta_deg", theta)
        object.__setattr__(self, "phi_deg", phi)
        object.__setattr__(self, "gain_db_grid", grid)
        if self.e_theta_grid is not None or self.e_phi_grid is not None:
            if self.e_theta_grid is None or self.e_phi_grid is None:
                raise ValueError("e_theta_grid and e_phi_grid must be provided together")
            e_theta = np.asarray(self.e_theta_grid, dtype=np.complex128)
            e_phi = np.asarray(self.e_phi_grid, dtype=np.complex128)
            if e_theta.shape != grid.shape or e_phi.shape != grid.shape:
                raise ValueError("complex FFD field grids must match gain_db_grid shape")
            object.__setattr__(self, "e_theta_grid", e_theta)
            object.__setattr__(self, "e_phi_grid", e_phi)

    @classmethod
    def isotropic(cls, gain_db: float = 0.0, pol_mode: str = "isotropic") -> "ReceiverAntennaPattern":
        return cls(
            theta_deg=np.asarray([0.0, 180.0], dtype=float),
            phi_deg=np.asarray([-180.0, 180.0], dtype=float),
            gain_db_grid=np.full((2, 2), float(gain_db), dtype=float),
            pol_mode=pol_mode,
            source="isotropic",
        )

    @classmethod
    def from_csv(
        cls,
        path: str | Path,
        theta_col: str = "theta_deg",
        phi_col: str = "phi_deg",
        gain_col: str = "gain_db",
        pol_mode: str = "unknown",
        frequency_hz: float | None = None,
        normalization: str = "absolute_dbi",
    ) -> "ReceiverAntennaPattern":
        rows: list[dict[str, float]] = []
        with Path(path).open("r", encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                rows.append({theta_col: float(row[theta_col]), phi_col: float(row[phi_col]), gain_col: float(row[gain_col])})
        theta = np.asarray(sorted({row[theta_col] for row in rows}), dtype=float)
        phi = np.asarray(sorted({row[phi_col] for row in rows}), dtype=float)
        grid = np.full((len(theta), len(phi)), np.nan, dtype=float)
        theta_index = {float(v): i for i, v in enumerate(theta)}
        phi_index = {float(v): i for i, v in enumerate(phi)}
        for row in rows:
            grid[theta_index[row[theta_col]], phi_index[row[phi_col]]] = row[gain_col]
        if np.isnan(grid).any():
            raise ValueError("CSV pattern grid is incomplete")
        return cls(theta, phi, grid, pol_mode=pol_mode, frequency_hz=frequency_hz, source=str(path), normalization=normalization)

    @classmethod
    def from_ffd(
        cls,
        path: str | Path,
        frequency_hz: float | None = None,
        pol_mode: str = "unknown",
        normalization: str = "absolute_dbi",
    ) -> "ReceiverAntennaPattern":
        """Load an HFSS-style .ffd vector-field pattern using total field power.

        The parser expects theta-major rows after each `Frequency ...` header.
        This keeps the convention explicit for later verification against the
        measured/simulated antenna pattern source.
        """

        path = Path(path)
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            theta_start, theta_stop, theta_count = fh.readline().split()
            phi_start, phi_stop, phi_count = fh.readline().split()
            theta_count_i = int(theta_count)
            phi_count_i = int(phi_count)
            theta = np.linspace(float(theta_start), float(theta_stop), theta_count_i)
            phi = np.linspace(float(phi_start), float(phi_stop), phi_count_i)
            freq_header = fh.readline().split()
            if len(freq_header) != 2 or freq_header[0].lower() != "frequencies":
                raise ValueError("FFD file must contain a 'Frequencies N' header")
            freq_count = int(freq_header[1])
            selected_grid: np.ndarray | None = None
            selected_e_theta: np.ndarray | None = None
            selected_e_phi: np.ndarray | None = None
            selected_freq: float | None = None
            for _ in range(freq_count):
                freq_line = fh.readline().split()
                if len(freq_line) != 2 or freq_line[0].lower() != "frequency":
                    raise ValueError("FFD file must contain 'Frequency <Hz>' blocks")
                current_freq = float(freq_line[1])
                use_block = frequency_hz is None or math.isclose(current_freq, float(frequency_hz), rel_tol=0.0, abs_tol=1.0)
                values: list[float] = []
                e_theta_values: list[complex] = []
                e_phi_values: list[complex] = []
                for _row_idx in range(theta_count_i * phi_count_i):
                    fields = [float(item) for item in fh.readline().split()]
                    if len(fields) < 2:
                        raise ValueError("FFD field row must contain at least two numeric components")
                    if len(fields) >= 4:
                        e_theta = complex(fields[0], fields[1])
                        e_phi = complex(fields[2], fields[3])
                    else:
                        e_theta = complex(fields[0], fields[1])
                        e_phi = 0.0 + 0.0j
                    power = float(sum(component * component for component in fields))
                    values.append(10.0 * math.log10(max(power, EPS)))
                    e_theta_values.append(e_theta)
                    e_phi_values.append(e_phi)
                if use_block and selected_grid is None:
                    selected_grid = np.asarray(values, dtype=float).reshape(theta_count_i, phi_count_i)
                    selected_e_theta = np.asarray(e_theta_values, dtype=np.complex128).reshape(theta_count_i, phi_count_i)
                    selected_e_phi = np.asarray(e_phi_values, dtype=np.complex128).reshape(theta_count_i, phi_count_i)
                    selected_freq = current_freq
                    if frequency_hz is None:
                        break
            if selected_grid is None:
                raise ValueError(f"frequency_hz={frequency_hz!r} was not found in {path}")
        return cls(
            theta,
            phi,
            selected_grid,
            pol_mode=pol_mode,
            frequency_hz=selected_freq,
            source=str(path),
            normalization=normalization,
            e_theta_grid=selected_e_theta,
            e_phi_grid=selected_e_phi,
        )

    def gain_db(self, theta_deg: float, phi_deg: float, pol_mode: str | None = None, frequency_hz: float | None = None) -> float:
        if pol_mode is not None and self.pol_mode not in {"unknown", "isotropic"} and str(pol_mode).lower() != self.pol_mode.lower():
            raise ValueError(f"pattern pol_mode={self.pol_mode!r} cannot answer pol_mode={pol_mode!r}")
        if frequency_hz is not None and self.frequency_hz is not None and not math.isclose(float(frequency_hz), float(self.frequency_hz), rel_tol=0.0, abs_tol=1.0):
            raise ValueError(f"pattern frequency_hz={self.frequency_hz!r} cannot answer frequency_hz={frequency_hz!r}")
        theta = float(np.clip(float(theta_deg), float(self.theta_deg[0]), float(self.theta_deg[-1])))
        phi = _wrap_phi_to_grid(phi_deg, self.phi_deg)
        t0, t1, tf = _bracket(self.theta_deg, theta)
        p0, p1, pf = _bracket(self.phi_deg, phi)
        g00 = float(self.gain_db_grid[t0, p0])
        g01 = float(self.gain_db_grid[t0, p1])
        g10 = float(self.gain_db_grid[t1, p0])
        g11 = float(self.gain_db_grid[t1, p1])
        g0 = g00 * (1.0 - pf) + g01 * pf
        g1 = g10 * (1.0 - pf) + g11 * pf
        return float(g0 * (1.0 - tf) + g1 * tf)

    def field_components(self, theta_deg: float, phi_deg: float) -> tuple[complex, complex]:
        if self.e_theta_grid is None or self.e_phi_grid is None:
            raise ValueError("pattern does not contain complex vector-field components")
        e_theta = _interp_complex_grid_deg(self.theta_deg, self.phi_deg, self.e_theta_grid, theta_deg, phi_deg)
        e_phi = _interp_complex_grid_deg(self.theta_deg, self.phi_deg, self.e_phi_grid, theta_deg, phi_deg)
        return e_theta, e_phi

    def circular_components(self, theta_deg: float, phi_deg: float, r_definition: str = "e_theta_plus_j_e_phi") -> tuple[complex, complex]:
        e_theta, e_phi = self.field_components(theta_deg, phi_deg)
        if r_definition == "e_theta_plus_j_e_phi":
            right = (e_theta + 1j * e_phi) / math.sqrt(2.0)
            left = (e_theta - 1j * e_phi) / math.sqrt(2.0)
        elif r_definition == "e_theta_minus_j_e_phi":
            right = (e_theta - 1j * e_phi) / math.sqrt(2.0)
            left = (e_theta + 1j * e_phi) / math.sqrt(2.0)
        else:
            raise ValueError(f"unsupported circular definition: {r_definition}")
        return right, left

    def circular_power_db(self, theta_deg: float, phi_deg: float, hand: str, r_definition: str = "e_theta_plus_j_e_phi") -> float:
        right, left = self.circular_components(theta_deg, phi_deg, r_definition)
        comp = right if str(hand).upper().startswith("R") else left
        return float(10.0 * math.log10(max(abs(comp) ** 2, EPS)))

    def circular_xpd_db(self, theta_deg: float, phi_deg: float, co_hand: str, r_definition: str = "e_theta_plus_j_e_phi") -> float:
        right, left = self.circular_components(theta_deg, phi_deg, r_definition)
        co = right if str(co_hand).upper().startswith("R") else left
        cross = left if str(co_hand).upper().startswith("R") else right
        return float(20.0 * math.log10(max(abs(co), EPS) / max(abs(cross), EPS)))

    def axial_ratio_db(self, theta_deg: float, phi_deg: float, r_definition: str = "e_theta_plus_j_e_phi") -> float:
        right, left = self.circular_components(theta_deg, phi_deg, r_definition)
        major = max(abs(right), abs(left))
        minor = min(abs(right), abs(left))
        if major <= EPS:
            return float("nan")
        if major <= minor + EPS:
            return float("inf")
        return float(20.0 * math.log10((major + minor) / max(major - minor, EPS)))


def _interp_complex_grid_deg(theta_grid_deg: np.ndarray, phi_grid_deg: np.ndarray, values: np.ndarray, theta_deg: float, phi_deg: float) -> complex:
    phi_wrapped = _wrap_phi_to_grid(phi_deg, phi_grid_deg)
    t0, t1, tf = _bracket(theta_grid_deg, theta_deg)
    p0, p1, pf = _bracket(phi_grid_deg, phi_wrapped)
    v00 = complex(values[t0, p0])
    v01 = complex(values[t0, p1])
    v10 = complex(values[t1, p0])
    v11 = complex(values[t1, p1])
    v0 = v00 * (1.0 - pf) + v01 * pf
    v1 = v10 * (1.0 - pf) + v11 * pf
    return complex(v0 * (1.0 - tf) + v1 * tf)


@lru_cache(maxsize=32)
def _load_ffd_pattern_cached(path_text: str, metadata_items: tuple[tuple[str, str], ...]) -> dict[str, object]:
    metadata = dict(metadata_items)
    path = Path(path_text)
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        theta_start, theta_stop, theta_count = fh.readline().split()
        phi_start, phi_stop, phi_count = fh.readline().split()
        theta_count_i = int(theta_count)
        phi_count_i = int(phi_count)
        theta_rad = np.radians(np.linspace(float(theta_start), float(theta_stop), theta_count_i))
        phi_rad = np.radians(np.linspace(float(phi_start), float(phi_stop), phi_count_i))
        freq_header = fh.readline().split()
        if len(freq_header) != 2 or freq_header[0].lower() != "frequencies":
            raise ValueError("FFD file must contain a 'Frequencies N' header")
        freq_count = int(freq_header[1])
        freqs: list[float] = []
        e_theta_blocks: list[np.ndarray] = []
        e_phi_blocks: list[np.ndarray] = []
        for _ in range(freq_count):
            freq_line = fh.readline().split()
            if len(freq_line) != 2 or freq_line[0].lower() != "frequency":
                raise ValueError("FFD file must contain 'Frequency <Hz>' blocks")
            freqs.append(float(freq_line[1]))
            e_theta: list[complex] = []
            e_phi: list[complex] = []
            for _row_idx in range(theta_count_i * phi_count_i):
                fields = [float(item) for item in fh.readline().split()]
                if len(fields) >= 4:
                    e_theta.append(complex(fields[0], fields[1]))
                    e_phi.append(complex(fields[2], fields[3]))
                elif len(fields) >= 2:
                    e_theta.append(complex(fields[0], fields[1]))
                    e_phi.append(0.0 + 0.0j)
                else:
                    raise ValueError("FFD field row must contain at least two numeric components")
            e_theta_blocks.append(np.asarray(e_theta, dtype=np.complex128).reshape(theta_count_i, phi_count_i))
            e_phi_blocks.append(np.asarray(e_phi, dtype=np.complex128).reshape(theta_count_i, phi_count_i))
    return {
        "theta_rad": theta_rad,
        "phi_rad": phi_rad,
        "freqs_hz": np.asarray(freqs, dtype=float),
        "e_theta": np.stack(e_theta_blocks, axis=0),
        "e_phi": np.stack(e_phi_blocks, axis=0),
        "source": str(path),
        "metadata": metadata,
    }


def load_ffd_pattern(path: str | Path, **metadata) -> dict[str, object]:
    path = Path(path)
    metadata_items = tuple(sorted((str(k), str(v)) for k, v in metadata.items()))
    return _load_ffd_pattern_cached(str(path.resolve()), metadata_items)


def _interp_complex_grid(theta_grid: np.ndarray, phi_grid: np.ndarray, values: np.ndarray, theta: float, phi: float) -> complex:
    theta_deg = math.degrees(theta)
    phi_deg = math.degrees(phi)
    theta_deg_grid = np.degrees(theta_grid)
    phi_deg_grid = np.degrees(phi_grid)
    phi_wrapped = _wrap_phi_to_grid(phi_deg, phi_deg_grid)
    t0, t1, tf = _bracket(theta_deg_grid, theta_deg)
    p0, p1, pf = _bracket(phi_deg_grid, phi_wrapped)
    v00 = complex(values[t0, p0])
    v01 = complex(values[t0, p1])
    v10 = complex(values[t1, p0])
    v11 = complex(values[t1, p1])
    v0 = v00 * (1.0 - pf) + v01 * pf
    v1 = v10 * (1.0 - pf) + v11 * pf
    return complex(v0 * (1.0 - tf) + v1 * tf)


def interpolate_pattern(ffd: dict[str, object], theta_rad: float, phi_rad: float, frequency_hz: float | np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    freqs_req = np.atleast_1d(np.asarray(frequency_hz, dtype=float))
    freqs = np.asarray(ffd["freqs_hz"], dtype=float)
    theta_grid = np.asarray(ffd["theta_rad"], dtype=float)
    phi_grid = np.asarray(ffd["phi_rad"], dtype=float)
    e_theta = np.asarray(ffd["e_theta"], dtype=np.complex128)
    e_phi = np.asarray(ffd["e_phi"], dtype=np.complex128)
    out_theta: list[complex] = []
    out_phi: list[complex] = []
    for freq in freqs_req:
        idx = int(np.argmin(np.abs(freqs - float(freq))))
        out_theta.append(_interp_complex_grid(theta_grid, phi_grid, e_theta[idx], float(theta_rad), float(phi_rad)))
        out_phi.append(_interp_complex_grid(theta_grid, phi_grid, e_phi[idx], float(theta_rad), float(phi_rad)))
    return np.asarray(out_theta, dtype=np.complex128), np.asarray(out_phi, dtype=np.complex128)


def interpolate_ffd_field(ffd: dict[str, object], theta_rad: float, phi_rad: float, freqs_hz: np.ndarray) -> np.ndarray:
    e_theta, e_phi = interpolate_pattern(ffd, theta_rad, phi_rad, freqs_hz)
    theta = float(theta_rad)
    phi = float(phi_rad)
    e_theta_vec = np.asarray([math.cos(theta) * math.cos(phi), math.cos(theta) * math.sin(phi), -math.sin(theta)], dtype=float)
    e_phi_vec = np.asarray([-math.sin(phi), math.cos(phi), 0.0], dtype=float)
    return e_theta_vec[:, None] * e_theta[None, :] + e_phi_vec[:, None] * e_phi[None, :]


def load_patch_pattern_synthetic(**kwargs) -> dict[str, object]:
    return {"type": "synthetic_patch", **kwargs}


def load_patch_pattern(paths: object | None = None, **kwargs) -> dict[str, object]:
    if isinstance(paths, (list, tuple)) and len(paths) >= 2:
        return {"ffd_r": load_ffd_pattern(paths[0]), "ffd_l": load_ffd_pattern(paths[1]), **kwargs}
    return {"type": "patch_pattern", "paths": paths, **kwargs}


def make_realistic_patch_antenna(pattern: object, position, boresight, h_axis=None, handedness: str = "R", *_, **__):
    from .core import make_ideal_cp_antenna

    antenna = make_ideal_cp_antenna(position, boresight, h_axis=h_axis, handedness=handedness)
    antenna.pattern_data = {"realistic_patch_pattern": pattern}
    return antenna


def make_realistic_patch_antenna_ffd(
    position,
    boresight,
    rhcp_pattern_file: str | Path,
    lhcp_pattern_file: str | Path,
    h_axis=None,
    handedness: str = "R",
):
    from .core import make_ideal_cp_antenna

    antenna = make_ideal_cp_antenna(position, boresight, h_axis=h_axis, handedness=handedness)
    antenna.use_ffd = True
    antenna.ffd_port_r = load_ffd_pattern(rhcp_pattern_file, pol_mode="RHCP")
    antenna.ffd_port_l = load_ffd_pattern(lhcp_pattern_file, pol_mode="LHCP")
    antenna.pattern_data = {
        "rhcp_pattern_file": str(rhcp_pattern_file),
        "lhcp_pattern_file": str(lhcp_pattern_file),
    }
    return antenna


def make_realistic_lp_antenna_ffd(
    position,
    boresight,
    copol_pattern_file: str | Path,
    crosspol_pattern_file: str | Path,
    h_axis=None,
):
    from .core import make_ideal_lp_antenna

    antenna = make_ideal_lp_antenna(position, boresight, h_axis=h_axis)
    antenna.use_ffd = True
    antenna.ffd_port_r = load_ffd_pattern(copol_pattern_file, pol_mode="LP_COPOL")
    antenna.ffd_port_l = load_ffd_pattern(crosspol_pattern_file, pol_mode="LP_CROSSPOL")
    antenna.pattern_data = {
        "lp_copol_pattern_file": str(copol_pattern_file),
        "lp_crosspol_pattern_file": str(crosspol_pattern_file),
    }
    return antenna


def coupling_from_angle(antenna, direction) -> tuple[float, float]:
    boresight = np.asarray(getattr(antenna, "boresight", [1.0, 0.0, 0.0]), dtype=float)
    cosine = abs(float(np.dot(_unit(direction), _unit(boresight))))
    off_boresight = math.degrees(math.acos(float(np.clip(cosine, -1.0, 1.0))))
    ar_db = 0.05 * off_boresight
    xpd_db = max(0.0, 20.0 - 0.1 * off_boresight)
    return float(ar_db), float(xpd_db)


def compute_ffd_metrics(ffd: dict[str, object], **_) -> dict[str, float]:
    e_theta = np.asarray(ffd["e_theta"], dtype=np.complex128)
    e_phi = np.asarray(ffd["e_phi"], dtype=np.complex128)
    power = np.abs(e_theta) ** 2 + np.abs(e_phi) ** 2
    return {
        "peak_gain_db": float(10.0 * np.log10(max(float(np.nanmax(power)), EPS))),
        "mean_gain_db": float(10.0 * np.log10(max(float(np.nanmean(power)), EPS))),
    }


def save_ffd_pattern_mat(ffd: dict[str, object], path: str | Path, **_) -> dict[str, str]:
    path = Path(path)
    path.write_text(
        "\n".join(
            [
                "# FFD pattern MAT export placeholder",
                "# This Python port records provenance instead of writing MATLAB .mat files.",
                f"source={ffd.get('source', '')}",
            ]
        ),
        encoding="utf-8",
    )
    return {"path": str(path), "status": "placeholder_written"}
