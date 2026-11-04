import csv
import hashlib
from collections import Counter
from pathlib import Path

REGISTRY_SHA = "7fd57c436e34c2a6312769310080b3886d62799348696c4eb894113977d3b11c"

def registry(path):
    assert hashlib.sha256(path.read_bytes()).hexdigest() == REGISTRY_SHA
    rows = list(csv.DictReader(path.open()))
    assert len(rows)==len({(r["route"],r["pose_id"]) for r in rows})==28
    assert sum(r["source"]=="B1" for r in rows)==7
    poses={(r["route"],int(r["pose_id"])):r for r in rows if r["source"]=="NEW"}
    assert len(poses)==21
    return poses

def keys(poses):
    return [(route, pose, mode) for route, pose in poses for mode in ("Full", "LoS")]

def verify(expected, results):
    actual = [(r["route"], r["pose"], r["mode"]) for r in results]
    if Counter(expected) != Counter(actual) or len(set(expected)) != 42:
        raise ValueError("REGISTERED_KEY_MISMATCH")
    if any(r["status"] != "PASS_TECHNICAL" or r["calls"] != 257 for r in results):
        raise ValueError("INCOMPLETE_RESULT")
