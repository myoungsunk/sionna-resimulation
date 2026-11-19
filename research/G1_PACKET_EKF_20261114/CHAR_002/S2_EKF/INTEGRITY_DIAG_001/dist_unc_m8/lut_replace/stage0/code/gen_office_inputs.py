"""Office online inputs, same law as o3_build.inputs() (frozen sensor_v2 via gen_inputs_ext, legacy-euler increments,
x0 = truth[0] + rng(seed,'initial')*[.1,.1,5deg]). Routes O01, O02, O03L (O03 RF rows 137-272).
  python gen_office_inputs.py parity          # regenerate seeds 10-29, compare with /home/claude/office/inputs
  python gen_office_inputs.py generate 50 69  # write /home/claude/office/inputs (new seeds only)"""
import sys, json, hashlib, numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/m8")
import gen_inputs_ext as G
O = "/home/claude/office"; RT = np.load(f"{O}/O3_ROUTES.npz"); F = pd.read_csv(f"{O}/OFFICE_ROUTE_FEATURES.csv.gz")
S, _ = G.load_sensor(); cfg, cfg2 = G.configs(S)
def route_z(name):
    src = "O03" if name == "O03L" else name; f = F[F.route == src].reset_index(drop=True)
    if name == "O03L": f = f.iloc[137:273].reset_index(drop=True)
    return f[["range_m", "s_fp"]].to_numpy()
def inputs(name, seed):
    t, truth, pid = RT[f"{name}/t"], RT[f"{name}/truth"], RT[f"{name}/pose_id"]
    ds, ang = S.motion_increments(t, truth, convention="legacy-euler")
    c0, _ = S.generate(t, ds, ang, cfg, seed); c2, _ = S.generate(t, ds, ang, cfg2, seed); x0, P0 = G.initial(S, truth, seed)
    base = dict(t=t, pose_id=pid, z=route_z(name), x0=x0, P0=P0, ds=c0["ds_odom"], dt=c0["dt_s"])
    return {"B0": dict(base, gy=c0["dtheta_gyro"]), "L2_GYRO_ARW": dict(base, gy=c2["dtheta_gyro"])}
cmd = sys.argv[1]; R = ("O01", "O02", "O03L")
if cmd == "parity":
    bad = []; n = 0
    for r in R:
        for s in range(10, 30):
            for c, p in inputs(r, s).items():
                old = dict(np.load(f"{O}/inputs/{r}_{c}_{s}.npz")); n += 1
                if set(old) != set(p) or any(not np.array_equal(old[k], p[k]) for k in p): bad.append(f"{r}_{c}_{s}")
    res = dict(compared=n, bit_exact=n - len(bad), mismatches=bad[:10], status="PASS" if not bad else "FAIL"); print(res)
    json.dump(res, open("/home/claude/lut0/OFFICE_INPUT_PARITY_10_29.json", "w"), indent=1)
else:
    lo, hi = int(sys.argv[2]), int(sys.argv[3]); assert lo >= 30; idx = {}
    for r in R:
        for s in range(lo, hi + 1):
            for c, p in inputs(r, s).items():
                path = f"{O}/inputs/{r}_{c}_{s}.npz"
                with open(path, "xb") as h: np.savez(h, **p)
                idx[f"{r}_{c}_{s}"] = hashlib.sha256(open(path, "rb").read()).hexdigest()
    json.dump(dict(seeds=[lo, hi], files=idx), open(f"/home/claude/lut0/OFFICE_INPUT_INDEX_{lo}_{hi}.json", "x"), indent=1); print("generated", len(idx))
