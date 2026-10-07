"""Method B, step 2 (numpy only): turn stored per-position Jones traces into H(pose, bin, rx, tx)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from qclean_uwb.drivesim import pattern_apply as P
from qclean_uwb.scenarios.corridor import ANCHOR_ROTATION, rot_z

ROOT = Path(__file__).resolve().parents[3]
BANK_MANIFEST = ROOT / "results" / "SIONNA_G2_FFD_NOFLIP_20260924_01a0d30b" / "bank" / "BANK_MANIFEST.json"
PORTS = ("LP_plus45", "LP_minus45")


def tag_of(x: float, y: float) -> str:
    return f"x{x:.4f}_y{y:.4f}"


def load_banks(bank_dir: Path = ROOT, ports=PORTS) -> list[P.Bank]:
    """Load FFD banks and verify their SHA256 against ``BANK_MANIFEST.json`` (same rule as corridor_sionna_run.load_banks)."""
    expected = json.loads(BANK_MANIFEST.read_text())["npz_sha256"]
    banks = []
    for name in ports:
        path = Path(bank_dir) / f"{name}_bank.npz"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected[path.name]:
            raise ValueError(f"BANK_SHA_MISMATCH {path.name}")
        with np.load(path) as z:
            banks.append(P.Bank({k: z[k] for k in z.files}))
    if not np.array_equal(banks[0].freqs_hz, banks[1].freqs_hz):
        raise ValueError("BANK_FREQUENCIES_DIFFER")
    return banks


def load_trace(path) -> dict:
    with np.load(path) as z:
        t = {k: z[k] for k in z.files}
    t["status"] = str(t["status"])
    return t


def h_for_antenna_yaws(trace: dict, banks: list[P.Bank], antenna_yaws_deg, tx_rotation=ANCHOR_ROTATION) -> np.ndarray:
    """H for several antenna yaws at one position: shape (n_yaw, n_bin, n_rx, n_tx), rows = RX ports, columns = anchor TX ports."""
    if trace["status"] != "OK":
        raise ValueError(f"TRACE_NOT_USABLE {trace['status']}")
    freqs = banks[0].freqs_hz
    jones = P.interp_jones(trace["jones"], trace["node_freq_hz"], freqs, present=trace.get("present"))
    ang, tau = trace["ang"], trace["tau"]
    tx_f = np.stack([P.field_world(b, tx_rotation, ang[0], ang[1]) for b in banks])
    out = []
    for yaw in antenna_yaws_deg:
        rx_f = np.stack([P.field_world(b, rot_z(float(yaw)), ang[2], ang[3]) for b in banks])
        out.append(P.channel_from_jones(jones, tau, freqs, rx_f, tx_f))
    return np.array(out)


def assemble(poses: list[dict], trace_dirs: list[Path], banks: list[P.Bank], mount_deg: float, allow_missing: bool = False):
    """H store for one (lateral, mount): returns (H[n_pose, n_bin, 2, 2], report dict)."""
    by_tag: dict[str, list[dict]] = {}
    for p in poses:
        by_tag.setdefault(tag_of(p["x"], p["y"]), []).append(p)
    n_bin = len(banks[0].freqs_hz)
    h = np.full((len(poses), n_bin, 2, 2), np.nan + 0j, complex)
    missing, unusable = [], []
    for tag, ps in by_tag.items():
        path = next((d / f"{tag}_trace.npz" for d in trace_dirs if (d / f"{tag}_trace.npz").exists()), None)
        if path is None:
            missing.append(tag)
            continue
        trace = load_trace(path)
        if trace["status"] != "OK":
            unusable.append(dict(tag=tag, status=trace["status"]))
            continue
        yaws = [p["yaw_body_deg"] + mount_deg for p in ps]
        hh = h_for_antenna_yaws(trace, banks, yaws)
        for p, row in zip(ps, hh):
            h[p["pose_id"]] = row
    report = dict(n_pose=len(poses), n_positions=len(by_tag), missing=missing, unusable=unusable, complete=not missing and not unusable)
    if not report["complete"] and not allow_missing:
        raise ValueError(f"INCOMPLETE_H_STORE missing={len(missing)} unusable={len(unusable)}")
    return h, report
