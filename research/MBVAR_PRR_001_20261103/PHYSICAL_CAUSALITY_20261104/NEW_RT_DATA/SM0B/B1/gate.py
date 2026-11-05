import csv
import hashlib
from collections import Counter
from pathlib import Path

REGISTRY_SHA = "b506d3cfef5ceab5e6fbf5da350d7a9674a3b8103d92bae564c77a296a8cff22"

def registry(path):
    assert hashlib.sha256(path.read_bytes()).hexdigest() == REGISTRY_SHA
    rows = list(csv.DictReader(path.open()))
    poses = {(r["route"], int(r["pose_id"])): r for r in rows}
    assert len(rows) == len(poses) == 15
    for pose in (194, 234):
        del poses["R4", pose]
    return poses

def keys(poses):
    return [(route, pose, mode) for route, pose in poses for mode in ("Full", "LoS")]

def verify(expected, results):
    actual = [(r["route"], r["pose"], r["mode"]) for r in results]
    if Counter(expected) != Counter(actual) or len(set(expected)) != 26:
        raise ValueError("REGISTERED_KEY_MISMATCH")
    if any(r["status"] != "PASS_TECHNICAL" or r["calls"] != 257 for r in results):
        raise ValueError("INCOMPLETE_RESULT")
