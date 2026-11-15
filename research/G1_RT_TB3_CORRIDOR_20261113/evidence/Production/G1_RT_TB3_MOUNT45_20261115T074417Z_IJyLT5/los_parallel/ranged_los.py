import time
import numpy as np
def run_los(trace, np, setup, load_scene, poses, out, start, stop):
    """Evaluate all 257 bins with the original BLOCK_C direct LoS path."""
    C, rt = trace.C, trace.rt
    cfg = dict(max_depth=0, los=True, specular_reflection=False, refraction=False,
               diffuse_reflection=False, diffraction=False, seed=42)
    t0 = time.monotonic()
    scene, _ = load_scene(setup, None)
    banks = C.load_banks()
    freqs = banks[0]["freqs_hz"][start:stop]
    txp, rxp = C.make_ports(banks)
    scene.add(rt.Transmitter("tx", position=setup.anchor_position.tolist(),
                             orientation=C.euler(C.ANCHOR_ROTATION)))
    for i, p in enumerate(poses):
        scene.add(rt.Receiver(f"rx_{i}", position=setup.robot_position(p["x"], p["y"]).tolist(),
                              orientation=C.euler(setup.robot_rotation(p["yaw_body_deg"]))))
    solver = rt.PathSolver()
    shape = (len(poses), len(freqs))
    coeff = np.empty((*shape, 2, 2), dtype=np.complex128)
    h = np.empty_like(coeff)
    tau = np.empty(shape)
    angles = {name: np.empty(shape) for name in ("theta_t", "phi_t", "theta_r", "phi_r")}
    counts = np.ones(shape, dtype=int)
    for fi, f in enumerate(freqs):
        C.set_bin(scene, banks, txp, rxp, start + fi, f)
        paths = solver(scene, **cfg)
        a = (np.asarray(paths.a[0]) + 1j * np.asarray(paths.a[1])).reshape(len(poses), 2, 2, -1)
        delay = np.asarray(paths.tau).reshape(len(poses), -1)
        if a.shape[-1] != 1 or delay.shape[1] != 1 or np.any(delay < 0):
            raise ValueError(f"Expected one valid direct path at bin {fi}")
        coeff[:, fi] = a[:, :, :, 0]
        tau[:, fi] = delay[:, 0]
        h[:, fi] = (a * np.exp(-2j * np.pi * f * delay)[:, None, None, :]).sum(-1)
        for name in angles:
            angles[name][:, fi] = np.asarray(getattr(paths, name)).reshape(len(poses), -1)[:, 0]
        if fi % 8 == 0 or fi + 1 == len(freqs):
            print(f"LoS bin {fi + 1}/{len(freqs)}", flush=True)
    if not all(np.isfinite(a).all() for a in [h, tau, *angles.values()]):
        raise ValueError("Non-finite LoS output")
    np.save(out / "H_LoS.npy", h)
    np.savez_compressed(out / "PATHS_LoS.npz", a=coeff, tau=tau, counts=counts,
                        interactions=np.zeros_like(counts), **angles, freqs_hz=freqs)
    return dict(wall_s=time.monotonic() - t0, solver=cfg, bins=len(freqs),
                frequency_hz=[float(freqs[0]), float(freqs[-1])], paths_per_pose_bin=1)
