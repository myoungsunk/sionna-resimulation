"""Narrow RF regression: Sionna RT 2.0.1 applies ONE full slab (ITU-R P.2040 single layer) per intersected sheet.

For each material/thickness the office uses, a straight line crosses (a) one flat sheet and (b) a closed box made of two parallel sheets. The complex ratio
of the refracted straight path to the free-space LoS path is compared with the analytic slab transmission coefficient T (TM, the polarization of the
vertically polarised iso antennas in the plane of incidence). (a) must equal T; (b) shows that a closed box applies the slab twice (T squared).
Requires the Sionna environment.      python scripts/office_slab_check.py --out DIR
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import mitsuba as mi

mi.set_variant("llvm_ad_mono_polarized")
import sionna.rt as rt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from qclean_uwb.features import specular_model as sm  # noqa: E402
from qclean_uwb.scenarios.ply import write_ply  # noqa: E402
from qclean_uwb.scenarios.office import MATERIALS, box_quads  # noqa: E402

C0 = 299792458.0
F = 6.25e9


def run(tmp: Path, sheets, mat, thick, tx, rx):
    scene = rt.load_scene()
    objs = []
    for i, q in enumerate(sheets):
        ply = tmp / f"s{i}.ply"
        write_ply(ply, q)
        objs.append(rt.SceneObject(fname=str(ply), name=f"s{i}", radio_material=rt.ITURadioMaterial(name=f"m{i}", itu_type=mat, thickness=thick)))
    if objs:
        scene.edit(add=objs)
    scene.frequency = F
    scene.tx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
    scene.rx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
    scene.add(rt.Transmitter("tx", position=list(tx)))
    scene.add(rt.Receiver("rx", position=list(rx)))
    p = rt.PathSolver()(scene, max_depth=2, los=True, specular_reflection=True, refraction=True)
    a = (np.asarray(p.a[0]) + 1j * np.asarray(p.a[1])).ravel()
    tau = np.asarray(p.tau).ravel()
    return a, tau


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    big = 3.0
    horiz = lambda z: np.array([[-big, -big, z], [big, -big, z], [big, big, z], [-big, big, z]], float)
    vert = lambda x: np.array([[x, -big, -big], [x, big, -big], [x, big, big], [x, -big, big]], float)
    cases = []
    for group in ("partitions", "desks", "outer_walls", "floor"):
        mat, d = MATERIALS[group]
        for orient in ("horizontal", "vertical"):
            tx, rx = ((0.0, 0.0, 1.0), (0.5, 0.0, -1.0)) if orient == "horizontal" else ((1.0, 0.0, 0.0), (-1.0, 0.0, 0.5))
            sheet = horiz(0.0) if orient == "horizontal" else vert(0.0)
            dist = float(np.linalg.norm(np.subtract(rx, tx)))
            theta = float(np.arccos(abs(np.dot((np.subtract(rx, tx)) / dist, [0, 0, 1] if orient == "horizontal" else [1, 0, 0]))))
            eta = sm.eta_complex(mat, F)
            t_te, t_tm = sm.slab_transmission(np.cos(theta), eta, d, C0 / F)
            a_free, _ = run(args.out, [], mat, d, tx, rx)
            a_one, tau_one = run(args.out, [sheet], mat, d, tx, rx)
            straight = np.argmin(abs(tau_one - dist / C0))
            ratio_one = a_one[straight] / a_free[0]
            # closed box: two parallel faces, the box thickness along the line is 0.2 m
            lo = np.array([-big, -big, -0.1]) if orient == "horizontal" else np.array([-0.1, -big, -big])
            hi = np.array([big, big, 0.1]) if orient == "horizontal" else np.array([0.1, big, big])
            faces = box_quads(lo, hi)
            a_box, tau_box = run(args.out, faces, mat, d, tx, rx)
            ratio_box = a_box[np.argmin(abs(tau_box - dist / C0))] / a_free[0]
            cases.append(dict(group=group, material=mat, thickness_m=d, orientation=orient, incidence_deg=round(float(np.degrees(theta)), 2),
                              T_tm=[float(t_tm.real), float(t_tm.imag)], sionna_one_sheet=[float(ratio_one.real), float(ratio_one.imag)],
                              rel_err_one_sheet=float(abs(ratio_one - t_tm) / abs(t_tm)),
                              sionna_closed_box=[float(ratio_box.real), float(ratio_box.imag)], T_squared=[float((t_tm ** 2).real), float((t_tm ** 2).imag)],
                              rel_err_box_vs_T2=float(abs(ratio_box - t_tm ** 2) / abs(t_tm ** 2)), rel_err_box_vs_T=float(abs(ratio_box - t_tm) / abs(t_tm))))
    ok = all(c["rel_err_one_sheet"] < 1e-4 for c in cases)
    (args.out / "SLAB_CHECK.json").write_text(json.dumps(dict(passed=bool(ok), tolerance=1e-4, frequency_hz=F, cases=cases), indent=1, default=float))
    for c in cases:
        print(f"{c['group']:12s} {c['orientation']:10s} one sheet err {c['rel_err_one_sheet']:.1e} | closed box vs T^2 {c['rel_err_box_vs_T2']:.1e}, vs T {c['rel_err_box_vs_T']:.2f}")
    print("PASSED" if ok else "FAILED")
    if not ok:
        raise SystemExit("SINGLE_SLAB_REGRESSION_FAILED")


if __name__ == "__main__":
    main()
