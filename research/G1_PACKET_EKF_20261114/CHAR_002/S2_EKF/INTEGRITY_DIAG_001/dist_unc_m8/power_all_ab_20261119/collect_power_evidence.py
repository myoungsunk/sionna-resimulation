"""Collect bounded, read-only Snowball evidence after all four shards finish."""
import datetime
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

EX = Path(__file__).parent
FAR_EX = EX.parent / "far_kriging_ab_20261119"
REMOTE = "/home/KMS/FAR_KRIGING_AB_20261119_01a1f269/power_all_explore_01"
OUT = EX / "execution_20261119"


def ssh(cmd):
    return subprocess.check_output(["ssh", "-o", "BatchMode=yes", "Snowball", cmd])


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    names = [f"power-all-{cond}-{first}-01a1f269"
             for cond in ("B0", "L2_GYRO_ARW") for first in (30, 40)]
    names.append("power-all-aggregate-01a1f269")
    names.append("power-all-verify-01a1f269")
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
    old = json.loads((FAR_EX / "revalidation_20261119/EXECUTION_RECEIPT.json").read_text(encoding="utf-8"))
    bundle_manifest = json.loads((FAR_EX / "execution_20261119/BUNDLE_MANIFEST.json").read_text(encoding="utf-8"))
    pins = {r["path"]: r["sha256"] for r in bundle_manifest["files"]}
    prefix = "research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001/dist_unc_m8"
    frozen = {"m8/" + name: pins[prefix + "/step3_fair/code/" + name]
              for name in ("common.py", "krige_online.py", "m8_replay.py", "m8s3_score.py")}
    frozen.update({"m8cal/" + name: value for name, value in {
        "SWEEP_FEATURES.csv.gz": "2917a06c8317fa81f3729e90d4c65a077af14c73c56137c75777eea6d710c320",
        "KRIGE_PARAMS.json": "fad67226ce0607db82fc9710df984d20ba9b7de5c4b20581ccd53f0d762716db",
        "SWEEP_TABLE_V.json": "bc918bb246e132c19e5ea10573b80e9839a2a6f9286832d3b50522de20e2daaf",
        "SWEEP_CAL_B.npz": "2a7be23be7c8b69eaa4712149208862dc55928ddab696f45e664b30f2365c4fb"}.items()})
    asset_root = REMOTE.rsplit("/", 1)[0] + "/attempt_02/"
    actual = {line.split()[1].removeprefix(asset_root): line.split()[0]
              for line in ssh("sha256sum " + " ".join(asset_root + k for k in frozen)).decode().splitlines()}
    assert actual == frozen, "Frozen model/calibration drift"
    receipt = dict(question_id="IPALO-POWER-ALL-AB-20261119",
        role="IMPLEMENTER_SELF_CHECK", independent_audit=False,
        authorization="2026-11-19 user: 단·중·장거리 모두 POWER, 나머지 조건 유지, 기존 기준 비교 실행 및 GitHub 업로드. Prior mismatch authorization persists.",
        source_commit=next(iter(source_commit)),
        recorded_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        account=ssh("whoami").decode().strip(), remote_workspace=REMOTE,
        status="EXPLORATORY_USER_AUTHORIZED_BASELINE_MISMATCH",
        original_model_sources="Unchanged read-only attempt_02; execution_20261119/BUNDLE_MANIFEST.json",
        frozen_model_and_calibration_sha256=actual,
        pinned_governance=old["pinned_governance"], containers=containers,
        source_sha256=runs[0]["source_sha256"], input_files=len(input_hashes), output_files=len(output_hashes),
        evidence_tools_sha256={name: sha(EX / name) for name in
            ("verify_power_traces.py", "collect_power_evidence.py")},
        paired_trace_files=480, stable_kriging_applied=False,
        trace_location=REMOTE + "/results/{condition}/seed{seed}/traces/",
        baseline_tolerance=1e-8, scientific_adoption_pass=False)
    assert receipt["account"] == "KMS"
    (OUT / "EXECUTION_RECEIPT.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Collected 40 results, 120 input hashes, 480 retained trace hashes; all six containers exited 0")


if __name__ == "__main__":
    main()
