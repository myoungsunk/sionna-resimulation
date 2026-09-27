"""Per-target post-processing for the full native campaign (no RF calls).

Raw native a/tau -> complex128 H (re-summed and compared with the producer
sum) -> fixed-operating-point observation (g2_scoped_channel.observe: absolute
noise, paired across arms, Hann 1028-tap CIR, detector) -> path metrics.

Only full-band (257 bins, 3 arms) raw outputs are accepted. RD-LoS /
HB-near-delay / HB-prior stay null (DEFERRED_BY_USER).
"""
import numpy as np

from .g2_native_channel import sum_native_paths
from .g2_scoped_channel import ARMS, observe

N_BINS = 257
FREQS = 6250400000. + 1950000.*np.arange(N_BINS)
SPECULAR, REFRACTION = 1, 4  # sionna.rt InteractionType bit flags


def resum(raw):
    """Recompute H from native a/tau for every bin and arm; return (H_arms, max_abs_diff)."""
    bins = np.asarray(raw['bins'])
    if bins.tolist() != list(range(N_BINS)):
        raise ValueError('FULL_BAND_REQUIRED')
    np.testing.assert_array_equal(raw['frequencies_hz'], FREQS)
    h = np.zeros((N_BINS, len(ARMS), 2, 2), np.complex128)
    for fi in range(N_BINS):
        for ai, arm in enumerate(ARMS):
            h[fi, ai] = sum_native_paths(raw[f'{arm}_a_{fi:03d}'], raw[f'{arm}_tau_{fi:03d}'], FREQS[fi])
    diff = float(np.max(np.abs(h - raw['H_arms']))) if raw['H_arms'].size else 0.
    scale = float(np.max(np.abs(h))) if h.size else 0.
    if diff > 1e-12*max(scale, 1e-30) + 1e-300:
        raise ValueError('H_RESUM_MISMATCH')
    return h, diff


def six_port(h_arms):
    h = np.zeros((N_BINS, 6, 6), np.complex128)
    for ai, ix in enumerate(ARMS.values()):
        for ri, r in enumerate(ix):
            for ti, t in enumerate(ix):
                h[:, r, t] = h_arms[:, ai, ri, ti]
    return h


def path_metrics(raw, fi=128):
    out = {}
    for arm in ARMS:
        inter = np.asarray(raw[f'{arm}_interactions_{fi:03d}'])
        valid = np.asarray(raw[f'{arm}_valid_{fi:03d}']).reshape(-1).astype(bool)
        inter = inter.reshape(inter.shape[0], -1)
        a = np.asarray(raw[f'{arm}_a_{fi:03d}'], np.complex128)
        powers = np.sum(np.abs(a)**2, axis=(0, 1))
        reflected = np.any((inter & SPECULAR) != 0, axis=0)
        transmitted = np.any((inter & REFRACTION) != 0, axis=0)
        los = np.all(inter == 0, axis=0) & valid
        total = float(powers[valid].sum()) if valid.size else 0.
        out[arm] = dict(native_los_present=bool(los.any()), valid_paths=int(valid.sum()),
                        paths_with_surface_reflection=int(np.sum(reflected & valid)),
                        paths_with_slab_transmission=int(np.sum(transmitted & valid)),
                        incoherent_reflection_path_power_fraction=(float(powers[reflected & valid].sum())/total
                                                                   if total else None),
                        definition='incoherent sum of |a|^2 per path at bin 128; not an interference-inclusive '
                                   'channel power ratio')
    return out


def finish_target(raw, target, noise, detector):
    """Return (channel arrays, result record) for one full-band raw output."""
    h_arms, diff = resum(raw)
    np.testing.assert_array_equal(raw['tx_m'], target['tx'])
    np.testing.assert_array_equal(raw['rx_m'], target['rx'])
    frame = target['frame_ref']['frame'] if target.get('frame_ref') else None
    row = dict(scene_id=target['scene_id'], link_id=target['target_id'], frame=frame,
               tx=target['tx'], rx=target['rx'])
    arrays, detections = observe(six_port(h_arms), FREQS, row, noise, detector)
    arrays.update(H_arms=h_arms, arms=np.array(list(ARMS)), tx_m=np.array(target['tx']),
                  rx_m=np.array(target['rx']), valid_port_pairs=np.array(
                      [[r, t] for ix in ARMS.values() for r in ix for t in ix]))
    metrics = path_metrics(raw)
    los = {arm: m['native_los_present'] for arm, m in metrics.items()}
    record = dict(target_id=target['target_id'], family=target['family'], scene_id=target['scene_id'],
                  tx=target['tx'], rx=target['rx'], geometric_range_m=target['geometric_range_m'],
                  detections=detections, native_midband_path_metrics=metrics, resum_max_abs_diff=diff,
                  labels=dict(NoLoS=None if len(set(los.values())) != 1 else (not next(iter(los.values()))),
                              NoLoS_basis='native valid LoS path at bin 128, all arms must agree',
                              NoLoS_arm_disagreement=len(set(los.values())) != 1,
                              RD_LoS=None, HB_near_delay=None, HB_prior=None, taxonomy_status='DEFERRED_BY_USER'),
                  path_index_policy='frequency-local indices; do not assume index identity across bins',
                  noise_seed_identity='scene_id, target_id, frame, replicate=0, seed_base (no batch/attempt/arm)')
    return arrays, record
