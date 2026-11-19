"""M8 Step 3 Phase B input generator (proposer-side reproduction of m7_inputs.generate_inputs).

Same law as m7_final_model_stage1/m7_inputs.py: frozen sensor_v2/sensors modules (hash-checked
against the M7 RUN_CONTRACT), paired B0 (N=.015) / L2 (N=.060 deg/sqrt s) configs, RF fields copied
from the frozen reference packet, x0 ~ truth[0] + rng(seed,'initial')*[.1,.1,5deg].
Only the seed grid differs.

  python gen_inputs_ext.py parity            # regenerate 10-29, compare bit-exact to M7 inputs
  python gen_inputs_ext.py generate 30 49    # write seeds 30-49 to inputs_ext/
"""
import sys, json, math, hashlib, importlib.util, types
from dataclasses import replace, asdict
from pathlib import Path
import numpy as np

M = Path("/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001/m7_final_model_stage1")
IG = M / "attempt_02/input_generation"
FROZEN = Path("/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/MOUNT45_VALIDATION_20261116/frozen_inputs/G1_CHAR002_S2_INPUTS_20261115")
REL = Path("/home/claude/rel")
OUT = Path("/home/claude/m8/inputs_ext")
KEYS = ("t", "pose_id", "P0", "z", "muMB", "muBASE", "R", "D", "ds", "gy", "dt", "x0")
RF = ("t", "pose_id", "z", "muMB", "muBASE", "R", "D")
ROUTES = ("R2", "R4", "R5")
CONDS = ("B0", "L2_GYRO_ARW")


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def arrays(p):
    with np.load(p, allow_pickle=False) as d: return {k: d[k].copy() for k in d.files}


CON = json.load(open(IG / "RUN_CONTRACT.json"))


def load_sensor():
    pins = {n: CON["model_assets"][f"src/qclean_uwb/drivesim/{n}.py"]["sha256"] for n in ("sensors", "sensor_v2")}
    prefix = "_m8_frozen_sensor"; pkg = types.ModuleType(prefix); pkg.__path__ = []; sys.modules[prefix] = pkg
    mod = None
    for n in ("sensors", "sensor_v2"):
        [p] = [q for q in FROZEN.glob(f"*_{n}.py")]
        assert sha(p) == pins[n], f"hash mismatch {n}"
        spec = importlib.util.spec_from_file_location(f"{prefix}.{n}", p)
        mod = importlib.util.module_from_spec(spec); sys.modules[spec.name] = mod; spec.loader.exec_module(mod)
    return mod, pins


def configs(S):
    b0 = S.SensorV2Config(level=1, condition="noise_pair", common_scale=0., bias_rw_rad_s_sqrt_s=0.)
    assert math.isclose(math.radians(.015), b0.gyro_N_rad_sqrt_s, rel_tol=0., abs_tol=1e-15)
    l2 = replace(b0, gyro_N_rad_sqrt_s=math.radians(.060))
    assert {k for k in asdict(b0) if asdict(b0)[k] != asdict(l2)[k]} == {"gyro_N_rad_sqrt_s"}
    return b0, l2


def route_inputs(route):
    cell = {c["route"]: c for c in CON["cells"]}[route]
    p = REL / f"{route}_B0_Full_10__online.npz"
    assert sha(p) == cell["online"]["sha256"], "reference online hash"
    ref = {k: v for k, v in arrays(p).items() if k in KEYS}
    e = REL / f"{route}_B0_Full_10__evaluator.npz"
    assert sha(e) == CON["evaluator_inputs"][route]["sha256"], "evaluator hash"
    ev = arrays(e)
    for k in ("t", "pose_id"): np.testing.assert_array_equal(ref[k], ev[k])
    return ref, ev["truth"]


def initial(S, truth, seed):
    x0 = truth[0] + S.rng(seed, "initial").standard_normal(3) * [.1, .1, math.radians(5.)]
    x0[2] = (x0[2] + math.pi) % (2 * math.pi) - math.pi
    return np.r_[x0, 0.], np.diag([.1**2, .1**2, math.radians(5.)**2, math.radians(.1)**2])


def make(S, cfg, cfg2, ref, truth, seed):
    ds, ang = S.motion_increments(ref["t"], truth, convention="legacy-euler")
    c0, lat0 = S.generate(ref["t"], ds, ang, cfg, seed)
    c2, lat2 = S.generate(ref["t"], ds, ang, cfg2, seed)
    for k in c0:
        if k != "dtheta_gyro": np.testing.assert_array_equal(c0[k], c2[k])
    x0, p0 = initial(S, truth, seed)
    b0 = {k: ref[k].copy() for k in KEYS}
    b0.update(ds=c0["ds_odom"], gy=c0["dtheta_gyro"], dt=c0["dt_s"], x0=x0, P0=p0)
    l2 = {k: b0[k].copy() for k in KEYS}; l2["gy"] = c2["dtheta_gyro"]
    # oracle checks (same as m7_inputs._check_pair)
    dt = np.r_[0., np.diff(b0["t"])]; np.testing.assert_array_equal(b0["dt"], dt)
    w = S.rng(seed, "gyro").standard_normal(len(dt)) * cfg.gyro_N_rad_sqrt_s * np.sqrt(dt); w[0] = 0.
    clean = np.r_[0., (np.diff(truth[:, 2]) + np.pi) % (2 * np.pi) - np.pi]
    np.testing.assert_allclose(b0["gy"] - clean, w, atol=1e-10, rtol=0)
    np.testing.assert_allclose(l2["gy"] - clean, 4 * w, atol=1e-10, rtol=0)
    for k in RF: np.testing.assert_array_equal(b0[k], ref[k])
    assert not lat0["true_bias_rad_s"].any() and not lat2["true_bias_rad_s"].any()
    return b0, l2


def main():
    S, pins = load_sensor(); cfg, cfg2 = configs(S)
    cmd = sys.argv[1]
    report = dict(command=sys.argv, sensor_pins=pins, numpy=np.__version__, law="m7_inputs.generate_inputs")
    if cmd == "parity":
        res = {}
        for r in ROUTES:
            ref, truth = route_inputs(r)
            for s in range(10, 30):
                pk = make(S, cfg, cfg2, ref, truth, s)
                for cond, p in zip(CONDS, pk):
                    old = arrays(IG / f"inputs/{cond}/seed{s}/{r}_online.npz")
                    assert set(old) == set(KEYS)
                    err = {k: float(np.max(np.abs(old[k] - p[k]))) for k in KEYS}
                    res[f"{cond}/seed{s}/{r}"] = dict(bit_exact=[k for k in KEYS if err[k] == 0.],
                                                      max_abs=dict((k, e) for k, e in err.items() if e))
        mx = max((e for v in res.values() for e in v["max_abs"].values()), default=0.)
        diffk = sorted({k for v in res.values() for k in v["max_abs"]})
        ok = mx <= 1e-10
        report.update(status="PASS_TOL_1e-10" if ok else "FAIL", m7_tol=1e-10, max_abs_diff=mx,
                      fields_not_bit_exact=diffk,
                      note="ds differs at ulp level (Windows vs Linux libm sin/cos in motion_increments); gy/x0/P0/RF bit-exact",
                      total=len(res), cells=res)
        print(report["status"], mx, diffk, len(res))
        json.dump(report, open("/home/claude/m8/INPUT_PARITY_10_29.json", "w"), indent=1)
    elif cmd == "generate":
        lo, hi = int(sys.argv[2]), int(sys.argv[3])
        assert lo >= 30, "never overwrite/duplicate the frozen M7 grid"
        idx = {c: {} for c in CONDS}; offs = {}
        for r in ROUTES:
            ref, truth = route_inputs(r)
            for s in range(lo, hi + 1):
                pk = make(S, cfg, cfg2, ref, truth, s)
                offs.setdefault(r, []).append(tuple(pk[0]["x0"] - np.r_[truth[0], 0.]))
                for cond, p in zip(CONDS, pk):
                    path = OUT / cond / f"seed{s}" / f"{r}_online.npz"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open("xb") as h: np.savez_compressed(h, **p)
                    idx[cond].setdefault(str(s), {})[r] = dict(path=str(path.relative_to(OUT)), sha256=sha(path))
        for r, o in offs.items(): assert len(set(o)) == len(o), "repeated initial offsets"
        report.update(status="PASS_EXECUTION", seeds=[lo, hi], index=idx,
                      input_aliases={"L2_GYRO_ARW_Q_B0_STRESS": "L2_GYRO_ARW"})
        json.dump(report, open(OUT / ("INPUT_INDEX_EXT.json" if lo == 30 else f"INPUT_INDEX_EXT_{lo}_{hi}.json"), "x"), indent=1)
        print("generated", sum(len(v) for c in idx.values() for v in c.values()))


if __name__ == "__main__":
    main()
