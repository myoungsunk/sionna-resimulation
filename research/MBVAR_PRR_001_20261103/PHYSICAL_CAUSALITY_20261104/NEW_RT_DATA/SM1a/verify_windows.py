"""Verify the two evidence packages and join the fixed SM1a windows."""
import csv
import hashlib
import json
import tarfile
from pathlib import Path

root = Path(__file__).resolve().parent
previous = root.parent / "SM0B/B1"
ledger = list(csv.DictReader((root / "SM1_KEY_LEDGER.csv").open()))
records = {}
for source, folder in (("B1", previous), ("NEW", root)):
    archive = folder / "evidence.tar.gz"
    archive_hash = (folder / "ARCHIVE_SHA256.txt").read_text().split()[0]
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == archive_hash
    actual = {}
    with tarfile.open(archive, "r|gz") as reader:
        for member in reader:
            if not member.isfile():
                continue
            name = member.name
            data = reader.extractfile(member).read()
            if name.startswith("out/"):
                actual[name] = hashlib.sha256(data).hexdigest()
            if name == "SHA256SUMS.txt":
                expected = {n: h for h, n in (line.split(None, 1) for line in data.decode().splitlines())}
            if name == "out/QA.json":
                qa = json.loads(data)
            if source == "NEW" and name in {"out/QA.json", "out/APPROVAL.json", "out/INPUT_LOCK.json",
                                              "out/FAILED_KEYS.csv", "SHA256SUMS.txt", "runtime.txt", "run.log"}:
                (root / Path(name).name).write_bytes(data)
    assert actual == expected
    for result in qa:
        key = (source, result["route"], result["pose"], result["mode"])
        assert key not in records
        records[key] = result
pairs = []
for pose in ledger:
    route, pid, source = pose["route"], int(pose["pose_id"]), pose["source"]
    full, los = [records[(source, route, pid, mode)] for mode in ("Full", "LoS")]
    assert all(r["status"] == "PASS_TECHNICAL" and r["calls"] == 257 for r in (full, los))
    pairs.append(dict(route=route, pose_id=pid, t_s=pose["t_s"], source=source,
                      full_tap=full["tap"], los_tap=los["tap"], delta_tap=full["tap"]-los["tap"],
                      full_s=full["signed_s"], los_s=los["signed_s"], delta_s=full["signed_s"]-los["signed_s"]))
assert len(pairs) == 28 and len([k for k in records if k[0]=="NEW"]) == 42
with (root/"PAIRED_WINDOWS.csv").open("w", newline="") as target:
    writer = csv.DictWriter(target, fieldnames=pairs[0])
    writer.writeheader()
    writer.writerows(pairs)
