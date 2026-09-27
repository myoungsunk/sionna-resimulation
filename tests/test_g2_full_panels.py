import math

import pytest

from rt_cp_uwb_py.g2_full_panels import (EPS0, occluder_conductivity, panel_material_spec, panel_ply)

PANEL = dict(center=[1., 2., 1.5], half=[0.4, 0.85], normal=[0., 1., 0.], u=[1., 0., 0.], v=[0., 0., 1.])


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


def test_panel_ply_keeps_pose_and_size():
    lines = panel_ply(PANEL).splitlines()
    corners = [[float(x) for x in l.split()] for l in lines[9:13]]
    xs, zs = {c[0] for c in corners}, {c[2] for c in corners}
    assert xs == {0.6, 1.4} and {round(z, 12) for z in zs} == {0.65, 2.35}
    assert all(c[1] == 2. for c in corners) and lines[-2:] == ['3 0 1 2', '3 0 2 3']
