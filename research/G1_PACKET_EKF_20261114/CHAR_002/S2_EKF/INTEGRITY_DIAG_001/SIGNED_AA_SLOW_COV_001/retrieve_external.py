"""Fetch only explicitly unsealed existing G-T1_B RF. No remote writes/jobs."""
import argparse
import datetime as dt
from pathlib import Path
import subprocess
from p0_inputs_v2 import sha, put


def run(out):
    out.mkdir(exist_ok=False)
    root = "/home/KMS/G1_RT_TB3_PRODUCTION_20261114T101708Z_6ZEqNa/results"
    files = [(f"H/G-T1_B/{f}", f) for f in ["H_full.npy", "H_LoS.npy", "MANIFEST.json"]]
    files += [(f"poses/G-T1_B/{f}", f) for f in ["rf_poses.json", "SAMPLES.json", "SCENE_ENTRY.json"]]
    put(out/"RETRIEVAL_CONTRACT.json", dict(scope="existing unsealed G-T1_B only; metadata/RF read-only", account="Snowball/KMS",
        root=root, files=files, no_G_T2_or_G_V_access=True, timestamp=dt.datetime.now(dt.timezone.utc).isoformat()))
    for remote, name in files:
        assert "G-T1_B/" in remote
        subprocess.run(["scp", "-q", "-o", "BatchMode=yes", "-o", "PasswordAuthentication=no",
                        "Snowball:"+root+"/"+remote, str(out/name)], check=True)
        print(name, (out/name).stat().st_size, flush=True)
    put(out/"RETRIEVAL_RECEIPT.json", {name: sha(out/name) for _, name in files})


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--out", type=Path, required=True); run(ap.parse_args().out)
