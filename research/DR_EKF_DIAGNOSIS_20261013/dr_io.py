"""Strict JSON output and cache I/O for the DR diagnosis (kept out of dr_harness.py, which is frozen for D6).

* json_text(): converts numpy scalars/arrays, maps non-finite floats to null and serialises with allow_nan=False, so
  no output contains the non-standard NaN/Infinity literals.
* save_cache()/load_cache(): atomic cache writes (temp file + os.replace) with provenance (runner/harness SHA256,
  git HEAD) and a content check against the requested seeds and route length before any cache is reused.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

import numpy as np


def json_safe(obj):
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return json_safe(obj.tolist())
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        v = float(obj)
        return v if math.isfinite(v) else None
    return obj


def json_text(obj, indent=1):
    return json.dumps(json_safe(obj), indent=indent, allow_nan=False)


def save_cache(path, arrays, provenance):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(arrays)
    for k, v in provenance.items():
        payload[f'prov_{k}'] = np.array(str(v))
    tmp = path.with_name(path.name + '.tmp')
    with open(tmp, 'wb') as fh:
        np.savez(fh, **payload)
    os.replace(tmp, path)


def load_cache(path):
    with np.load(path, allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def validate_cell(arr, seeds, n_time):
    """Reasons the cached cell cannot stand for (seeds, route); empty list = valid."""
    problems = []
    if 'seeds' not in arr or list(arr['seeds']) != list(seeds):
        problems.append('seed list differs from the requested seeds')
    N = len(seeds)
    for key, shape in (('E_post', (N, n_time, 6)), ('nees_pose_post', (N, n_time)), ('P3_post', (N, n_time, 3, 3)),
                       ('sigma_psi_post', (N, n_time))):
        if key not in arr:
            problems.append(f'missing {key}')
        elif arr[key].shape != shape:
            problems.append(f'{key} shape {arr[key].shape} != {shape}')
    if 'E_post' in arr and arr['E_post'].shape == (N, n_time, 6) and not np.isfinite(arr['E_post']).all():
        problems.append('non-finite state errors')
    return problems


def load_json(path):
    import json as _json
    return _json.loads(Path(path).read_text())
