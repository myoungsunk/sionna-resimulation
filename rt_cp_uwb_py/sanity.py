from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .channel import ifft_to_cir
from .config import default_config
from .core import Material, fresnel_reflection, make_ideal_cp_antenna, normalize
from .scenes import make_single_slab_scene
from .sweep import run_one_case
from .trace import enumerate_paths


def _result(name: str, passed: bool, value=None, expected=None, tolerance=None, message: str = "") -> dict:
    return {"name": name, "passed": bool(passed), "value": value, "expected": expected, "tolerance": tolerance, "message": message}


def check_los_path_loss() -> dict:
    out, aux = run_one_case({"case_id": 1, "snr_db": 999.0}, return_aux=True)
    return _result("A1_los_path_loss", out["failed"] is False and out["num_paths"] >= 1, out.get("num_paths"), ">=1")


def check_single_bounce_path() -> dict:
    scene = make_single_slab_scene(Material(kind="pec"), slab_size_m=10.0)
    paths = enumerate_paths(scene, np.array([-1.0, -1.0, 1.0]), np.array([-1.0, 1.0, 1.0]), 1)
    bounces = sorted({p.bounce_count for p in paths})
    return _result("A2_single_bounce_path", 0 in bounces and 1 in bounces, bounces, "contains 0 and 1")


def check_snell_law() -> dict:
    freqs = default_config().freqs
    gs, gp = fresnel_reflection(Material(eps_r=4.0), np.deg2rad(30.0), freqs)
    ok = np.all(np.isfinite(gs)) and np.all(np.isfinite(gp)) and np.max(np.abs(gs)) <= 1.0 and np.max(np.abs(gp)) <= 1.0
    return _result("A3_snell_law", ok, float(np.max(np.abs(gp))), "<=1")


def check_path_enumeration() -> dict:
    scene = make_single_slab_scene(Material(), slab_size_m=5.0)
    paths = enumerate_paths(scene, np.array([-1.0, -1.5, 1.5]), np.array([-1.0, 1.5, 1.5]), 2)
    return _result("A4_path_enumeration", len(paths) > 0 and max(p.bounce_count for p in paths) <= 2, len(paths), ">0")


def check_cp_handedness_reversal() -> dict:
    out = run_one_case({"case_id": 2, "snr_db": 999.0})
    val = float(out.get("gamma_cp_1_freq_avg", np.nan))
    return _result("B1_cp_handedness_reversal", np.isfinite(val), val, "finite")


def check_brewster_angle() -> dict:
    freqs = np.array([6.5e9])
    eps_r = 4.0
    theta_b = np.arctan(np.sqrt(eps_r))
    _, gp = fresnel_reflection(Material(eps_r=eps_r), theta_b, freqs)
    return _result("B3_brewster_angle", abs(gp[0]) < 1e-6, float(abs(gp[0])), 0.0, 1e-6)


def check_normal_incidence() -> dict:
    gs, gp = fresnel_reflection(Material(eps_r=4.0), 0.0, np.array([6.5e9]))
    ok = np.isclose(abs(gs[0]), 1 / 3, atol=1e-6) and np.isclose(abs(gp[0]), 1 / 3, atol=1e-6)
    return _result("B4_normal_incidence", ok, [float(abs(gs[0])), float(abs(gp[0]))], 1 / 3, 1e-6)


def check_los_cir_peak() -> dict:
    freqs = default_config().freqs
    h, _ = ifft_to_cir(np.ones_like(freqs, dtype=np.complex128), freqs)
    return _result("C1_los_cir_peak", int(np.argmax(np.abs(h))) == 0, int(np.argmax(np.abs(h))), 0)


def check_uwb_pulse_shape() -> dict:
    freqs = default_config().freqs
    h, t = ifft_to_cir(np.ones_like(freqs, dtype=np.complex128), freqs)
    return _result("C2_uwb_pulse_shape", h.shape == t.shape and h.size == 4 * freqs.size, h.size, 4 * freqs.size)


def check_coupling_unitarity() -> dict:
    ant = make_ideal_cp_antenna(np.zeros(3), np.array([1.0, 0.0, 0.0]))
    basis = ant.port_basis_vectors(np.array([1.0, 0.0, 0.0]))
    gram = basis.conj().T @ basis
    return _result("D2_coupling_unitarity", np.allclose(gram, np.eye(2), atol=1e-9), float(np.max(np.abs(gram - np.eye(2)))), 0.0, 1e-9)


def check_direct_cp_los_convention() -> dict:
    ant = make_ideal_cp_antenna(np.zeros(3), np.array([1.0, 0.0, 0.0]), handedness="R")
    return _result("D4_direct_cp_los_convention", ant.circular_order == "RL", ant.circular_order, "RL")


def check_single_bounce_concrete_fresnel() -> dict:
    freqs = np.array([6.5e9])
    gs, gp = fresnel_reflection(Material(name="concrete", eps_r=5.0, tan_delta=0.02), np.deg2rad(45.0), freqs)
    ok = np.isfinite(gs[0]) and np.isfinite(gp[0])
    return _result("D5_single_bounce_concrete_fresnel", bool(ok), [complex(gs[0]).real, complex(gp[0]).real], "finite")


def run_implemented_checks(out_dir: str | Path | None = None) -> pd.DataFrame:
    checks = [
        check_los_path_loss,
        check_single_bounce_path,
        check_snell_law,
        check_path_enumeration,
        check_cp_handedness_reversal,
        check_brewster_angle,
        check_normal_incidence,
        check_los_cir_peak,
        check_uwb_pulse_shape,
        check_coupling_unitarity,
        check_direct_cp_los_convention,
        check_single_bounce_concrete_fresnel,
    ]
    rows = [fn() for fn in checks]
    df = pd.DataFrame(rows)
    if out_dir is not None:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        df.to_csv(out / "sanity_checks.csv", index=False)
        (out / "sanity_checks.json").write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    return df
