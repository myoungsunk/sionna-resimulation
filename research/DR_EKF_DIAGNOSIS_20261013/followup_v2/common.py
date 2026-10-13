"""Safety / provenance helpers for V0-V5. This module never mutates D6 caches."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DIAG = HERE.parent
ROOT = DIAG.parents[1]
if str(DIAG) not in sys.path:
    sys.path.insert(0, str(DIAG))
import dr_harness as H  # noqa: E402
import dr_io as IO  # noqa: E402

D6_SPEC = DIAG / "D6_SPEC.json"
D6_PREREG_COMMIT = "9bbe217a5e023b6a58eb0ac8e2d4908a55277f45"
D6_SEEDS = tuple(range(8100, 8400))
DEV_SEEDS = tuple(range(8000, 8032))
FOLLOWUP_SEEDS = tuple(range(9000, 9300))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(2 ** 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_frozen_spec():
    """Compare spec bytes with the pre-run registration commit; no git mutation."""
    rel = D6_SPEC.relative_to(ROOT).as_posix()
    r = subprocess.run(["git", "-C", str(ROOT), "show",
                        f"{D6_PREREG_COMMIT}:{rel}"],
                       capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"Cannot retrieve pre-registered D6 spec: {r.stderr!r}")
    if D6_SPEC.read_bytes() != r.stdout:
        raise RuntimeError("D6_SPEC.json differs from pre-registered bytes")
    return dict(path=rel, sha256=sha256(D6_SPEC), prereg_commit=D6_PREREG_COMMIT)


def new_dir(directory: str | Path) -> Path:
    """Outputs MUST be outside any running D6 directory; refuse overwrite."""
    p = Path(directory).resolve()
    for protected in (DIAG / "cache", DIAG / "out"):
        if p == protected.resolve() or protected.resolve() in p.parents:
            raise ValueError(f"Refusing write inside existing D6 tree: {p}")
    p.mkdir(parents=True, exist_ok=False)
    return p


def write_json_new(path: Path, value):
    if path.exists():
        raise FileExistsError(path)
    path.write_text(IO.json_text(value, indent=2) + "\n", encoding="utf-8")


def provenance(extra=None):
    r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                       capture_output=True, text=True)
    return dict(repo_head=r.stdout.strip() if r.returncode == 0 else "UNKNOWN",
                frozen_spec=git_frozen_spec(), generated_utc=time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                src_sha256={p.name: sha256(p) for p in sorted(HERE.glob("*.py"))},
                **(extra or {}))


def parse_seed_range(text: str) -> list[int]:
    lo, hi = (int(s) for s in text.split(":"))
    if hi <= lo or hi - lo > 2000:
        raise ValueError("invalid/too large seed interval")
    return list(range(lo, hi))


def cache_path(arm: str, seeds: list[int], route: str, level: int,
               cache_root: Path | None = None):
    from diagnose_dr_trace import cache_path as old_cache_path
    if cache_root is None:
        return old_cache_path(arm, seeds, route, level)
    return (cache_root / f"{arm}_s{seeds[0]}-{seeds[-1]}"
            / f"{H.cell_name(route, level)}.npz")


def validated_cache(path: Path, seeds: list[int], route: str,
                    *, min_age_s=120, sha=False, full_psd=False):
    """Read-only; protects against simultaneously written and stale/malformed NPZ."""
    result = dict(file=str(path), cell=route, status="NOT_READY", errors=[])
    if not path.is_file():
        result["status"] = "MISSING"
        return result, None
    s0 = path.stat()
    result["age_s"] = max(0., time.time() - s0.st_mtime)
    result["bytes"] = s0.st_size
    if result["age_s"] < min_age_s:
        result["status"] = "RECENT_WRITER_POSSIBLE"
        return result, None
    try:
        with np.load(path, allow_pickle=False) as z:
            arr = {k: z[k] for k in z.files}
        if (path.stat().st_mtime_ns, path.stat().st_size) != (s0.st_mtime_ns, s0.st_size):
            result["status"] = "CHANGED_DURING_READ"
            return result, None
        T = len(H.MOT[route]["t"])
        issues = IO.validate_cell(arr, seeds, T)
        n = len(seeds)
        required = {"status": (n, T), "P3_post": (n, T, 3, 3),
                    "nees_pose_post": (n, T),
                    "nees_heading_post": (n, T), "nees_cond_xy_post": (n, T)}
        for k, sh in required.items():
            if k not in arr:
                issues.append(f"missing {k}")
            elif arr[k].shape != sh:
                issues.append(f"{k}: expected {sh}, got {arr[k].shape}")
        for k in ("E_post", "P3_post", "nees_pose_post",
                  "nees_heading_post", "nees_cond_xy_post"):
            if k in arr and not np.isfinite(arr[k]).all():
                issues.append(f"non-finite {k}")
        if not issues:
            P = arr["P3_post"]
            chosen = np.arange(T) if full_psd else np.unique(
                np.r_[0, np.linspace(0, T-1, min(T, 12)).astype(int)])
            eig = np.linalg.eigvalsh(P[:, chosen])
            result["min_sampled_eig"] = float(eig.min())
            if eig.min() <= 0:
                issues.append(f"nonpositive pose covariance: {eig.min()}")
            # Validate pose NEES from the actual errors/covariance at selected steps.
            if not issues:
                E = arr["E_post"][:, chosen, :3].astype(float)
                v = np.einsum("...i,...i->...",
                              E, np.linalg.solve(P[:, chosen], E[..., None])[..., 0])
                got = arr["nees_pose_post"][:, chosen]
                result["max_nees_recalc_abs"] = float(np.max(np.abs(v - got)))
                if not np.allclose(v, got, atol=3e-3, rtol=3e-4):
                    issues.append("pose NEES incompatible with stored errors/covariance")
        result["errors"] = issues
        result["seeds_n"] = n
        result["status"] = "VALID" if not issues else "INVALID"
        if sha and not issues:
            result["sha256"] = sha256(path)
        return result, arr if not issues else None
    except Exception as exc:
        result["status"] = "UNREADABLE"
        result["errors"] = [f"{type(exc).__name__}: {exc}"]
        return result, None
