import numpy as np
import pytest

from qclean_uwb.drivesim import pattern_apply as P
from qclean_uwb.drivesim.paths import path_signature, signature_diff

C0 = 299792458.0


def fake_bank(n_bin=5, seed=0):
    rng = np.random.default_rng(seed)
    th = np.arange(0.0, 181.0, 5.0)
    ph = np.arange(-180.0, 181.0, 5.0)
    shape = (n_bin, len(th), len(ph))
    return dict(theta_deg=th, phi_deg=ph, e_theta=rng.normal(size=shape) + 1j * rng.normal(size=shape),
                e_phi=rng.normal(size=shape) + 1j * rng.normal(size=shape), freqs_hz=np.linspace(6.25e9, 6.75e9, n_bin))


def test_los_jones_roundtrip_matches_cartesian_contraction():
    th_t, ph_t, th_r, ph_r = np.array([2.0]), np.array([0.4]), np.array([1.1]), np.array([-2.0])
    d_t = P.direction(th_t, ph_t)
    # LoS Jones = spreading * identity on the plane transverse to d_t (rx basis uses the *arrival* direction, here the same line reversed)
    d_r = P.direction(th_r, ph_r)
    br = np.stack(P.sph_basis(th_r, ph_r), -1)
    bt = np.stack(P.sph_basis(th_t, ph_t), -1)
    j_true = 0.37 * (np.eye(3) - np.outer(d_t[0], d_t[0]))
    a_iso = np.einsum("nki,ij,njl->nkl", np.swapaxes(br, 1, 2), j_true, bt)           # (1,2,2)
    j = P.jones_from_iso(np.moveaxis(a_iso, 0, -1), th_t, ph_t, th_r, ph_r)[0]
    # projected onto the two bases the recovered J reproduces every basis contraction
    assert np.allclose(np.swapaxes(br[0], 0, 1) @ j @ bt[0], np.swapaxes(br[0], 0, 1) @ j_true @ bt[0], atol=1e-12)
    assert d_r.shape == (1, 3)


def test_bank_sample_matches_grid_points_and_wraps_phi():
    b = P.Bank(fake_bank())
    th = np.deg2rad(np.array([30.0, 90.0]))
    ph = np.deg2rad(np.array([-180.0, 45.0]))
    et, ep = b.sample(th, ph)
    assert np.allclose(et[:, 0], b.e_theta[:, 6, 0]) and np.allclose(ep[:, 1], b.e_phi[:, 18, 45])
    et2, _ = b.sample(th[:1], ph[:1] + 2 * np.pi)
    assert np.allclose(et2[:, 0], et[:, 0])


def test_canonical_order_is_stable_under_permutation_and_angle_jitter():
    rng = np.random.default_rng(1)
    n = 30
    tau = np.round(rng.uniform(1e-8, 2e-7, n), 12)
    tau[5] = tau[6]                                        # degenerate delay
    ang = rng.uniform(-3, 3, (4, n))
    o1 = P.canonical_order(tau, *ang)
    perm = rng.permutation(n)
    jitter = ang[:, perm] + rng.normal(scale=3e-6, size=(4, n))
    o2 = P.canonical_order(tau[perm], *jitter)
    assert np.array_equal(tau[o1], tau[perm][o2])
    assert np.allclose(ang[:, o1], jitter[:, o2], atol=1e-4)


def test_interp_jones_exact_at_nodes_and_accurate_for_smooth_response():
    f = np.linspace(6.25e9, 6.75e9, 257)
    rng = np.random.default_rng(2)
    base = rng.normal(size=(3, 3, 3)) + 1j * rng.normal(size=(3, 3, 3))
    delay = np.array([1e-9, 2e-9, 3e-9])[:, None, None]
    j = base[None] * np.exp(-2j * np.pi * (f[:, None, None, None] - f[0]) * delay[None]) / (f[:, None, None, None] / f[0])
    nodes = np.unique(np.round(np.linspace(0, 256, 17)).astype(int))
    out = P.interp_jones(j[nodes], f[nodes], f)
    assert np.allclose(out[nodes], j[nodes])
    assert np.linalg.norm(out - j) / np.linalg.norm(j) < 1e-3
    assert P.interp_jones(j, f, f) is j


def test_path_signature_detects_matches_and_unmatched():
    from qclean_uwb.features.reflection_attribution import image_delays
    tx, rx = np.array([4.0, 0.0, 2.65]), np.array([7.0, 0.3, 0.45])
    table = image_delays(tx, rx, 20.0, 1.2, 2.7)
    tau = np.array([table[()], table[("floor",)], 1.234e-7])
    sig, unmatched = path_signature(tau, tx, rx, 20.0, 1.2, 2.7)
    assert sig == sorted(["LOS", "floor"]) and unmatched == 1
    assert signature_diff(sig, ["LOS"]) == dict(removed=["floor"], added=[])


def test_equal_image_sequences_are_one_class():
    from qclean_uwb.features.reflection_attribution import image_delays
    tx, rx = np.array([4.0, 0.0, 2.65]), np.array([7.0, 0.0, 0.45])           # robot on the corridor axis: wall_y_neg == wall_y_pos
    table = image_delays(tx, rx, 20.0, 1.2, 2.7)
    assert abs(table[("end_x_max", "floor", "end_x_max")] - table[("floor",)]) < 1e-13
    sig, unmatched = path_signature([table[("floor",)], table[("wall_y_neg",)], table[("wall_y_pos",)]], tx, rx, 20.0, 1.2, 2.7)
    assert unmatched == 0 and sig.count("floor") == 1 and sig.count("wall_y_neg") == 2 and "end_x_max>floor>end_x_max" not in sig


def test_align_paths_matches_degenerate_delays_by_direction():
    rng = np.random.default_rng(3)
    n = 12
    tau = np.round(rng.uniform(1e-8, 2e-7, n), 12)
    tau[3] = tau[4] = tau[5]                                  # three paths with the same delay, different directions
    ang = rng.uniform(-3, 3, (4, n))
    ref_dirs = P.path_directions(*ang)
    perm_true = rng.permutation(n)
    jitter = ang[:, perm_true] + rng.normal(scale=3e-6, size=(4, n))
    got = P.align_paths(tau, ref_dirs, tau[perm_true], P.path_directions(*jitter))
    assert got is not None
    perm, worst = got
    assert np.array_equal(perm_true[perm], np.arange(n)) and worst < 1e-4


def test_align_paths_rejects_changed_path_set():
    tau = np.array([1e-8, 2e-8, 3e-8])
    d = np.eye(3, 6)
    assert P.align_paths(tau, d, tau + np.array([0, 0, 1e-15]), d) is not None   # 1 ulp float32 jitter is accepted
    assert P.align_paths(tau, d, tau + np.array([0, 0, 1e-11]), d) is None
    assert P.align_paths(tau, d, tau, d + 0.5) is None


def _fake_trace(tmp_path, tag, status="OK", unmatched=0):
    rng = np.random.default_rng(5)
    n, k = 6, 5
    freqs = np.linspace(6.2504e9, 6.7496e9, 257)
    nodes = np.unique(np.round(np.linspace(0, 256, k)).astype(int))
    jones = (rng.normal(size=(len(nodes), n, 3, 3)) + 1j * rng.normal(size=(len(nodes), n, 3, 3))) * 1e-3
    ang = np.array([rng.uniform(2.0, 3.0, n), rng.uniform(-3, 3, n), rng.uniform(0.2, 1.0, n), rng.uniform(-3, 3, n)])
    np.savez(tmp_path / f"{tag}_trace.npz", jones=jones, tau=np.sort(rng.uniform(2e-8, 1e-7, n)), ang=ang, node_bins=nodes, node_freq_hz=freqs[nodes],
             x=1.0, y=0.0, signature=np.array(["LOS"]), unmatched=unmatched, status=status, flagged_bins=np.array([], int), path_counts=np.full(len(nodes), n))


def test_assemble_maps_poses_to_rows_and_flags_missing_or_unusable_traces(tmp_path):
    from test_drivesim_hs_lut import ideal_banks
    from qclean_uwb.drivesim import rf_store as R
    banks = ideal_banks()
    _fake_trace(tmp_path, "x7.0000_y0.0000")
    poses = [dict(pose_id=0, x=7.0, y=0.0, yaw_body_deg=0.0), dict(pose_id=1, x=7.0, y=0.0, yaw_body_deg=30.0), dict(pose_id=2, x=8.0, y=0.0, yaw_body_deg=0.0)]
    h, rep = R.assemble(poses, [tmp_path], banks, 45.0, allow_missing=True)
    assert rep["missing"] == ["x8.0000_y0.0000"] and not rep["complete"] and np.isnan(h[2]).all()
    direct = R.h_for_antenna_yaws(R.load_trace(tmp_path / "x7.0000_y0.0000_trace.npz"), banks, [45.0, 75.0])
    np.testing.assert_allclose(h[0], direct[0])
    np.testing.assert_allclose(h[1], direct[1])
    with pytest.raises(ValueError):
        R.assemble(poses, [tmp_path], banks, 0.0)
    _fake_trace(tmp_path, "x8.0000_y0.0000", status="PATH_SET_CHANGED_WITH_FREQUENCY")
    h2, rep2 = R.assemble(poses, [tmp_path], banks, 0.0, allow_missing=True)
    assert rep2["unusable"][0]["tag"] == "x8.0000_y0.0000"


def test_match_partial_reports_missing_and_new_paths():
    tau = np.array([1e-8, 2e-8, 3e-8, 4e-8])
    d = np.eye(4, 6)
    match, extra = P.match_partial(tau, d, tau[[0, 2, 3]], d[[0, 2, 3]])
    assert match.tolist() == [0, -1, 1, 2] and len(extra) == 0
    match, extra = P.match_partial(tau[:3], d[:3], np.r_[tau[:3], 9e-8], np.vstack([d[:3], 0.5 * np.ones((1, 6))]))
    assert match.tolist() == [0, 1, 2] and extra.tolist() == [3]


def test_interp_handles_a_path_that_vanishes_inside_the_band_without_ringing():
    f = np.linspace(6.25e9, 6.75e9, 257)
    nodes = np.unique(np.round(np.linspace(0, 256, 17)).astype(int).tolist() + [148, 149])
    amp = np.array([1.0, 0.05])                                    # path 1 exists up to bin 148 and is then dropped by the solver
    j = np.zeros((len(f), 2, 3, 3), complex)
    j[:, 0] = 1.0
    j[:148 + 1, 1] = 0.05
    present = np.ones((len(nodes), 2), bool)
    present[:, 1] = np.array(nodes) <= 148
    jn = j[nodes] * np.where(present, 1.0, 0.0)[:, :, None, None]
    out = P.interp_jones(jn, f[nodes], f, present=present)
    assert np.allclose(out[149:, 1], 0.0) and np.allclose(out[:149, 1], 0.05, atol=1e-6)
    plain = P.interp_jones(jn, f[nodes], f)
    assert np.abs(plain[:, 1] - j[:, 1]).max() > np.abs(out[:, 1] - j[:, 1]).max()
