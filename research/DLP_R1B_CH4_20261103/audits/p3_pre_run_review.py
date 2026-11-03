#!/usr/bin/env python3
"""Independent source review math checks; artificial inputs only, NO R1 replay."""
from __future__ import annotations
import datetime
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
ADAPTER = ROOT / "research/DLP_R1B_CH4_20261103/runtime/r1b_replay.py"
CORE = ROOT / "research/EKF4_RANGE_S_STAGED_20261014/core.py"
OBSERVER = ROOT / "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src/qclean_uwb/drivesim/observation.py"

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    sys.modules[name] = obj
    spec.loader.exec_module(obj)
    return obj

def main():
    adapter = module("independent_r1b_adapter", ADAPTER)
    core = module("independent_r1b_core", CORE)
    observer = module("independent_r1b_observer", OBSERVER)
    checks = []
    def record(name, value, threshold):
        checks.append(dict(name=name, measured=float(value), maximum=float(threshold), passed=bool(value <= threshold)))

    # Independent centered derivative of the frozen motion transition on
    # artificial interior states; no project trajectory and no RF are used.
    f_error = 0.
    for x, ds, da, dt in [(np.array([1., -.2, .4, .001]), .04, .005, .2),
                          (np.array([-2., .7, -1.1, -.002]), .03, .12, .2),
                          (np.array([0., 0., .2, 0.]), 0., .1, .2)]:
        _, f, _ = core.transition(x, ds, da, dt)
        for axis in range(4):
            delta = np.eye(4)[axis] * 1e-6
            yp = core.transition(x + delta, ds, da, dt)[0]
            ym = core.transition(x - delta, ds, da, dt)[0]
            diff = yp - ym
            diff[2] = float(adapter.wrap(diff[2]))
            f_error = max(f_error, float(np.max(abs(diff / 2e-6 - f[:, axis]))))
    record("U03_artificial_motion_F_centered_difference", f_error, 1e-6)

    # Accepted and rejected affine measurement checks, using an independently
    # formed explicit inverse and Joseph form. No SourceFFD/real observation.
    x = np.array([1., .3, .2, .001])
    p = np.array([[.02, .003, .001, 0.], [.003, .03, -.002, 0.],
                  [.001, -.002, .01, .0001], [0., 0., .0001, .0001]])
    hmat = np.array([[.8, .1, 0., 0.], [.01, -.04, .7, 0.]])
    offset = np.array([.2, -.15])
    r = adapter.R0.copy()
    s = hmat @ p @ hmat.T + r
    gain = p @ hmat.T @ np.linalg.inv(s)
    for name, innovation in [("accepted", np.array([.01, -.02])), ("rejected", np.array([3., -2.]))]:
        z = hmat @ x + offset + innovation
        y, pc, info = core.gaussian_update(x, p, z, lambda q: (hmat @ q + offset, hmat), r, gate_threshold=adapter.GATE)
        expected_nis = float(innovation @ np.linalg.inv(s) @ innovation)
        accepted = expected_nis <= adapter.GATE
        expected_y = x.copy()
        expected_p = p.copy()
        if accepted:
            expected_y += gain @ innovation
            expected_y[2] = adapter.wrap(expected_y[2])
            a = np.eye(4) - gain @ hmat
            expected_p = a @ p @ a.T + gain @ r @ gain.T
        record("U05_artificial_" + name + "_state", float(np.max(abs(y - expected_y))), 1e-10)
        record("U05_artificial_" + name + "_Joseph", float(np.max(abs(pc - expected_p))), 1e-10)
        record("U10_artificial_" + name + "_NIS", abs(info["NIS"] - expected_nis), 1e-9)
        checks.append(dict(name="U10_artificial_" + name + "_gate", measured=bool(info["accepted"]), expected=accepted, passed=bool(info["accepted"]) == accepted))

    # Three artificial spectra with a deliberately conflicting Tx1 column.
    # Compare the adapter extractor to independent per-pose direct FFT math;
    # this tests Tx0, RX order, common tap, and independent Full/LoS detection.
    f = 6250400000. + 1950000. * np.arange(257)
    c = 299792458.
    distance = np.array([3.2, 6.7, 11.1])
    direct = np.exp(-2j * np.pi * distance[:, None] / c * f[None, :])
    full = np.zeros((3, 257, 2, 2), complex)
    los = np.zeros_like(full)
    los[:, :, 0, 0] = direct
    los[:, :, 1, 0] = .6j * direct
    los[:, :, 0, 1] = -70 * direct
    los[:, :, 1, 1] = 100 * direct
    full[:] = los
    delayed = np.exp(-2j * np.pi * (distance + 1.2)[:, None] / c * f[None, :])
    full[:, :, 0, 0] += .7j * delayed
    full[:, :, 1, 0] += 1.1 * delayed
    extracted = adapter.observe_rf(dict(freq_hz=f, H_full=full, H_los=los), observer)
    extraction_error = 0.
    tap_mismatch = 0
    for channel, h in [("full", full), ("los", los)]:
        for k in range(3):
            w = .5 - .5 * np.cos(2 * np.pi * np.arange(257) / 256)
            cir = np.fft.ifft(h[k, :, :, 0] * w[:, None], n=1028, axis=0) * 257
            mag = abs(cir)
            branch = int(np.argmax(mag.max(axis=0)))
            tap = int(np.flatnonzero(mag[:, branch] >= .3 * mag[:, branch].max())[0])
            power = abs(cir[tap]) ** 2
            expected = np.array([tap * c / (1028 * 1950000.), (power[0] - power[1]) / power.sum()])
            extraction_error = max(extraction_error, float(np.max(abs(expected - extracted[channel]["z"][k]))))
            tap_mismatch += int(tap != extracted[channel]["tap"][k])
    record("T05_artificial_observer_range_s_parity", extraction_error, 1e-9)
    record("T05_artificial_observer_tap_parity", tap_mismatch, 0.)
    result = dict(schema="DLP_R1B_P3_PRE_RUN_PURE_MATH_REVIEW_V1",
                  reviewer="/root/ekf_contract_review",
                  role="DISTINCT_COMPUTATIONAL_REVIEWER_NOT_HUMAN_SIGNOFF",
                  status="PASS_PURE_MATH_CHECKS" if all(c["passed"] for c in checks) else "FAIL",
                  not_scientific_release=True, real_R1_RF_or_filter_executed=False,
                  source_files={str(p.relative_to(ROOT)): digest(p) for p in [ADAPTER, CORE, OBSERVER]},
                  reviewer_code_sha256=digest(__file__), checks=checks,
                  utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  limits=["No real SourceFFD Native RF parity tested here", "No R1 recursive result or score computed", "Production remains gated on parent P0/G1 and frozen input contract"])
    target = OUT / "P3_PRE_RUN_MATH_QA.json"
    target.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if all(c["passed"] for c in checks) else 1

if __name__ == "__main__":
    raise SystemExit(main())
