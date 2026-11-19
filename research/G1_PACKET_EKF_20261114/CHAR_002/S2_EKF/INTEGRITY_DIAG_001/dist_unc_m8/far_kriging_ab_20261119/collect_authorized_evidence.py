"""Collect bounded, read-only Snowball evidence after all four shards finish."""
import datetime
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

EX = Path(__file__).parent
REMOTE = "/home/KMS/FAR_KRIGING_AB_20261119_01a1f269/authorized_explore_01"
OUT = EX / "authorized_exploration_20261119"


def ssh(cmd):
    return subprocess.check_output(["ssh", "-o", "BatchMode=yes", "Snowball", cmd])


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    names = [f"far-authorized-{cond}-{first}-01a1f269"
             for cond in ("B0", "L2_GYRO_ARW") for first in (30, 40)]
    names.append("far-authorized-aggregate-01a1f269")
    names.append("far-authorized-verify-01a1f269")
    inspected = json.loads(ssh("docker inspect " + " ".join(names)))
    for d in inspected:
        assert not d["State"]["Running"] and d["State"]["ExitCode"] == 0, d["Name"]
    OUT.mkdir(exist_ok=False)
    bundle = ssh("tar -cz --exclude=traces -C " + REMOTE + "/results .")
    with tarfile.open(fileobj=io.BytesIO(bundle), mode="r:gz") as tf:
        for member in tf.getmembers():
            if member.isdir():
                continue
            assert member.isfile(), member.name
            target = (OUT / member.name).resolve()
            assert target.is_relative_to(OUT.resolve()), member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(tf.extractfile(member).read())
    containers = []
    for d in inspected:
        name = d["Name"].lstrip("/")
        containers.append(dict(name=name, id=d["Id"], image=d["Image"], state=d["State"],
            command=d["Config"]["Cmd"], user=d["Config"]["User"], mounts=d["Mounts"],
            network=d["HostConfig"]["NetworkMode"],
            nano_cpus=d["HostConfig"]["NanoCpus"], memory=d["HostConfig"]["Memory"],
            environment=[v for v in d["Config"]["Env"]
                if v.startswith(("OPENBLAS_NUM_THREADS=", "OMP_NUM_THREADS=", "PYTHONDONTWRITEBYTECODE="))]))
        (OUT / (name + ".log")).write_bytes(ssh("docker logs " + name))
    runs = [json.loads(p.read_text(encoding="utf-8")) for p in OUT.glob("RUN_*.json")]
    assert len(runs) == 4
    source_commit = {r["source_commit"] for r in runs}
    assert len(source_commit) == 1
    input_hashes, output_hashes = {}, {}
    for r in runs:
        assert not input_hashes.keys() & r["inputs"].keys()
        input_hashes.update(r["inputs"])
        output_hashes.update(r["outputs"])
        for name, value in r["source_sha256"].items():
            assert sha(EX / name) == value, name
    assert len(input_hashes) == 120 and len(output_hashes) == 40
    for path, value in output_hashes.items():
        assert sha(OUT / Path(path).relative_to("/runout/results")) == value
    old = json.loads((EX / "revalidation_20261119/EXECUTION_RECEIPT.json").read_text(encoding="utf-8"))
    receipt = dict(question_id="IPALO-FAR-KRIGING-AB-20261119/AUTHORIZED-EXPLORATION-01",
        role="IMPLEMENTER_SELF_CHECK", independent_audit=False,
        authorization="2026-11-19 user: 우선 그냥 진행하도록 해",
        source_commit=next(iter(source_commit)),
        recorded_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        account=ssh("whoami").decode().strip(), remote_workspace=REMOTE,
        status="EXPLORATORY_USER_AUTHORIZED_BASELINE_MISMATCH",
        original_model_sources="Unchanged read-only attempt_02; execution_20261119/BUNDLE_MANIFEST.json",
        pinned_governance=old["pinned_governance"], containers=containers,
        source_sha256=runs[0]["source_sha256"], input_files=len(input_hashes), output_files=len(output_hashes),
        evidence_tools_sha256={name: sha(EX / name) for name in
            ("verify_authorized_traces.py", "collect_authorized_evidence.py")},
        paired_trace_files=480, stable_kriging_applied=False,
        trace_location=REMOTE + "/results/{condition}/seed{seed}/traces/",
        baseline_tolerance=1e-8, scientific_adoption_pass=False)
    assert receipt["account"] == "KMS"
    (OUT / "EXECUTION_RECEIPT.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Collected 40 results, 120 input hashes, 480 retained trace hashes; all six containers exited 0")


if __name__ == "__main__":
    main()
