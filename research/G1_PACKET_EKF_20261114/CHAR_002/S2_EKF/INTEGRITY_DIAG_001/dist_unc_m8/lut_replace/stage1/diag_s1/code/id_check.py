import sys, json, numpy as np
sys.path.insert(0, "/home/claude/m8"); sys.path.insert(0, "/home/claude/lut0"); sys.path.insert(0, "/home/claude/lut1")
from common import packet, env
import m8_replay as M0, m8_replay_lut as M1, h_ref as HR
from run_m8s3 import sweep_packet, ZERO_SB
from run_c0 import krige_fn
e0 = env(); eF = HR.swap_env(e0, HR.ffd_s_fn(e0["model"])); spec = e0["spec"]; base = e0["model"]
aF = lambda nav: float(base.batch(np.asarray(nav, float)[None], spec)[1][0, 1, 2])
B = np.load("/home/claude/lut0/S0ID_CAL.npz"); VT = json.load(open("/home/claude/lut0/S0ID_TABLES.json"))["tableV"]
es = np.load("/home/claude/lut0/ES_FFDREF_CORRIDOR.npy"); vtab = dict(edges=VT["edges"], c1=VT["c1"], c0=VT["c0"])
out = {}
for r in ("R2", "R4", "R5"):
    p = packet("B0", 10, r); ps = sweep_packet(p, B[f"{r}/mu_r"], B[f"{r}/mu_s"], B[f"{r}/Rrr"], B[f"{r}/Rss"])
    kw = dict(table=vtab, sigma_b=ZERO_SB, condition="B0", mu_s_fn=krige_fn(es, B[f"{r}/mu_s"]), **M0.ARM_MODES["F2"])
    t0 = M0.replay_m8(ps, eF, "F2SKRWV", **kw); t1 = M1.replay_m8(ps, eF, "F2SKRWV", **kw); t2 = M1.replay_m8(ps, eF, "F2SKRWV", a_fn=aF, **kw)
    eq = lambda u, v: all(np.array_equal(u[k], v[k]) for k in u if not k.startswith("metadata"))
    out[r] = dict(nohook_bitident=bool(eq(t0, t1)), ffd_hook_bitident=bool(eq(t0, t2)),
                  ffd_hook_maxdiff_x=float(np.abs(t0["x"] - t2["x"]).max()))
print(json.dumps(out, indent=1)); json.dump(out, open("/home/claude/lut1/ID_CHECK_A_FN.json", "w"), indent=1)
