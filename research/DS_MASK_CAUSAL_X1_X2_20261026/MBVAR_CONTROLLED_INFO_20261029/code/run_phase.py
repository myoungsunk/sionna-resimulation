"""Phase dispatcher for the run workflow.

  run_phase.py plan                                  -> prints {"phase","matrix","contract_mode","gate"} from RUN_REQUEST.json
  run_phase.py run --shard <id> --out <dir>          -> executes one shard of the requested phase
  run_phase.py aggregate --shards <dir> --out <dir>  -> merges shards, writes phase outputs + MANIFEST.json
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
REQ = EXP / "RUN_REQUEST.json"
PHASES = {"P0_PREFLIGHT": dict(mode="draft", gate="G1"), "P1_S0": dict(mode="frozen", gate="G2"),
          "P2_S1": dict(mode="frozen", gate="G3"), "P0_GEO2": dict(mode="frozen", gate="G2"), "P0_GEO2_REEVAL": dict(mode="frozen", gate="G2"),
          "P1_S0V2": dict(mode="frozen", gate="G2"), "P2_S1V2": dict(mode="frozen", gate="G3"),
          "P2_S1V2_REEVAL": dict(mode="frozen", gate="G3")}


def request():
    r = json.loads(REQ.read_text())
    if r.get("phase") not in PHASES:
        raise SystemExit(f"ERR_ROLE_ROUTING: phase {r.get('phase')} not runnable in this workflow (RT phases need a signed pre-P3 amendment)")
    if r.get("role") != "IMPLEMENTER" or r.get("contract_id") != "MBVAR-INFO-001":
        raise SystemExit("ERR_ROLE_ROUTING: role/contract")
    return r


def plan():
    r = request(); ph = r["phase"]
    shards = ["all"]
    if ph == "P0_GEO2":
        shards = ["geo"] + [f"c1:{f}" for f in r["c1_fields"]]
    if ph in ("P2_S1", "P2_S1V2"):
        ids = r["field_ids"]; k = int(r.get("n_shards", 8))
        shards = [",".join(map(str, ids[i::k])) for i in range(k) if ids[i::k]]
    print(json.dumps(dict(phase=ph, governance=r["governance_git_sha"], contract_mode=PHASES[ph]["mode"],
                          gate=PHASES[ph]["gate"], matrix=dict(shard=shards))))


def run(shard, out):
    r = request(); ph = r["phase"]; out = Path(out); out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, MBVAR_GOVERNANCE_SHA=r["governance_git_sha"])
    if ph == "P0_PREFLIGHT":
        cmd = [sys.executable, str(HERE / "p0_preflight.py"), "--out", str(out), "--rf-dir", str(Path(os.environ["REFLECT_ROOT"]) / r["rf_dir"]),
               "--draft-contract-sha256", r["draft_contract_sha256"]]
    elif ph == "P1_S0":
        rc = subprocess.call([sys.executable, str(HERE / "s0_math.py"), "--out", str(out)], env=env)
        rc2 = subprocess.call([sys.executable, str(EXP / "audit" / "audit_s0_independent.py"), "--s0", str(out), "--out", str(out)], env=env)
        return rc or rc2
    elif ph == "P0_GEO2":
        cmd = [sys.executable, str(HERE / "p0_geo2.py"), "geo", "--out", str(out)] if shard == "geo" else \
              [sys.executable, str(HERE / "p0_geo2.py"), "c1", "--field", shard.split(":")[1], "--out", str(out)]
    elif ph == "P0_GEO2_REEVAL":
        cmd = [sys.executable, str(HERE / "p0_geo2.py"), "reeval", "--src", r["reeval_source"], "--out", str(out)]
    elif ph == "P2_S1V2_REEVAL":
        cmd = [sys.executable, str(HERE / "s1v2.py"), "reeval", "--src", r["reeval_source"], "--split", r["split"], "--out", str(out)]
    elif ph == "P1_S0V2":
        cmd = [sys.executable, str(HERE / "s0v2.py"), "--out", str(out)]
    elif ph == "P2_S1V2":
        cmd = [sys.executable, str(HERE / "s1v2.py"), "run", "--fields", shard, "--split", r["split"], "--out", str(out)]
    else:
        cmd = [sys.executable, str(HERE / "s1_mc.py"), "run", "--fields", shard, "--split", r["split"], "--out", str(out)]
    print(" ".join(cmd), flush=True)
    return subprocess.call(cmd, env=env)


def aggregate(shards, out):
    r = request(); ph = r["phase"]
    env = dict(os.environ, MBVAR_GOVERNANCE_SHA=r["governance_git_sha"])
    if ph == "P2_S1":
        env["S0_RESULTS_DIR"] = str(EXP / r["s0_results"])
        return subprocess.call([sys.executable, str(HERE / "s1_mc.py"), "aggregate", "--shards", shards, "--split", r["split"],
                                "--out", out], env=env)
    if ph in ("P0_GEO2", "P0_GEO2_REEVAL"):
        return subprocess.call([sys.executable, str(HERE / "p0_geo2.py"), "aggregate", "--shards", shards, "--out", out], env=env)
    if ph in ("P2_S1V2", "P2_S1V2_REEVAL"):
        env["S0V2_RESULTS_DIR"] = str(EXP / r["s0v2_results"])
        return subprocess.call([sys.executable, str(HERE / "s1v2.py"), "aggregate", "--shards", shards, "--split", r["split"], "--out", out], env=env)
    return 0


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("cmd"); ap.add_argument("--shard", default="all")
    ap.add_argument("--out"); ap.add_argument("--shards")
    a = ap.parse_args()
    if a.cmd == "plan":
        plan(); return 0
    if a.cmd == "run":
        return run(a.shard, a.out)
    return aggregate(a.shards, a.out)


if __name__ == "__main__":
    raise SystemExit(main())
