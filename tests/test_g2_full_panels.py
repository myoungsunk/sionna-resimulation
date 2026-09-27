import math

import numpy as np
import pytest

from rt_cp_uwb_py.g2_full_panels import (EPS0, occluder_conductivity, panel_material_spec, panel_ply,
                                        panel_triangles)

PANEL = dict(center=[1., 2., 1.5], half=[0.4, 0.85], normal=[0., -1., 0.], u=[1., 0., 0.], v=[0., 0., 1.])


def obj(kind, name, eps_r, tan_delta):
    return dict(object_id='X_P2_PANEL', panel=PANEL,
                material=dict(kind=kind, name=name, eps_r=eps_r, tan_delta=tan_delta, conductivity_s_m=0.))


def test_occluder_keeps_tan_delta_constant_over_band():
    for k in (0, 128, 256):
        f = 6250400000. + 1950000.*k
        sigma = occluder_conductivity(f)
        assert math.isclose(sigma/(2*math.pi*f*EPS0*12.), 0.35, rel_tol=1e-12)
    assert 1.46 < occluder_conductivity(6250400000.) < occluder_conductivity(6749600000.) < 1.58


def test_dielectric_occluder_is_not_metal():
    spec = panel_material_spec(obj('dielectric', 'blockage_panel', 12.0, 0.35))
    assert spec['kind'] == 'dielectric' and spec['thickness_m'] == 0.020
    assert spec['relative_permittivity'] == 12.0 and spec['tan_delta'] == 0.35


def test_pec_panel_stays_itu_metal_1mm():
    spec = panel_material_spec(obj('PEC', 'metal_pec', 4.0, 0.0))
    assert spec == dict(spec, kind='PEC', itu_type='metal', thickness_m=0.001)


@pytest.mark.parametrize('kind,name,eps_r,tan_delta', [
    ('dielectric', 'blockage_panel', 11.0, 0.35), ('dielectric', 'other', 12.0, 0.35), ('glass', 'g', 6., 0.)])
def test_unknown_panel_material_is_rejected(kind, name, eps_r, tan_delta):
    with pytest.raises(ValueError, match='UNSUPPORTED_CONDITION_PANEL_MATERIAL'):
        panel_material_spec(obj(kind, name, eps_r, tan_delta))


def ply_mesh(text):
    lines = text.splitlines()
    verts = np.array([[float(x) for x in l.split()] for l in lines[9:13]])
    faces = [[int(x) for x in l.split()[1:]] for l in lines[13:15]]
    assert [int(l.split()[0]) for l in lines[13:15]] == [3, 3]
    return verts, faces


def point_in_triangle(p, a, b, c):
    """Barycentric test in the panel plane; boundary counts as inside."""
    v0, v1, v2 = c-a, b-a, p-a
    d00, d01, d11, d20, d21 = v0@v0, v0@v1, v1@v1, v2@v0, v2@v1
    den = d00*d11-d01*d01
    s, t = (d11*d20-d01*d21)/den, (d00*d21-d01*d20)/den
    return s >= -1e-12 and t >= -1e-12 and s+t <= 1+1e-12


REAL_PANELS = [  # 0.8 x 1.7 m occluder and 1.2 x 1.5 m metal records from FRAMES.jsonl
    dict(center=[0.9454266605167866, 2.2430896561997047, 1.9207668249846832], half=[0.4, 0.85],
         normal=[0.4508451808276029, -0.8926021638583039, 0.0], u=[0.8926021638583039, 0.4508451808276029, 0.0],
         v=[0.0, 0.0, 1.0]),
    dict(center=[3.2154368084422287, 2.4612532276409134, 1.9207668249846832], half=[0.6, 0.75],
         normal=[0.40403089425669425, 0.9147453396908543, 0.0], u=[-0.9147453396908543, 0.40403089425669425, 0.0],
         v=[0.0, 0.0, 1.0]),
    PANEL]


@pytest.mark.parametrize('panel', REAL_PANELS)
def test_panel_mesh_covers_rectangle_once_with_declared_normal(panel):
    verts, faces = ply_mesh(panel_ply(panel))
    c, u, v, n = (np.array(panel[k], float) for k in ('center', 'u', 'v', 'normal'))
    h0, h1 = panel['half']
    # Vertices are exactly the rectangle corners (pose and size preserved).
    local = np.array([[(p-c)@u, (p-c)@v, (p-c)@n] for p in verts])
    assert np.allclose(sorted(map(tuple, np.round(local[:, :2], 12))),
                       sorted({(a*h0, b*h1) for a in (-1, 1) for b in (-1, 1)}))
    assert np.allclose(local[:, 2], 0)
    areas = []
    for f in faces:
        a, b, cc = verts[f]
        cross = np.cross(b-a, cc-a)
        areas.append(np.linalg.norm(cross)/2)
        assert np.allclose(cross/np.linalg.norm(cross), n, atol=1e-12)  # both normals = declared normal
    assert np.isclose(sum(areas), 4*h0*h1)  # no gap in total area
    # Every sample of the rectangle interior lies in exactly one triangle (no hole, no overlap).
    for x in np.linspace(-.97, .97, 23):
        for y in np.linspace(-.97, .97, 23):
            if abs(x - y) < 1e-9:
                continue  # on the shared 0-3 diagonal both triangles legitimately touch
            p = c + x*h0*u + y*h1*v
            hits = sum(point_in_triangle(p, *verts[f]) for f in faces)
            assert hits == 1, (x, y, hits)


def test_panel_axes_must_match_declared_normal():
    bad = dict(PANEL, normal=[0., 1., 0.])
    with pytest.raises(ValueError, match='RIGHT_HANDED'):
        panel_triangles(bad)
