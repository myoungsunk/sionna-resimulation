"""Corridor yaw-sweep producer: native Sionna RT 2.0.1, LP_DIAG (+45/-45) ports only.

One process handles one robot position. For every (yaw, frequency bin) it runs the
unmodified PathSolver with the project's FFD bank adapter and stores the 2x2 complex H
(rows = robot RX ports [+45, -45], columns = anchor TX ports [+45, -45]) plus the path
list. Run inside an environment that has sionna-rt 2.0.1 / mitsuba 3.8.0 / drjit 1.3.1.

  python scripts/corridor_sionna_run.py --out DIR --position 0            # full sweep
  python scripts/corridor_sionna_run.py --out DIR --position 0 --yaws 0 90 --bin-stride 128
  python scripts/corridor_sionna_run.py --out DIR --los-check              # FFD/rotation check
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
import mitsuba as mi

mi.set_variant("llvm_ad_mono_polarized")
import drjit as dr  # noqa: E402
import sionna.rt as rt  # noqa: E402
from scipy.interpolate import RegularGridInterpolator  # noqa: E402
from scipy.spatial.transform import Rotation  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "g2_completion"))
from sionna_native_runtime import BankPort, Ports  # noqa: E402  (project's pinned FFD adapter)
from qclean_uwb.scenarios.corridor import ANCHOR_ROTATION, CorridorSetup  # noqa: E402

C0 = 299792458.0
# Temporary material assignment (same ITU names the project uses); thickness in metres.
MATERIALS = {
    "floor": ("concrete", 0.2), "ceiling": ("concrete", 0.2),
    "end_x_min": ("concrete", 0.2), "end_x_max": ("concrete", 0.2),
    "wall_y_neg": ("plasterboard", 0.0125), "wall_y_pos": ("plasterboard", 0.0125),
}
BANK_DIR = ROOT
PORTS = ("LP_plus45", "LP_minus45")
SOLVER_SOURCE = ROOT / "results" / "SIONNA_NATIVE41_REFRESH_20260925_01a0d84e" / "CONFIG.json"
BANK_MANIFEST = ROOT / "results" / "SIONNA_G2_FFD_NOFLIP_20260924_01a0d30b" / "bank" / "BANK_MANIFEST.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_banks() -> list[dict]:
    expected = json.loads(BANK_MANIFEST.read_text())["npz_sha256"]
    banks = []
    for name in PORTS:
        p = BANK_DIR / f"{name}_bank.npz"
        assert sha256(p) == expected[p.name], f"BANK_SHA_MISMATCH {p.name}"
        with np.load(p) as z:
            banks.append({k: z[k] for k in z.files})
    assert np.array_equal(banks[0]["freqs_hz"], banks[1]["freqs_hz"])
    return banks


def write_ply(path: Path, quad: np.ndarray) -> None:
    tris = [(0, 1, 2), (0, 2, 3)]
    lines = ["ply", "format ascii 1.0", "element vertex 4", "property float x", "property float y", "property float z",
             "element face 2", "property list uchar int vertex_indices", "end_header"]
    lines += [" ".join(format(float(v), ".17g") for v in p) for p in quad]
    lines += [f"3 {a} {b} {c}" for a, b, c in tris]
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def build_scene(setup: CorridorSetup, scene_dir: Path):
    scene_dir.mkdir(parents=True, exist_ok=True)
    scene = rt.load_scene()
    objects, bindings = [], []
    for name, quad in setup.surfaces().items():
        itu, thick = MATERIALS[name]
        ply = scene_dir / f"{name}.ply"
        write_ply(ply, quad)
        mat = rt.ITURadioMaterial(name="rm_" + name, itu_type=itu, thickness=thick)
        objects.append(rt.SceneObject(fname=str(ply), name=name, radio_material=mat))
        bindings.append(dict(object=name, itu_type=itu, thickness_m=thick, ply_sha256=sha256(ply)))
    scene.edit(add=objects)
    return scene, bindings


def euler(rotation: np.ndarray) -> list[float]:
    return Rotation.from_matrix(rotation).as_euler("ZYX").tolist()


def make_ports(banks):
    txp = [BankPort(np.deg2rad(b["theta_deg"]), np.deg2rad(b["phi_deg"])) for b in banks]
    rxp = [BankPort(np.deg2rad(b["theta_deg"]), np.deg2rad(b["phi_deg"]), True) for b in banks]
    return txp, rxp


def set_bin(scene, banks, txp, rxp, fi: int, freq_hz: float) -> None:
    scene.frequency = float(freq_hz)
    for i, b in enumerate(banks):
        txp[i].update(b["e_theta"][fi], b["e_phi"][fi])
        rxp[i].update(b["e_theta"][fi], b["e_phi"][fi])
    scene.tx_array = rt.AntennaArray(Ports(txp), mi.Point3f(0, 0, 0))
    scene.rx_array = rt.AntennaArray(Ports(rxp), mi.Point3f(0, 0, 0))


def solve(solver, scene, cfg):
    paths = solver(scene, **cfg)
    a = np.asarray(paths.a[0]) + 1j * np.asarray(paths.a[1])
    tau = np.asarray(paths.tau).reshape(-1)
    n = tau.size
    coef = a.reshape(2, 2, n)
    inter = np.asarray(paths.interactions).reshape(-1, n)
    obj = np.asarray(paths.objects).reshape(-1, n).astype(np.int64)
    return coef, tau, inter, obj


def run_sweep(args, setup, cfg, banks):
    x, y = args.xy if args.xy else setup.example_xy_m[args.position]
    tag = args.tag or f"position_{args.position}"
    lo, hi = setup.robot_x_range_m
    assert lo <= x <= hi and abs(y) <= setup.robot_y_limit_m, f"POSITION_OUTSIDE_ALLOWED_REGION {x},{y}"
    yaws = args.yaws if args.yaws else list(setup.yaw_sweep_deg)
    freq = banks[0]["freqs_hz"]
    bins = list(range(0, len(freq), args.bin_stride))
    scene, bindings = build_scene(setup, args.out / "scene")
    a_pos, r_pos = setup.anchor_position, setup.robot_position(x, y)
    scene.add(rt.Transmitter("tx", position=a_pos.tolist(), orientation=euler(ANCHOR_ROTATION)))
    scene.add(rt.Receiver("rx", position=r_pos.tolist(), orientation=euler(setup.robot_rotation(0.0))))
    txp, rxp = make_ports(banks)
    solver = rt.PathSolver()
    H = np.zeros((len(yaws), len(bins), 2, 2), np.complex128)
    counts = np.zeros((len(yaws), len(bins)), np.int32)
    flat_a, flat_tau, flat_inter, flat_obj, offsets = [], [], [], [], [0]
    t0 = time.monotonic()
    for bi, fi in enumerate(bins):
        set_bin(scene, banks, txp, rxp, fi, freq[fi])
        for yi, yaw in enumerate(yaws):
            scene.receivers["rx"].orientation = mi.Point3f(*euler(setup.robot_rotation(yaw)))
            coef, tau, inter, obj = solve(solver, scene, cfg)
            H[yi, bi] = (coef * np.exp(-2j * np.pi * freq[fi] * tau)[None, None, :]).sum(-1)
            counts[yi, bi] = tau.size
            flat_a.append(coef.astype(np.complex64)); flat_tau.append(tau); flat_inter.append(inter.astype(np.int8)); flat_obj.append(obj)
            offsets.append(offsets[-1] + tau.size)
        if bi % 16 == 0:
            print(json.dumps(dict(position=args.position, bin=int(fi), done=bi + 1, of=len(bins),
                                  seconds=round(time.monotonic() - t0, 1), last_paths=int(counts[-1, bi]))), flush=True)
    assert np.isfinite(H).all(), "NONFINITE_H"
    inter_depth = max(i.shape[0] for i in flat_inter)
    inter_cat = np.concatenate([np.pad(i, ((0, inter_depth - i.shape[0]), (0, 0))) for i in flat_inter], axis=1)
    obj_cat = np.concatenate([np.pad(o, ((0, inter_depth - o.shape[0]), (0, 0))) for o in flat_obj], axis=1)
    np.save(args.out / f"{tag}_H.npy", H)
    np.savez_compressed(
        args.out / f"{tag}_sweep.npz", H=H, objects_cat=obj_cat, yaw_deg=np.array(yaws), bin_index=np.array(bins),
        freqs_hz=freq[bins], path_counts=counts, a_cat=np.concatenate(flat_a, axis=-1), tau_cat=np.concatenate(flat_tau),
        interactions_cat=inter_cat, offsets=np.array(offsets), robot_xy_m=np.array([x, y]), anchor_m=a_pos, robot_antenna_m=r_pos,
        ports=np.array(PORTS), H_layout="[yaw, bin, rx_port(+45,-45), tx_port(+45,-45)]; offsets index flattened (bin-major, yaw-minor)")
    receipt = dict(position=args.position, tag=tag, object_indices={str(o.object_id): n for n, o in scene.objects.items()}, robot_xy_m=[x, y], yaws=yaws, n_bins=len(bins), bin_stride=args.bin_stride,
                   pathsolver_calls=len(yaws) * len(bins), elapsed_s=round(time.monotonic() - t0, 2),
                   seconds_per_call=round((time.monotonic() - t0) / (len(yaws) * len(bins)), 4),
                   mean_paths=float(counts.mean()), max_paths=int(counts.max()), materials=bindings,
                   solver=cfg, versions={n: importlib.metadata.version(n) for n in ("sionna-rt", "mitsuba", "drjit")},
                   runner_sha256=sha256(Path(__file__)), adapter_sha256=sha256(ROOT / "scripts" / "g2_completion" / "sionna_native_runtime.py"),
                   bank_sha256={f"{n}_bank.npz": sha256(BANK_DIR / f"{n}_bank.npz") for n in PORTS}, command=" ".join(sys.argv))
    (args.out / f"{tag}_receipt.json").write_text(json.dumps(receipt, indent=2))
    print(json.dumps(dict(done=True, **{k: receipt[k] for k in ("position", "pathsolver_calls", "elapsed_s", "seconds_per_call", "mean_paths")})), flush=True)


def los_check(args, setup, banks):
    """Independent Cartesian contraction vs PathSolver LoS (max_depth=0), at the corridor poses."""
    freq = banks[0]["freqs_hz"]
    txp, rxp = make_ports(banks)
    solver, results = rt.PathSolver(), []
    for pos, (x, y) in enumerate(setup.example_xy_m):
        for yaw in (0.0, 50.0, 130.0, 180.0):
            for fi in (0, 128, 256):
                f = float(freq[fi])
                rots = {"tx": ANCHOR_ROTATION, "rx": setup.robot_rotation(yaw)}
                tx_pos, rx_pos = setup.anchor_position, setup.robot_position(x, y)
                dvec = rx_pos - tx_pos
                dist = float(np.linalg.norm(dvec))
                direction = dvec / dist
                fields = {}
                for role in ("tx", "rx"):
                    d_local = rots[role].T @ (direction if role == "tx" else -direction)
                    theta, phi = np.arccos(np.clip(d_local[2], -1, 1)), np.arctan2(d_local[1], d_local[0])
                    vecs = []
                    for b in banks:
                        th, ph = np.deg2rad(b["theta_deg"]), np.deg2rad(b["phi_deg"])
                        pp = (phi - ph[0]) % (2 * np.pi) + ph[0]
                        e = RegularGridInterpolator((th, ph), np.stack((b["e_theta"][fi], b["e_phi"][fi]), axis=-1))([[theta, pp]])[0]
                        et = np.array([np.cos(theta) * np.cos(phi), np.cos(theta) * np.sin(phi), -np.sin(theta)])
                        ep = np.array([-np.sin(phi), np.cos(phi), 0.0])
                        vecs.append(rots[role] @ (et * e[0] + ep * e[1]) * np.sqrt(2 * np.pi / 376.730313668))
                    fields[role] = np.array(vecs)
                expected = fields["rx"] @ fields["tx"].T * C0 / f / (4 * np.pi * dist)
                scene = rt.load_scene()
                set_bin(scene, banks, txp, rxp, fi, f)
                scene.add(rt.Transmitter("tx", position=tx_pos.tolist(), orientation=euler(rots["tx"])))
                scene.add(rt.Receiver("rx", position=rx_pos.tolist(), orientation=euler(rots["rx"])))
                paths = solver(scene, max_depth=0, los=True, specular_reflection=False, refraction=False)
                actual = (np.asarray(paths.a[0]) + 1j * np.asarray(paths.a[1])).reshape(2, 2)
                err = float(np.linalg.norm(actual - expected) / np.linalg.norm(expected))
                derr = float(abs(np.asarray(paths.tau).ravel()[0] - dist / C0))
                results.append(dict(position=pos, yaw_deg=yaw, bin=fi, relative_complex_error=err, delay_error_s=derr,
                                    passed=bool(err < 1e-4 and derr < 1e-12)))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "LOS_CHECK.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(dict(los_check_cases=len(results), passed=sum(r["passed"] for r in results),
                          max_relative_error=max(r["relative_complex_error"] for r in results))))
    assert all(r["passed"] for r in results), "FFD_ROTATION_LOS_CHECK_FAILED"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--position", type=int, default=0)
    ap.add_argument("--xy", type=float, nargs=2, help="robot x y in metres (overrides --position)")
    ap.add_argument("--tag", help="output file prefix (default position_<N>)")
    ap.add_argument("--yaws", type=float, nargs="*")
    ap.add_argument("--bin-stride", type=int, default=1)
    ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--los-check", action="store_true")
    ap.add_argument("--anchor-x", type=float, default=None, help="ceiling anchor x in metres (default: CorridorSetup default, 4.0)")
    ap.add_argument("--anchor-y", type=float, default=None, help="ceiling anchor y in metres (default 0.0)")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    dr.set_thread_count(args.threads)
    over = {k: v for k, v in (("anchor_x_m", args.anchor_x), ("anchor_y_m", args.anchor_y)) if v is not None}
    setup = CorridorSetup(**over)
    assert all(c["passed"] for c in setup.validate()), "SETUP_VALIDATION_FAILED"
    cfg = json.loads(SOLVER_SOURCE.read_text())["solver"]
    banks = load_banks()
    (args.out / "SETUP_SNAPSHOT.json").write_text(json.dumps(setup.snapshot(), indent=2))
    if args.los_check:
        los_check(args, setup, banks)
    else:
        run_sweep(args, setup, cfg, banks)


if __name__ == "__main__":
    main()
