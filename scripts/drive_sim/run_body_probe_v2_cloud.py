#!/usr/bin/env python3
"""Portable asset precheck and explicit delegation to the unchanged native runner."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs/body_probe/ekf_native_noisy_body_v1.cloud.json"
DEFAULT_MANIFEST = ROOT / "configs/body_probe/FFD_BANK_MANIFEST.json"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_config(template, bank_dir, bank_manifest):
    cfg = copy.deepcopy(template)
    if cfg["rf"]["mode"] != "range_only":
        raise ValueError("CLOUD_TEMPLATE_REQUIRES_RANGE_ONLY; s needs a separate LUT contract")
    cfg["rf"]["bank_dir"] = str(Path(bank_dir).resolve())
    cfg["rf"]["bank_manifest"] = str(Path(bank_manifest).resolve())
    return cfg


def verify_assets(cfg):
    expected = cfg["cloud_assets"]
    manifest = Path(cfg["rf"]["bank_manifest"])
    if not manifest.is_file():
        raise ValueError(f"BANK_MANIFEST_MISSING: {manifest}")
    if sha256(manifest) != expected["manifest_sha256"]:
        raise ValueError("BANK_MANIFEST_SHA_MISMATCH")
    declared = json.loads(manifest.read_text(encoding="utf-8"))["npz_sha256"]
    verified = {}
    for name, digest in expected["bank_sha256"].items():
        if declared.get(name) != digest:
            raise ValueError(f"MANIFEST_BANK_HASH_MISMATCH: {name}")
        path = Path(cfg["rf"]["bank_dir"]) / name
        if not path.is_file():
            raise ValueError(f"BANK_MISSING: {path}")
        with path.open("rb") as stream:
            if stream.read(64).startswith(b"version https://git-lfs.github.com/spec/v1"):
                raise ValueError(f"BANK_IS_LFS_POINTER: {name}; fetch actual LFS bytes")
        if sha256(path) != digest:
            raise ValueError(f"BANK_SHA_MISMATCH: {name}")
        verified[name] = digest
    if set(verified) != {"LP_plus45_bank.npz", "LP_minus45_bank.npz"}:
        raise ValueError("EXPECTED_LP45_BANK_PAIR_REQUIRED")
    return verified


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--bank-dir", type=Path,
                        default=Path(os.environ.get("FFD_BANK_DIR", str(ROOT))))
    parser.add_argument("--bank-manifest", type=Path,
                        default=Path(os.environ.get("FFD_BANK_MANIFEST", str(DEFAULT_MANIFEST))))
    parser.add_argument("--out", type=Path)
    parser.add_argument("--execute-native", action="store_true")
    args = parser.parse_args(argv)
    try:
        cfg = resolve_config(json.loads(args.config.read_text(encoding="utf-8")),
                             args.bank_dir, args.bank_manifest)
        verified = verify_assets(cfg)
        if args.execute_native:
            if args.out is None or args.out.exists():
                raise ValueError("NEW_OUT_REQUIRED; existing results must not be overwritten")
            resolved = args.out.resolve().with_name(args.out.name + ".config.json")
            if resolved.exists():
                raise ValueError(f"RESOLVED_CONFIG_EXISTS: {resolved}")
    except (ValueError, KeyError, OSError) as exc:
        print(json.dumps({"status": "BLOCKED_PRECONDITION", "error": str(exc),
                          "scientific_PASS": False}), file=sys.stderr)
        return 2

    print(json.dumps({"status": "ASSET_HASHES_VERIFIED_NOT_RF_VALIDATED",
                      "bank_sha256": verified, "scientific_PASS": False}), flush=True)
    native = ROOT / "scripts/drive_sim/run_body_probe_v2_native.py"
    # Original precheck never constructs a plant or calls PathSolver.
    with tempfile.TemporaryDirectory(prefix="body-probe-precheck-") as temp:
        temp_config = Path(temp) / "resolved.json"
        temp_config.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        checked = subprocess.run([sys.executable, str(native), "--config", str(temp_config)])
    if checked.returncode or not args.execute_native:
        return checked.returncode

    # Preserve the concrete config outside the new result directory. The native
    # runner requires --out not to exist and includes this config in its manifest.
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with resolved.open("x", encoding="utf-8") as stream:
        json.dump(cfg, stream, indent=2)
        stream.write("\n")
    return subprocess.run([sys.executable, str(native), "--config", str(resolved),
                           "--out", str(args.out), "--execute-native"]).returncode


if __name__ == "__main__":
    raise SystemExit(main())
