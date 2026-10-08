"""Minimal ASCII PLY writer for the ray-tracing scenes (quads split into two triangles each)."""
from __future__ import annotations

from pathlib import Path

import numpy as np


def write_ply(path: Path, quads) -> None:
    """One PLY mesh from a single (4, 3) quad or a list of quads."""
    arr = np.asarray(quads, float)
    quads = [arr] if arr.ndim == 2 else [np.asarray(q, float) for q in quads]
    n = len(quads)
    lines = ["ply", "format ascii 1.0", f"element vertex {4 * n}", "property float x", "property float y", "property float z",
             f"element face {2 * n}", "property list uchar int vertex_indices", "end_header"]
    for q in quads:
        lines += [" ".join(format(float(v), ".17g") for v in p) for p in q]
    for i in range(n):
        lines += [f"3 {4 * i} {4 * i + 1} {4 * i + 2}", f"3 {4 * i} {4 * i + 2} {4 * i + 3}"]
    Path(path).write_text("\n".join(lines) + "\n", encoding="ascii")
