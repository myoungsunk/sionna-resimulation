"""P4 mandatory static audit; no NumPy, RF model, or estimator imported."""
from __future__ import annotations
import argparse, ast, hashlib, json, os, subprocess
from pathlib import Path
from datetime import datetime, timezone
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
WORKFLOW=ROOT/".github/workflows/ekf4-r4-p4-one-step.yml"
P3_SHA="b244c2e399d9d105972a09ce35a2516c71f7e514"
P3_ARTIFACT_SHA="de40cbbef664b064b6c24ac679ffb7238738ceab36995ee4fa156bb99699428b"
RF_ARTIFACT_SHA="88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63"
P3_SOURCE_SHA={
"research/EKF4_RANGE_S_STAGED_20261014/core.py":"1abdac002631e1de2303b0ef7c39c6c9eb619b53d9ba9fd8d89d1a3cd9c630d1",
"research/EKF4_RANGE_S_STAGED_20261014/synthetic.py":"c3fc54d9726beab176971aa8652c0b6f61353f55f596613e4c8150351c4d9643",
"research/EKF4_RANGE_S_STAGED_20261014/P2_SPEC.json":"548258a444c02a3a1d0c2d210b470489560b1bd56ad911cc9ee93d7631b36ce7",
"research/EKF4_RANGE_S_STAGED_20261014/p3_pre_run_audit.py":"901949665ebdd1eb90a5704c0804598df3f1426b1253659633eb7cf59ce4788b",
"research/EKF4_RANGE_S_STAGED_20261014/p3_frozen_inputs.py":"10f6d68f45fccff6d41ed2b2feec5c31927332b4824c67871a132f2261bbf1ea",
"research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py":"dfec050fcc81ff39aed0058a2654b3b845b8d3320437136a3f2317033e5efe22",
"research/EKF4_RANGE_S_STAGED_20261014/p3_parity.py":"bb217fa4b7aa01c7f1fda52636a897b306524ab9ff08cc632fb6437ffb727a1a",
"research/EKF4_RANGE_S_STAGED_20261014/p3_export.py":"16b0f90413b3c21d868311e79f4e82bca042e900fbf36006976b412248fa5a5c",
"research/EKF4_RANGE_S_STAGED_20261014/test_p3_adapter.py":"d871705ef30edc7461dd99a65aa701adfdb6ab933e21d6c1fbba84c21a86c604",
"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json":"462c0bc89e1b55653d289d8a529c1c7022c17a8d954c5ea5740a99092d367455",
"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_meta.json":"8773e79fbb39d07fd80605339a0752e6e4e5eb0658572f091e67395ab0fd5856",
"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy":"711e12ee48a30cb666db4ada749b983de49bd565ea351b906269ec8da375a079"
}
P4_CODES=("p4_pre_run_audit.py","p4_frozen_cases.py","p4_one_step_models.py",
"test_p4_math.py","p4_fixed_replay.py","p4_offline_score.py","p4_archive_audit.py")
PLAN="P4_R4_FROZEN_RF_ONE_STEP_IMPLEMENTATION_PLAN_20261015_KO.md"
def digest(p):
    h=hashlib.sha256()
    with Path(p).open("rb") as f:
        for part in iter(lambda:f.read(1<<20),b""):h.update(part)
    return h.hexdigest()

def require_p4_audit(path):
    if os.environ.get("GITHUB_ACTIONS")!="true":raise RuntimeError("GITHUB_ACTIONS_REQUIRED")
    a=json.loads(Path(path).read_text())
    if a["decision"]!="GO" or a["git_sha"]!=os.getenv("GITHUB_SHA"):
        raise RuntimeError("P4_PREAUDIT_NOT_GO_OR_COMMIT_MISMATCH")
    for rel,expected in a["source_sha256"].items():
        f=ROOT/rel
        if not f.is_file() or digest(f)!=expected:
            raise RuntimeError("P4_SOURCE_CHANGED_AFTER_AUDIT:"+rel)
    return a

def run(out):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    fatal=[];warning=[];source={}
    if os.getenv("GITHUB_ACTIONS")!="true":fatal.append("NOT_GITHUB_ACTIONS")
    try:
        head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
        if head!=os.environ.get("GITHUB_SHA"):fatal.append("GIT_HEAD_NOT_GITHUB_SHA")
        for rel,expected in P3_SOURCE_SHA.items():
            f=ROOT/rel
            if not f.is_file():fatal.append("MISSING_FROZEN:"+rel);continue
            h=digest(f);source[rel]=h
            if h!=expected:fatal.append("P3_FROZEN_SOURCE_CHANGED:"+rel)
        for name in P4_CODES:
            rel="research/EKF4_RANGE_S_STAGED_20261014/"+name
            f=ROOT/rel
            if not f.is_file():fatal.append("P4_CODE_MISSING:"+rel);continue
            source[rel]=digest(f)
            ast.parse(f.read_text(),filename=name)
        plan="research/EKF4_RANGE_S_STAGED_20261014/"+PLAN
        if not (ROOT/plan).exists():fatal.append("FROZEN_P4_PLAN_MISSING")
        else:source[plan]=digest(ROOT/plan)
        if WORKFLOW.is_file():
            wf=WORKFLOW.read_text()
            calls=["p4_pre_run_audit.py --out","p4_frozen_cases.py --archive",
                   "python -m pytest --noconftest -q -s -c research/EKF4_RANGE_S_STAGED_20261014/pytest.ini research/EKF4_RANGE_S_STAGED_20261014/test_p4_math.py","p4_fixed_replay.py --phase canary",
                   "p4_fixed_replay.py --phase fixed","p4_fixed_replay.py --phase map",
                   "p4_offline_score.py --archive","p4_archive_audit.py --"]
            found=[wf.find(v) for v in calls]
            if -1 in found or found!=sorted(found):fatal.append("AUDIT_MODEL_EXECUTION_ORDER")
            if "if: always()" not in wf or "set -euo pipefail" not in wf:
                fatal.append("FAILURE_LOGGING_OR_PIPEFAIL_NOT_ENFORCED")
            if "actions: read" not in wf or "11782748118" not in wf or "11904127597" not in wf:
                fatal.append("INPUT_ARTIFACT_READ_PERMISSION_MISSING")
            source[".github/workflows/ekf4-r4-p4-one-step.yml"]=digest(WORKFLOW)
        else:fatal.append("WORKFLOW_MISSING")
        # This narrow AST audit checks obvious truth usage in the inference
        # functions; the independent scorer is intentionally exempt.
        for name in ("p4_frozen_cases.py","p4_one_step_models.py","p4_fixed_replay.py"):
            txt=(HERE/name).read_text()
            if "truth_for_offline_scoring_only" in txt or "get_offline_truth" in txt:
                fatal.append("P4_TRUTH_LEAKAGE_IN_ESTIMATOR:"+name)
        manifest=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
        if not (len(manifest["assets"])==39 and len(manifest["cases"])==7
                 and len(manifest["routes"])==3):
            fatal.append("P0_MANIFEST_COUNTS_CHANGED")
        warning.extend(["P3 input parity and P2 solver are source SHA bound, not independent science proof.",
            "Single corridor seed0, R0 cross-covariance uncalibrated, P4 one-step only.",
            "Local MAP may be invalid on LUT knots and discontinuous interpolation; do not relax 1e-8."])
    except Exception as e:
        fatal.append("AUDIT_RUNTIME_ERROR:"+repr(e))
    rec={"schema":"EKF4_R4_P4_PRE_EXECUTION_AUDIT_V1",
         "git_sha":os.getenv("GITHUB_SHA"),"run_id":os.getenv("GITHUB_RUN_ID"),
         "status":"GO" if not fatal else "HOLD",
         "decision":"GO" if not fatal else "HOLD",
         "fatal":fatal,"warnings":warning,"source_sha256":source,
         "P3_original_sha":P3_SHA,"P3_archive_sha256":P3_ARTIFACT_SHA,
         "RF_archive_sha256":RF_ARTIFACT_SHA,
         "scientific_PASS":False,"peer_independent_audit":False,
         "created_utc":datetime.now(timezone.utc).isoformat()}
    (out/"P4_PRE_AUDIT.json").write_text(json.dumps(rec,indent=2)+"\n")
    print("P4_PRE_AUDIT "+json.dumps({k:rec[k] for k in ("decision","fatal","git_sha","run_id")}),flush=True)
    return 0 if not fatal else 2
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--out",type=Path,required=True)
    args=p.parse_args();raise SystemExit(run(args.out))
