"""Re-run every FG-V1 step from this folder and write results/MANIFEST.json (inputs, outputs, sha256, commands, versions, git base)."""
import subprocess, json, hashlib, time, sys, os, platform, glob
from pathlib import Path
HERE = Path(__file__).resolve().parent; FGV1 = HERE.parent; REPO = FGV1.parents[1]
STEPS = [["parity_ekf3.py"], ["surrogate_check.py"], ["r_offdiag_check.py"], ["equivalence_check.py"], ["cir_es_rank_check.py"]] + [["run_lag_inf.py", c, "10", r, "560"] for c in ("B0", "L2_GYRO_ARW") for r in ("R2", "R4", "R5")] + \
        [["diag_r5.py", "B0", "156", "sur"], ["diag_r5_odom.py"], ["diag_r5_meas.py"], ["diag_r5_sur.py"], ["diag_r5_rot.py"], ["diag_r5_decomp.py"]]
only = sys.argv[1:]
def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()
log = []
for st in STEPS:
    if only and st[0] not in only: continue
    t0 = time.time(); r = subprocess.run([sys.executable] + st, cwd=HERE, capture_output=True, text=True)
    log.append(dict(command="python3 " + " ".join(st), returncode=r.returncode, seconds=round(time.time() - t0, 1), stdout_tail=r.stdout.strip().splitlines()[-3:]))
    print(log[-1]["command"], r.returncode, log[-1]["seconds"], flush=True)
I = "research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001"
inputs = sorted(glob.glob(str(REPO / I / "m7_final_model_stage1/attempt_02/input_generation/inputs/*/seed10/*_online.npz"))) + \
         sorted(glob.glob(str(REPO / I / "gm_theta_m6/inputs/*_evaluator.npz"))) + sorted(glob.glob(str(REPO / I / "m7_final_model_stage1/attempt_02/replay/cells/*/own/seed10/R2/H2/trace.npz")))
import gtsam, numpy
man = dict(created_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           git_base=dict(branch="research/g1-sweep-heading-floor-spec-20261113", commit=subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()),
           environment=dict(python=platform.python_version(), gtsam=getattr(gtsam, "__version__", "4.x"), numpy=numpy.__version__, cpus=os.cpu_count()),
           config=dict(state="X=(x,y,psi) world-frame Vector3, no gyro-bias state", odom="ekf3.transition, Q=G diag(2e-5|ds|, (N deg)^2 dt) G^T + 1e-10 I",
                       meas="joint [r,s] factor, R = EKF Reff (packet R + diag(0, sigma_b^2), sigma_b=0.005), EKF 2D NIS gate mask (9.21)",
                       solver="iSAM2 QR, relinearizeThreshold 1e-3, relinearizeSkip 1; causal = latest-node estimate and marginal",
                       surrogate="trilinear h and H on x .5..19.5/.025, y -1..1/.05, psi 4 deg (sur/ffd_grid.npz, sha256 below)",
                       conditions=dict(B0=".015 deg/sqrt(s)", L2_GYRO_ARW=".060 deg/sqrt(s)"), seeds=[10], routes=["R2", "R4", "R5"]),
           inputs={str(Path(p).relative_to(REPO)): sha(p) for p in inputs},
           surrogate_grid_sha256=sha(FGV1 / "sur/ffd_grid.npz") if (FGV1 / "sur/ffd_grid.npz").exists() else "MISSING: run gen_grid.py",
           outputs={str(Path(p).relative_to(FGV1)): sha(p) for p in sorted(glob.glob(str(FGV1 / "results/*.json"))) if not p.endswith("MANIFEST.json")},
           runs=log)
mp = FGV1 / 'results/MANIFEST.json'
if mp.exists():
    old = {r['command']: r for r in json.load(open(mp)).get('runs', [])}
    old.update({r['command']: r for r in log}); man['runs'] = list(old.values())
json.dump(man, open(FGV1 / "results/MANIFEST.json", "w"), indent=1); print("manifest written")
