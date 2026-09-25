"""Float64 RF delay for already-admitted, finite planar R0-R3 paths.

Uses source geometry and solver hit points only, never reference RF/path truth.
Visibility remains the path solver's responsibility. Ambiguous surface matching
fails closed. This is not a diffraction, transmission, or curved-surface adapter.
"""
import numpy as np

C0 = 299792458.0


def refined_delay(tx, rx, hit_points, surfaces, geometry_tolerance_m=1e-4):
    tx, rx = np.asarray(tx, dtype=np.float64), np.asarray(rx, dtype=np.float64)
    hits = np.asarray(hit_points, dtype=np.float64).reshape(-1, 3)
    if len(hits) > 3 or not np.isfinite(np.concatenate([tx, rx, hits.ravel()])).all():
        raise ValueError('Requires finite R0-R3 geometry')
    selected, images = [], [tx]
    for hit in hits:
        candidates = []
        for surface in surfaces:
            p, n, u, v = [np.asarray(surface[k], dtype=np.float64)
                          for k in ('point', 'normal', 'u_axis', 'v_axis')]
            basis = np.stack([n, u, v])
            if not np.allclose(basis @ basis.T, np.eye(3), atol=1e-10, rtol=0):
                raise ValueError('Non-orthonormal plane frame')
            q = hit - p
            if (abs(q @ n) <= geometry_tolerance_m
                    and abs(q @ u) <= surface['half_u'] + geometry_tolerance_m
                    and abs(q @ v) <= surface['half_v'] + geometry_tolerance_m):
                candidates.append((surface, p, n, u, v))
        if len(candidates) != 1:
            raise ValueError('Missing or ambiguous solver-hit surface')
        selected.append(candidates[0])
        _, p, n, _, _ = candidates[0]
        image = images[-1]
        images.append(image - 2 * ((image - p) @ n) * n)
    current, reverse_points = rx, []
    for k in range(len(selected)-1, -1, -1):
        surface, p, n, u, v = selected[k]
        ray = images[k+1] - current
        denom = ray @ n
        if abs(denom) < 1e-12:
            raise ValueError('Degenerate image-plane intersection')
        fraction = ((p-current) @ n) / denom
        if not 0 < fraction < 1:
            raise ValueError('Reflection outside image segment')
        point = current + fraction * ray
        q = point-p
        if (abs(q@u) > surface['half_u']+1e-10
                or abs(q@v) > surface['half_v']+1e-10
                or np.max(abs(point-hits[k])) > geometry_tolerance_m):
            raise ValueError('Refined vertex violates admitted finite geometry')
        reverse_points.append(point)
        current = point
    points = np.array([tx, *reverse_points[::-1], rx], dtype=np.float64)
    segments = np.linalg.norm(np.diff(points, axis=0), axis=1)
    if np.any(segments <= 1e-9):
        raise ValueError('Degenerate physical segment')
    length = np.linalg.norm(images[-1]-rx)
    if abs(segments.sum()-length) > 1e-10:
        raise ValueError('Image and polyline lengths disagree')
    return float(length/C0), [s[0]['surface_id'] for s in selected]


def propagation_phase(frequency_hz, delay_s):
    return np.exp(-2j*np.pi*np.asarray(frequency_hz, dtype=np.float64)
                  * np.asarray(delay_s, dtype=np.float64))
