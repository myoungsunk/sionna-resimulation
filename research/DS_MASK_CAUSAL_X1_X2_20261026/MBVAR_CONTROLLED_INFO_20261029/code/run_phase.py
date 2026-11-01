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
          "P2_S1V2_REEVAL": dict(mode="frozen", gate="G3"), "P2_C2": dict(mode="frozen", gate="G3"),
          "P2_S1V3": dict(mode="frozen", gate="G3"), "P2_C3": dict(mode="frozen", gate="G3"),
          "P2_S1V4": dict(mode="frozen", gate="G3"), "P2_C3V4": dict(mode="frozen", gate="G3"),
          "P2_BTAP": dict(mode="frozen", gate="G3"), "P2_RFRES": dict(mode="frozen", gate="G3"),
          "P2_A010P0_GEN": dict(mode="frozen", gate="G3"), "P2_A010P0_ABL": dict(mode="frozen", gate="G3"),
          "P2_S1V5": dict(mode="frozen", gate="G3"), "P2_C3V5": dict(mode="frozen", gate="G5")}


def request():
    r = json.loads(REQ.read_text())
    if r.get("phase") not in PHASES:
        raise SystemExit(f"ERR_ROLE_ROUTING: phase {r.get('phase')} not runnable in this workflow (RT phases need a signed pre-P3 amendment)")
    if r.get("role") != "IMPLEMENTER" or r.get("contract_id") != "MBVAR-INFO-001":
        raise SystemExit("ERR_ROLE_ROUTING: role/contract")
    if r["phase"] in ("P2_S1V5", "P2_C3V5"):
        # Early fail closed, before any DEV3 shard is scheduled. The science
        # amendment and source hash lock still need independent signoff.
        science = (EXP / "contracts/AMENDMENT-010.md").read_text()
        if '"status": "FROZEN"' not in science or "AMENDMENT_LOCK" not in science:
            raise SystemExit("ERR_A010_UNFROZEN_NO_DEV3")
        if r.get("split") != "DEV3":
            raise SystemExit("ERR_A010_SPLIT_DEV3_REQUIRED")
        fs = r.get("field_ids") if r["phase"] == "P2_S1V5" else r.get("c3_fields")
        if sorted(fs or []) != list(range(20, 30)):
            raise SystemExit("ERR_A010_DEV3_FIELD_SET")
    return r


def plan():
    r = request(); ph = r["phase"]
    shards = ["all"]
    if ph == "P0_GEO2":
        shards = ["geo"] + [f"c1:{f}" for f in r["c1_fields"]]
    if ph == "P2_C2":
        shards = [f"{f}:{g}" for f in r["c2_fields"] for g in ("LH", "RV")]
    if ph in ("P2_C3", "P2_C3V4", "P2_C3V5"):
        shards = [f"{f}:{g}" for f in r["c3_fields"] for g in ("LH", "RV")]
    if ph == "P2_BTAP":
        shards = [str(f) for f in r["field_ids"]]
    if ph == "P2_A010P0_ABL":
        shards = [f"{k}:{rep}" for k in r["a010p0_cases"] for rep in r["a010p0_reps"]]
    if ph in ("P2_S1", "P2_S1V2", "P2_S1V3", "P2_S1V4", "P2_S1V5"):
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
    elif ph == "P2_C2":
        f, g = shard.split(":")
        cmd = [sys.executable, str(HERE / "c2_conv.py"), "run", "--field", f, "--group", g, "--out", str(out)]
    elif ph == "P2_C3":
        f, g = shard.split(":")
        cmd = [sys.executable, str(HERE / "c3_verify.py"), "run", "--field", f, "--group", g, "--out", str(out)]
        env["S1V3_RUN"] = r["s1v3_run"]
    elif ph == "P2_S1V3":
        cmd = [sys.executable, str(HERE / "s1v3.py"), "run", "--fields", shard, "--split", r["split"], "--out", str(out)]
    elif ph == "P2_S1V4":
        cmd = [sys.executable, str(HERE / "s1v4.py"), "run", "--fields", shard, "--split", r["split"], "--out", str(out)]
    elif ph == "P2_S1V5":
        cmd = [sys.executable, str(HERE / "s1v5.py"), "run", "--fields", shard, "--split", r["split"], "--out", str(out)]
    elif ph == "P2_C3V5":
        f, g = shard.split(":")
        cmd = [sys.executable, str(HERE / "c3v5.py"), "run", "--field", f, "--group", g, "--out", str(out)]
        env["S1V5_RUN"] = r["s1v5_run"]
    elif ph == "P2_C3V4":
        f, g = shard.split(":")
        cmd = [sys.executable, str(HERE / "c3v4.py"), "run", "--field", f, "--group", g, "--out", str(out)]
        env["S1V4_RUN"] = r["s1v4_run"]
    elif ph == "P2_BTAP":
        cmd = [sys.executable, str(HERE / "b_tap.py"), "run", "--fields", shard, "--out", str(out)]
    elif ph == "P2_RFRES":
        cmd = [sys.executable, str(HERE / "c_rfres.py"), "run", "--out", str(out)]
    elif ph == "P2_A010P0_GEN":
        cmd = [sys.executable, str(HERE / "a10_p0.py"), "gen", "--out", str(out)]
    elif ph == "P2_A010P0_ABL":
        k, rep = shard.split(":")
        cmd = [sys.executable, str(HERE / "a10_p0.py"), "abl", "--case", k, "--rep", rep, "--out", str(out)]
        env["A010_GEN_RUN"] = r["a010_gen_run"]
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
    if ph == "P2_C2":
        env["S1V2_DEV_RUN"] = r["s1v2_dev_run"]
        return subprocess.call([sys.executable, str(HERE / "c2_conv.py"), "aggregate", "--shards", shards, "--out", out], env=env)
    if ph == "P2_C3":
        env["S1V3_RUN"] = r["s1v3_run"]
        return subprocess.call([sys.executable, str(HERE / "c3_verify.py"), "aggregate", "--shards", shards, "--out", out], env=env)
    if ph == "P2_C3V5":
        env["S1V5_RUN"] = r["s1v5_run"]
        return subprocess.call([sys.executable, str(HERE / "c3v5.py"), "aggregate", "--shards", shards, "--out", out], env=env)
    if ph == "P2_S1V5":
        env["S0V2_RESULTS_DIR"] = str(EXP / r["s0v2_results"])
        return subprocess.call([sys.executable, str(HERE / "s1v5.py"), "aggregate", "--shards", shards, "--split", r["split"], "--out", out], env=env)
    if ph == "P2_C3V4":
        env["S1V4_RUN"] = r["s1v4_run"]
        return subprocess.call([sys.executable, str(HERE / "c3v4.py"), "aggregate", "--shards", shards, "--out", out], env=env)
    if ph == "P2_S1V4":
        env["S0V2_RESULTS_DIR"] = str(EXP / r["s0v2_results"])
        return subprocess.call([sys.executable, str(HERE / "s1v4.py"), "aggregate", "--shards", shards, "--split", r["split"], "--out", out], env=env)
    if ph == "P2_BTAP":
        env["S0V2_RESULTS_DIR"] = str(EXP / r["s0v2_results"])
        return subprocess.call([sys.executable, str(HERE / "b_tap.py"), "aggregate", "--shards", shards, "--out", out], env=env)
    if ph == "P2_RFRES":
        return subprocess.call([sys.executable, str(HERE / "c_rfres.py"), "aggregate", "--shards", shards, "--out", out], env=env)
    if ph == "P2_A010P0_GEN":                    # single shard: copy its outputs, then write the phase manifest
        import glob as _g, shutil as _sh
        Path(out).mkdir(parents=True, exist_ok=True)
        for f in _g.glob(str(Path(shards) / "**" / "A010_*"), recursive=True):
            _sh.copyfile(f, Path(out) / Path(f).name)
        return subprocess.call([sys.executable, "-c", "import sys; sys.path.insert(0, %r); import a10_p0 as A; raise SystemExit(A.cmd_gen_manifest(%r))" % (str(HERE), str(out))], env=env)
    if ph == "P2_A010P0_ABL":
        env["A010_GEN_RUN"] = r["a010_gen_run"]
        return subprocess.call([sys.executable, str(HERE / "a10_p0.py"), "aggregate", "--shards", shards, "--out", out], env=env)
    if ph == "P2_S1V3":
        env["S0V2_RESULTS_DIR"] = str(EXP / r["s0v2_results"])
        return subprocess.call([sys.executable, str(HERE / "s1v3.py"), "aggregate", "--shards", shards, "--split", r["split"], "--out", out], env=env)
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
