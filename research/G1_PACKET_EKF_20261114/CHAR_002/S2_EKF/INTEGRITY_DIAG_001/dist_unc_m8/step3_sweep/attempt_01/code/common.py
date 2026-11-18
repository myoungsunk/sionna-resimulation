import sys, json, numpy as np
from pathlib import Path
M="/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001/m7_final_model_stage1"
sys.path.insert(0,M)
import m7_replay as R7
A2=Path(M)/"attempt_02"
CON=json.load(open(A2/"replay/RUN_CONTRACT.json"))
PARAMS=CON["parameters"]
KEYS=("t","pose_id","z","muMB","muBASE","R","D","x0","P0","ds","gy","dt")
def packet(cond,seed,route):
    src="L2_GYRO_ARW" if cond=="L2_GYRO_ARW_Q_B0_STRESS" else cond  # M7: stress reuses L2 online inputs
    Z=np.load(A2/f"input_generation/inputs/{src}/seed{seed}/{route}_online.npz")
    return {k:Z[k] for k in KEYS}
def m7trace(cond,mode,seed,route,arm):
    return np.load(A2/f"replay/cells/{cond}/{mode}/seed{seed}/{route}/{arm}/trace.npz")
_env=None
def env():
    global _env
    if _env is None: _env=R7.load_environment("/home/claude/m8/base.json")
    return _env

# ---------- scoring (M7 pinned scorer modules, located in repo by hash) ----------
import hashlib, importlib
S2="/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF"
I1=S2+"/INTEGRITY_DIAG_001"
for d in [S2, I1+"/continuation_d2_d3", I1+"/continuation_ks", I1+"/final_model_stage0/inputs"]:
    if d not in sys.path: sys.path.insert(0,d)
SCON=json.load(open(A2/"scoring/RUN_CONTRACT.json"))
def _sha(p): return hashlib.sha256(open(p,"rb").read()).hexdigest()
_scorers=None
def scorers():
    global _scorers
    if _scorers is None:
        pins={f["path"].replace("\\","/").split("/")[-1]:f["sha256"] for f in SCON["scorer_assets"]["files"]}
        mods=[importlib.import_module(m) for m in ("verify_s2","ks_diagnostics","exposure_score","metrics_s2")]
        for m in mods:
            n=Path(m.__file__).name
            assert _sha(m.__file__)==pins[n], f"scorer hash mismatch {n}"
        _scorers=(mods[0].from_trace, mods[1].scores_with_blocks, mods[2].branch_metrics)
    return _scorers
TRUTH={}
for r in ("R2","R4","R5"):
    p=f"/home/claude/rel/{r}_B0_Full_10__evaluator.npz"
    assert _sha(p)==SCON["evaluator_inputs"][r]["sha256"]
    Z=np.load(p); TRUTH[r]=dict(truth=Z["truth"],t=Z["t"],pose_id=Z["pose_id"])
def m7_kwargs(arm,route,cond,mode="own",seed=None):
    P=PARAMS[route]
    kw=dict(sigma_b=P["sigma_b"],condition=cond,rref_policy="own",sigma_rad=P["sigma_rad"] if arm in("H3","H4") else 0.)
    if arm in("H3","H5","H5P"): kw["q_table"]=P["qprime_table"] if arm=="H5P" else P["q_table"]
    if mode=="fixed": kw["fixed_mask"]=fixed_mask(route)
    return kw
_FM={}
def fixed_mask(route):
    if route not in _FM:
        rec=CON["fixed_masks"][route]; p=f"{I1}/attempt_02/d0/B_B0_{route}.npz"
        assert _sha(p)==rec["sha256"], "fixed mask hash"
        _FM[route]=np.load(p)[rec["field"]].astype(bool)
    return _FM[route]

FIT=json.load(open("/home/claude/m8/FIT_TABLES.json"))
def table(route):
    t=FIT["tables"][route]
    return dict(edges=[t[0]["lo"]]+[r["hi"] for r in t], c1=[r["c1"] for r in t], c0=[r["c0"] for r in t])
