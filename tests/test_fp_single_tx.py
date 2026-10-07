import numpy as np
import pytest

from qclean_uwb.features.fp_power import first_path_power, first_path_power_single_tx, signed_port_ratio, signed_s_single_tx

FREQ = np.linspace(6.0e9, 8.0e9, 257)


def path(delay_s, amp):
    return amp * np.exp(-2j * np.pi * FREQ * delay_s)


def channel(amps_by_branch, delays_by_branch):
    h = np.zeros((FREQ.size, 2, 2), complex)
    for (rx, tx), a in amps_by_branch.items():
        h[:, rx, tx] = path(delays_by_branch[(rx, tx)], a)
    return h


def test_signed_ratio_matches_definition_and_handles_zero():
    assert signed_port_ratio(3.0, 1.0) == pytest.approx(0.5)
    assert np.isnan(signed_port_ratio(0.0, 0.0))


def test_single_path_s_equals_power_ratio_for_column_zero():
    d = 40e-9
    h = channel({(0, 0): 0.3, (1, 0): 0.9}, {(0, 0): d, (1, 0): d})
    s, power, _, _ = signed_s_single_tx(h, FREQ, tx=0)
    p1, p2 = power
    assert s == pytest.approx((0.3**2 - 0.9**2) / (0.3**2 + 0.9**2), rel=1e-9)
    assert p2 > p1


def test_other_tx_column_does_not_change_the_selected_column_result():
    d = 40e-9
    base = channel({(0, 0): 0.3, (1, 0): 0.9}, {(0, 0): d, (1, 0): d})
    with_other = base + channel({(0, 1): 5.0}, {(0, 1): 80e-9})
    a = first_path_power_single_tx(base, FREQ, 0)
    b = first_path_power_single_tx(with_other, FREQ, 0)
    np.testing.assert_allclose(a[0], b[0])
    assert a[1] == b[1]


def test_four_branch_rule_differs_when_the_strongest_branch_is_in_the_other_column():
    h = channel({(0, 0): 0.3, (1, 0): 0.9, (0, 1): 5.0}, {(0, 0): 40e-9, (1, 0): 40e-9, (0, 1): 80e-9})
    _, idx4, _ = first_path_power(h, FREQ)
    _, idx1, _ = first_path_power_single_tx(h, FREQ, 0)
    assert idx4 != idx1


def test_column_index_selects_the_other_port():
    h = channel({(0, 0): 1.0, (1, 0): 1.0, (0, 1): 2.0, (1, 1): 0.5}, {k: 30e-9 for k in [(0, 0), (1, 0), (0, 1), (1, 1)]})
    s0 = signed_s_single_tx(h, FREQ, 0)[0]
    s1 = signed_s_single_tx(h, FREQ, 1)[0]
    assert s0 == pytest.approx(0.0, abs=1e-12) and s1 > 0.5
