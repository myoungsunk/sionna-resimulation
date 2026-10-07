"""Method B, step 1 (needs Sionna): trace each corridor position once with unit isotropic V/H ports.

For every position the unmodified PathSolver is called at K frequency nodes (default 17 of the 257 bins; ``--nodes all`` = bin-by-bin)
with TX and RX at identity orientation and isotropic V/H ports.  The result is the per-path transverse Jones matrix ``J``
(see qclean_uwb.drivesim.pattern_apply); FFD patterns, antenna yaw and mount offsets are applied offline by rf_b_apply.py.

  python scripts/drive_sim/rf_b_trace.py --tasks results/DRIVE_SIM_20261007/S1/rf_tasks_y0_m0.json --out OUT --shard 0/4 --nodes 17

One process = one thread; start N shards in parallel (see run_rf_snowball.sh).  Positions whose trace file exists are skipped.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import sys
import time
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPTS / "g2_completion"))
import corridor_sionna_run as C  # noqa: E402  (sets the mitsuba variant, imports sionna.rt)
import mitsuba as mi  # noqa: E402
import sionna.rt as rt  # noqa: E402
from sionna_native_runtime import Ports  # noqa: E402
from qclean_uwb.drivesim import pattern_apply as P  # noqa: E402
from qclean_uwb.drivesim.paths import path_signature  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402

ANGLE_TOL_RAD = 1e-4


class IsoPort:
    """Unit-gain isotropic port with fixed local (theta_hat, phi_hat) polarisation: k=0 -> V, k=1 -> H."""

    def __init__(self, k: int):
        self.k = k

    def evaluate(self, theta, phi):
        one, zero = theta * 0.0 + 1.0, theta * 0.0
        if self.k == 0:
            return mi.Complex2f(one, zero), mi.Complex2f(zero, zero)
        return mi.Complex2f(zero, zero), mi.Complex2f(one, zero)


def node_bins(n_total: int, k: str) -> list[int]:
    if k == "all":
        return list(range(n_total))
    return sorted({int(v) for v in np.round(np.linspace(0, n_total - 1, int(k)))})


def ang_perm(perm, p):
    return [np.asarray(getattr(p, k)).ravel().astype(np.float64)[perm] for k in ("theta_t", "phi_t", "theta_r", "phi_r")]


def trace_position(scene, solver, cfg, freq, bins, x, y, setup):
    scene.receivers["rx"].position = mi.Point3f(*setup.robot_position(x, y).tolist())
    jones, ref, flags, counts = [], None, [], []
    for fi in bins:
        scene.frequency = float(freq[fi])
        p = solver(scene, **cfg)
        a_iso = (np.asarray(p.a[0]) + 1j * np.asarray(p.a[1])).reshape(2, 2, -1)
        tau = np.asarray(p.tau).ravel().astype(np.float64)
        ang = [np.asarray(getattr(p, k)).ravel().astype(np.float64) for k in ("theta_t", "phi_t", "theta_r", "phi_r")]
        if ref is None:
            order = P.canonical_order(tau, *ang)
            ref = (tau[order], [a[order] for a in ang], P.path_directions(*[a[order] for a in ang]))
            tau, ang = ref[0], ref[1]
            perm = order
        else:
            got = P.align_paths(ref[0], ref[2], tau, P.path_directions(*ang), tol=ANGLE_TOL_RAD)
            if got is None:
                if __import__("os").environ.get("DRIVE_DEBUG"):
                    g2 = P.align_paths(ref[0], ref[2], tau, P.path_directions(*ang), tol=10.0)
                    print("ALIGN_FAIL bin", fi, "n", tau.size, "tau multiset equal", bool(np.array_equal(np.sort(ref[0]), np.sort(tau))),
                          "worst", None if g2 is None else g2[1], flush=True)
                flags.append(int(fi))
                counts.append(int(tau.size))
                continue
            perm = got[0]
        counts.append(int(ref[0].size))
        jones.append(P.jones_from_iso(a_iso[:, :, perm], *ang_perm(perm, p)))
    return np.array(jones), ref, flags, counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", type=Path, required=True, help="rf_tasks_*.json (positions are taken from it)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--nodes", default="17", help="number of frequency nodes, or 'all'")
    ap.add_argument("--shard", default="0/1")
    ap.add_argument("--limit", type=int, default=0, help="only the first N positions of this shard (smoke test)")
    ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--only", nargs="*", help="only these tags, e.g. x7.0000_y0.0000")
    args = ap.parse_args()
    import drjit as dr
    dr.set_thread_count(args.threads)
    shard, n_shards = (int(v) for v in args.shard.split("/"))
    tasks = json.loads(args.tasks.read_text())
    if args.only:
        tasks = [t for t in tasks if t["tag"] in set(args.only)]
    tasks = [t for i, t in enumerate(tasks) if i % n_shards == shard]
    if args.limit:
        tasks = tasks[: args.limit]
    args.out.mkdir(parents=True, exist_ok=True)
    setup = CorridorSetup()
    assert all(c["passed"] for c in setup.validate()), "SETUP_VALIDATION_FAILED"
    cfg = json.loads(C.SOLVER_SOURCE.read_text())["solver"]
    with np.load(C.BANK_DIR / "LP_plus45_bank.npz") as z:     # only the frequency axis is needed; SHA is checked by load_banks()
        freq = z["freqs_hz"]
    banks_ok = C.load_banks()                                 # asserts bank SHA256 == BANK_MANIFEST.json
    del banks_ok
    bins = node_bins(len(freq), args.nodes)
    scene, bindings = C.build_scene(setup, args.out / f"scene_shard{shard}")
    scene.add(rt.Transmitter("tx", position=setup.anchor_position.tolist(), orientation=[0.0, 0.0, 0.0]))
    scene.add(rt.Receiver("rx", position=setup.robot_position(*setup.example_xy_m[0]).tolist(), orientation=[0.0, 0.0, 0.0]))
    scene.tx_array = rt.AntennaArray(Ports([IsoPort(0), IsoPort(1)]), mi.Point3f(0, 0, 0))
    scene.rx_array = rt.AntennaArray(Ports([IsoPort(0), IsoPort(1)]), mi.Point3f(0, 0, 0))
    solver = rt.PathSolver()
    versions = {n: importlib.metadata.version(n) for n in ("sionna-rt", "mitsuba", "drjit")}
    for t in tasks:
        out = args.out / f"{t['tag']}_trace.npz"
        if out.exists():
            continue
        t0 = time.monotonic()
        j, ref, flags, counts = trace_position(scene, solver, cfg, freq, bins, t["x"], t["y"], setup)
        status = "OK" if not flags else "PATH_SET_CHANGED_WITH_FREQUENCY"
        tau, ang = ref[0], ref[1]
        names, unmatched = path_signature(tau, setup.anchor_position, setup.robot_position(t["x"], t["y"]), setup.length_m, setup.y_half, setup.height_m)
        tmp = out.with_suffix(".tmp.npz")
        np.savez_compressed(tmp, jones=j, tau=tau, ang=np.array(ang), node_bins=np.array(bins), node_freq_hz=freq[bins], x=t["x"], y=t["y"],
                            signature=np.array(names), unmatched=unmatched, status=status, flagged_bins=np.array(flags, int), path_counts=np.array(counts))
        tmp.replace(out)
        receipt = dict(tag=t["tag"], x=t["x"], y=t["y"], status=status, flagged_bins=flags, n_nodes=len(bins), n_paths=int(tau.size),
                       unmatched_paths=unmatched, pathsolver_calls=len(bins), elapsed_s=round(time.monotonic() - t0, 2), versions=versions,
                       solver=cfg, materials=bindings, runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                       command=" ".join(sys.argv))
        (args.out / f"{t['tag']}_trace_receipt.json").write_text(json.dumps(receipt, indent=1))
        print(json.dumps(dict(tag=t["tag"], status=status, paths=int(tau.size), unmatched=unmatched, seconds=receipt["elapsed_s"])), flush=True)


if __name__ == "__main__":
    main()
