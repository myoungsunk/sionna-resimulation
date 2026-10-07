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


MAX_DROPPED_REL_AMP = 1e-2          # reported flag only (PREREG_AMENDMENTS A10b); validity is decided by the parity run


def _solve(scene, solver, cfg, freq, fi):
    scene.frequency = float(freq[fi])
    p = solver(scene, **cfg)
    a_iso = (np.asarray(p.a[0]) + 1j * np.asarray(p.a[1])).reshape(2, 2, -1)
    tau = np.asarray(p.tau).ravel().astype(np.float64)
    ang = [np.asarray(getattr(p, k)).ravel().astype(np.float64) for k in ("theta_t", "phi_t", "theta_r", "phi_r")]
    return a_iso, tau, ang


def _assemble(raw, bins):
    """Union reference over all nodes; returns (ref_tau, ref_ang, ref_dirs, jones, amp, present)."""
    _, t0, g0 = raw[bins[0]]
    order = P.canonical_order(t0, *g0)
    ref_tau, ref_ang = t0[order], [a[order] for a in g0]
    ref_dirs = P.path_directions(*ref_ang)
    for fi in bins[1:]:                                              # grow the reference with paths that are new at later nodes
        _, tau, ang = raw[fi]
        _, extra = P.match_partial(ref_tau, ref_dirs, tau, P.path_directions(*ang), tol=ANGLE_TOL_RAD)
        if len(extra):
            ref_tau = np.r_[ref_tau, tau[extra]]
            ref_ang = [np.r_[r, a[extra]] for r, a in zip(ref_ang, ang)]
            ref_dirs = P.path_directions(*ref_ang)
    n = len(ref_tau)
    jones = np.zeros((len(bins), n, 3, 3), complex)
    amp = np.zeros((len(bins), n))
    present = np.zeros((len(bins), n), bool)
    for k, fi in enumerate(bins):
        a_iso, tau, ang = raw[fi]
        match, _ = P.match_partial(ref_tau, ref_dirs, tau, P.path_directions(*ang), tol=ANGLE_TOL_RAD)
        got = np.flatnonzero(match >= 0)
        sel = match[got]
        present[k, got] = True
        jones[k, got] = P.jones_from_iso(a_iso[:, :, sel], *[a[sel] for a in ang])
        amp[k, got] = np.linalg.norm(a_iso[:, :, sel], axis=(0, 1))
    return ref_tau, ref_ang, ref_dirs, jones, amp, present


def trace_position(scene, solver, cfg, freq, bins, x, y, setup):
    """Trace one position at ``bins``; returns (jones (K, n, 3, 3), (tau, ang), status, counts, audit).

    Paths are matched across nodes against a union reference; a path absent at a node gets J = 0 there.  For a path that exists on one side of a cut only,
    the cut bin is located by bisection and its two bins are added as nodes (A10c).  ``audit`` lists every path absent somewhere with its relative amplitude.
    """
    scene.receivers["rx"].position = mi.Point3f(*setup.robot_position(x, y).tolist())
    raw = {fi: _solve(scene, solver, cfg, freq, fi) for fi in bins}
    nodes = list(bins)
    ref_tau, ref_ang, ref_dirs, jones, amp, present = _assemble(raw, nodes)
    cuts, complex_paths = {}, []
    for i in np.flatnonzero(~present.all(axis=0)):
        p = present[:, i]
        k = np.flatnonzero(p[:-1] != p[1:])
        if len(k) != 1:
            complex_paths.append(int(i))
            continue
        lo, hi, had_lo = nodes[k[0]], nodes[k[0] + 1], bool(p[k[0]])
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if mid not in raw:
                raw[mid] = _solve(scene, solver, cfg, freq, mid)
            _, tau_m, ang_m = raw[mid]
            match, _ = P.match_partial(ref_tau[[i]], ref_dirs[[i]], tau_m, P.path_directions(*ang_m), tol=ANGLE_TOL_RAD)
            if (match[0] >= 0) == had_lo:
                lo = mid
            else:
                hi = mid
        cuts[int(i)] = dict(last_present_bin=int(lo if had_lo else hi), first_absent_bin=int(hi if had_lo else lo), present_below=had_lo)
    if len(raw) > len(nodes):
        nodes = sorted(raw)
        ref_tau, ref_ang, ref_dirs, jones, amp, present = _assemble(raw, nodes)
    counts = [int(raw[fi][1].size) for fi in nodes]
    rel = amp / np.maximum(np.linalg.norm(amp, axis=1, keepdims=True), 1e-300)
    dropped = [dict(path=int(i), tau_s=float(ref_tau[i]), absent_nodes=[int(nodes[k]) for k in np.flatnonzero(~present[:, i])], cut=cuts.get(int(i)),
                    max_rel_amp_where_present=float(rel[present[:, i], i].max()) if present[:, i].any() else 0.0) for i in np.flatnonzero(~present.all(axis=0))]
    worst = max([d["max_rel_amp_where_present"] for d in dropped], default=0.0)
    status = "OK" if not complex_paths else "PATH_SET_CHANGED_WITH_FREQUENCY"          # more than one transition of a path inside the band: not handled
    return jones, (ref_tau, ref_ang), status, counts, dict(dropped_paths=dropped, max_dropped_rel_amp=worst, screen_exceeded=bool(worst > MAX_DROPPED_REL_AMP),
                                                           n_paths_union=int(len(ref_tau)), present=present, nodes=nodes, complex_paths=complex_paths)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", type=Path, required=True, help="rf_tasks_*.json (positions are taken from it)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--nodes", default="17", help="number of frequency nodes, or 'all'")
    ap.add_argument("--shard", default="0/1")
    ap.add_argument("--limit", type=int, default=0, help="only the first N positions of this shard (smoke test)")
    ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--only", nargs="*", help="only these tags, e.g. x7.0000_y0.0000")
    ap.add_argument("--anchor-x", type=float, default=4.0, help="ceiling anchor x [m] (A = 4, B = 10); anchor y is 0")
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
    setup = CorridorSetup(anchor_x_m=args.anchor_x)
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
            with np.load(out) as z:
                if str(z["status"]) == "OK":
                    continue                              # unusable traces are recomputed (A10)
        t0 = time.monotonic()
        j, ref, status, counts, audit = trace_position(scene, solver, cfg, freq, bins, t["x"], t["y"], setup)
        flags = []
        tau, ang = ref[0], ref[1]
        names, unmatched = path_signature(tau, setup.anchor_position, setup.robot_position(t["x"], t["y"]), setup.length_m, setup.y_half, setup.height_m)
        tmp = out.with_suffix(".tmp.npz")
        np.savez_compressed(tmp, jones=j, tau=tau, ang=np.array(ang), node_bins=np.array(audit["nodes"]), node_freq_hz=freq[audit["nodes"]], x=t["x"], y=t["y"],
                            signature=np.array(names), unmatched=unmatched, status=status, flagged_bins=np.array(flags, int), path_counts=np.array(counts),
                            present=audit["present"], max_dropped_rel_amp=audit["max_dropped_rel_amp"])
        tmp.replace(out)
        receipt = dict(tag=t["tag"], x=t["x"], y=t["y"], status=status, flagged_bins=flags, dropped_audit=audit["dropped_paths"], max_dropped_rel_amp=audit["max_dropped_rel_amp"], screen_exceeded=audit["screen_exceeded"],
                       n_nodes=len(audit["nodes"]), n_paths=int(tau.size), complex_paths=audit["complex_paths"],
                       unmatched_paths=unmatched, pathsolver_calls=len(audit["nodes"]), elapsed_s=round(time.monotonic() - t0, 2), versions=versions,
                       solver=cfg, materials=bindings, runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                       command=" ".join(sys.argv))
        (args.out / f"{t['tag']}_trace_receipt.json").write_text(json.dumps(receipt, indent=1))
        print(json.dumps(dict(tag=t["tag"], status=status, paths=int(tau.size), unmatched=unmatched, seconds=receipt["elapsed_s"])), flush=True)


if __name__ == "__main__":
    main()
