import numpy as np

from qclean_uwb.scenarios.office import OfficeSetup
from qclean_uwb.scenarios.ply import write_ply


def read_ply(path):
    lines = path.read_text().splitlines()
    n_v = int(next(l for l in lines if l.startswith("element vertex")).split()[-1])
    n_f = int(next(l for l in lines if l.startswith("element face")).split()[-1])
    i = lines.index("end_header") + 1
    v = np.array([[float(t) for t in l.split()] for l in lines[i:i + n_v]])
    f = np.array([[int(t) for t in l.split()[1:]] for l in lines[i + n_v:i + n_v + n_f]])
    return v, f


def test_single_quad_and_box_roundtrip(tmp_path):
    quad = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], float)
    write_ply(tmp_path / "q.ply", quad)
    v, f = read_ply(tmp_path / "q.ply")
    assert v.shape == (4, 3) and f.shape == (2, 3) and np.allclose(v, quad)
    obj = [o for o in OfficeSetup().objects() if o["name"].startswith("desk_")][0]
    write_ply(tmp_path / "d.ply", obj["quads"])
    v, f = read_ply(tmp_path / "d.ply")
    assert v.shape == (24, 3) and f.shape == (12, 3) and f.max() == 23
    area = sum(0.5 * np.linalg.norm(np.cross(v[b] - v[a], v[c] - v[a])) for a, b, c in f)
    lo, hi = v.min(0), v.max(0)
    d = hi - lo
    assert np.isclose(area, 2 * (d[0] * d[1] + d[0] * d[2] + d[1] * d[2]))
