import numpy as np

from qclean_uwb.features import specular_model as sm

F = 6.25e9
LAM = sm.C0 / F


def test_thick_slab_matches_half_space_fresnel():
    eta = sm.eta_complex("concrete", F)
    cos_t = np.cos(np.deg2rad(40.0))
    root = np.sqrt(eta - (1 - cos_t**2) + 0j)
    te = (cos_t - root) / (cos_t + root)
    tm = (eta * cos_t - root) / (eta * cos_t + root)
    # a 0.2 m concrete slab is lossy enough that the back face does not matter
    r_te, r_tm = sm.slab_reflection(cos_t, eta, 0.2, LAM)
    assert abs(r_te - te) < 5e-3 and abs(r_tm - tm) < 5e-3


def test_zero_thickness_slab_does_not_reflect():
    eta = sm.eta_complex("plasterboard", F)
    r_te, r_tm = sm.slab_reflection(0.7, eta, 0.0, LAM)
    assert abs(r_te) < 1e-12 and abs(r_tm) < 1e-12


def test_reflection_magnitude_below_one_and_tm_has_brewster_dip():
    eta = sm.eta_complex("concrete", F)
    angles = np.deg2rad(np.arange(5, 86, 5))
    r_te, r_tm = sm.slab_reflection(np.cos(angles), eta, 0.2, LAM)
    assert np.all(np.abs(r_te) < 1.0) and np.all(np.abs(r_tm) < 1.0)
    assert np.abs(r_tm).min() < 0.3 * np.abs(r_te)[np.argmin(np.abs(r_tm))]


def test_scale_changes_permittivity_and_conductivity_together():
    e1, e2 = sm.eta_complex("concrete", F), sm.eta_complex("concrete", F, scale=1.2)
    assert np.isclose(e2.real, 1.2 * e1.real) and np.isclose(e2.imag, 1.2 * e1.imag)


def test_mirror_places_image_behind_plane():
    q = sm.mirror([4.0, 0.5, 2.65], 2, 0.0)
    assert np.allclose(q, [4.0, 0.5, -2.65])
    axis, coord, n = sm.plane("ceiling", 20.0, 1.2, 2.7)
    assert axis == 2 and coord == 2.7 and np.allclose(n, [0, 0, 1])


def test_transmission_limits_and_energy():
    eta = sm.eta_complex("chipboard", F)
    t0 = sm.slab_transmission(0.9, eta, 1e-9, LAM)
    assert np.allclose(t0, 1.0, atol=1e-6)  # vanishing thickness: nothing happens
    for d in (0.0125, 0.03, 0.04, 0.2):
        for ang in (0, 30, 60):
            c = np.cos(np.deg2rad(ang))
            (r_te, t_te), (r_tm, t_tm) = sm.slab_coefficients(c, eta, d, LAM)
            assert abs(r_te) ** 2 + abs(t_te) ** 2 <= 1 + 1e-9 and abs(r_tm) ** 2 + abs(t_tm) ** 2 <= 1 + 1e-9


def test_sionna_material_constants_match():
    import pytest
    itu = pytest.importorskip("sionna.rt.radio_materials.itu")
    for name in ("concrete", "plasterboard", "chipboard", "wood"):
        (rng,) = [v for k, v in itu.ITU_MATERIALS_PROPERTIES[name].items() if k[0] <= 6.25 <= k[1]][:1]
        assert tuple(rng) == sm.ITU[name]
