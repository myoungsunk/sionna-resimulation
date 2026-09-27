import json
from pathlib import Path

import numpy as np
import pytest

from rt_cp_uwb_py.g2_full_finish import FREQS, N_BINS, finish_target, resum
from rt_cp_uwb_py.g2_scoped_channel import ARMS

CONFIG = json.loads((Path(__file__).resolve().parents[1]/
                     'results/SIONNA_NATIVE41_REFRESH_20260925_01a0d84e/CONFIG.json').read_text())
TARGET = dict(target_id='f'*64, family='L1', scene_id='S', tx=[0., 0., 2.], rx=[3., 0., 1.2],
              frame_ref=None, geometric_range_m=float(np.hypot(3, .8)))


def raw_two_paths(bins=range(N_BINS), los=True):
    """Synthetic native output: one LoS (no interaction) + one specular path per arm/bin."""
    tau = np.array([np.hypot(3, .8), np.hypot(3, 3.2)])/299792458.
    raw = dict(bins=np.array(list(bins)), frequencies_hz=FREQS[list(bins)], tx_m=np.array(TARGET['tx']),
               rx_m=np.array(TARGET['rx']))
    h = np.zeros((len(raw['bins']), 3, 2, 2), complex)
    for k, fi in enumerate(raw['bins']):
        for ai, arm in enumerate(ARMS):
            a = np.zeros((2, 2, 2), np.complex64)
            a[..., 0] = 1e-3*(1 if los else 0); a[..., 1] = -4e-4
            raw[f'{arm}_a_{fi:03d}'] = a; raw[f'{arm}_tau_{fi:03d}'] = tau
            inter = np.zeros((3, 2), np.uint32); inter[0, 1] = 1
            raw[f'{arm}_interactions_{fi:03d}'] = inter; raw[f'{arm}_valid_{fi:03d}'] = np.array([los, True])
            h[k, ai] = np.sum(a.astype(complex)*np.exp(-2j*np.pi*FREQS[fi]*tau)[None, None, :], axis=-1)
    raw['H_arms'] = h
    return raw


def test_three_bin_smoke_output_is_rejected_by_finish():
    with pytest.raises(ValueError, match='FULL_BAND_REQUIRED'):
        resum(raw_two_paths(bins=[0, 128, 256]))


def test_resum_detects_tampered_producer_sum():
    raw = raw_two_paths()
    raw['H_arms'] = raw['H_arms'].copy(); raw['H_arms'][10, 1, 0, 0] += 1e-6
    with pytest.raises(ValueError, match='H_RESUM_MISMATCH'):
        resum(raw)


def test_finish_two_path_channel_labels_and_detection():
    arrays, record = finish_target(raw_two_paths(), TARGET, CONFIG['noise'], CONFIG['detector'])
    assert record['labels']['NoLoS'] is False and record['labels']['RD_LoS'] is None
    assert record['labels']['taxonomy_status'] == 'DEFERRED_BY_USER'
    assert all(d['state'] == 'DETECTED_CANDIDATE' for d in record['detections'])
    m = record['native_midband_path_metrics']['CP']
    assert m['paths_with_surface_reflection'] == 1 and m['native_los_present']
    assert np.isclose(m['incoherent_reflection_path_power_fraction'], .16/1.16)
    np.testing.assert_array_equal(arrays['CP_H_noisy'], arrays['CP_H'] + arrays['noise_H'])
    np.testing.assert_array_equal(arrays['LP_AXIS_H_noisy'], arrays['LP_AXIS_H'] + arrays['noise_H'])


def test_nolos_when_no_valid_direct_path():
    _, record = finish_target(raw_two_paths(los=False), TARGET, CONFIG['noise'], CONFIG['detector'])
    assert record['labels']['NoLoS'] is True
