"""Per-target post-processing for the full native campaign (no RF calls).

Raw native a/tau -> complex128 H (re-summed and compared with the producer
sum) -> fixed-operating-point observation (g2_scoped_channel.observe: absolute
noise, paired across arms, Hann 1028-tap CIR, detector) -> path metrics.

Only full-band (257 bins, 3 arms) raw outputs are accepted. RD-LoS /
HB-near-delay / HB-prior stay null (DEFERRED_BY_USER).
"""
import datetime
import json
import sys
from pathlib import Path

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


class FinishRefused(RuntimeError):
    pass


def finish_batch(code_root, root, inputs_dir, batch, runs_dir='batches'):
    """Finish one batch against the current expected keys; see finish_sionna_full.py."""
    from .g2_full_runner import (atomic_write_bytes, atomic_write_json, attempts, batch_complete,
                                 expected_run_key, file_sha, npz_bytes, production_complete, production_key,
                                 verified_receipt)
    root, inputs = Path(root), Path(root)/inputs_dir
    config = json.loads((inputs/'CONFIG.json').read_text(encoding='utf8'))
    batch_dir = root/runs_dir/batch['batch_id']
    key = expected_run_key(code_root, inputs)
    pkey = production_key(code_root, inputs, key)
    prod = batch_dir/'production'
    if production_complete(batch_dir, batch, pkey):
        return dict(batch_id=batch['batch_id'], status='ALREADY_FINISHED_FOR_CURRENT_KEY')
    if prod.exists() and any(prod.iterdir()):
        raise FinishRefused('PRODUCTION_STALE_OR_INCOMPLETE: existing production/ does not match the current '
                            'key or misses outputs; preserved, not overwritten')
    if not batch_complete(batch_dir, batch, key):
        raise FinishRefused('RAW_KEY_NOT_CURRENT_OR_BATCH_INCOMPLETE')
    att = next(att for att in reversed(attempts(batch_dir)) if (att/'COMPLETE.json').is_file()
               and json.loads((att/'COMPLETE.json').read_text(encoding='utf8'))['run_key'] == key)
    manifest = json.loads((att/'MANIFEST.json').read_text(encoding='utf8'))
    wanted, targets = set(batch['target_ids']), {}
    with (inputs/'TARGETS.jsonl').open(encoding='utf8') as fh:
        for line in fh:
            t = json.loads(line)
            if t['target_id'] in wanted:
                targets[t['target_id']] = t
    prod.mkdir(exist_ok=True)
    outputs, states = {}, {}
    for tid in batch['target_ids']:
        o = manifest['outputs'][tid]
        raw_dir = batch_dir/o['attempt']/'raw'
        if not verified_receipt(raw_dir, tid, key):
            raise FinishRefused(f'RAW_NOT_VERIFIED:{tid}')
        with np.load(raw_dir/f'{tid}.npz') as z:
            raw = {k: z[k] for k in z.files}
        arrays, record = finish_target(raw, targets[tid], config['noise'], config['detector'])
        record.update(raw_npz=f"{o['attempt']}/raw/{tid}.npz", raw_npz_sha256=o['npz_sha256'])
        outputs[f'{tid}_CHANNEL.npz'] = atomic_write_bytes(prod/f'{tid}_CHANNEL.npz', npz_bytes(arrays))
        outputs[f'{tid}_RESULT.json'] = atomic_write_json(prod/f'{tid}_RESULT.json', record)
        for d in record['detections']:
            states[d['state']] = states.get(d['state'], 0) + 1
    atomic_write_json(prod/'MANIFEST.json', dict(
        batch_id=batch['batch_id'], production_key=pkey, outputs=outputs,
        timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), command=sys.argv))
    atomic_write_json(prod/'FINISHED.json', dict(batch_id=batch['batch_id'], targets=len(batch['target_ids']),
                                                 production_key=pkey, detection_states=states, rf_calls=0,
                                                 manifest_sha256=file_sha(prod/'MANIFEST.json')))
    if not production_complete(batch_dir, batch, pkey):
        raise FinishRefused('PRODUCTION_SELF_CHECK_FAILED')
    return dict(batch_id=batch['batch_id'], status='FINISHED', targets=len(batch['target_ids']),
                detection_states=states)
