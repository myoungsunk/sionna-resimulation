"""Summaries and explicit production binding for native Sionna channel archives."""
import json
from pathlib import Path

import numpy as np

from .g2_native_channel import file_sha, load_native_link


def summarize_paths(coefficients, delays, interactions, valid):
    a = np.asarray(coefficients, np.complex128)
    tau = np.asarray(delays, float).reshape(-1)
    mask = np.asarray(valid, bool).reshape(-1)
    events = np.asarray(interactions).reshape(-1, len(tau)) if len(tau) else np.empty((0,0), int)
    if a.ndim != 3 or a.shape[:2] != (2,2) or a.shape[-1] != len(tau) or len(mask) != len(tau):
        raise ValueError('NATIVE_PATH_SHAPE')
    if not np.isfinite(a).all() or not np.isfinite(tau[mask]).all() or np.any(tau[mask] < 0):
        raise ValueError('INVALID_NATIVE_PATH')
    power = np.sum(abs(a)**2, axis=(0,1))
    reflected = np.any((events & 1) != 0, axis=0)
    transmitted = np.any((events & 4) != 0, axis=0)
    direct = np.all(events == 0, axis=0)
    total = float(power[mask].sum())
    delay_mean = float(np.sum(power[mask]*tau[mask])/total) if total else None
    rms = float(np.sqrt(np.sum(power[mask]*(tau[mask]-delay_mean)**2)/total)) if total else None
    return dict(valid_paths=int(mask.sum()), native_los_present=bool(np.any(direct & mask)),
        reflected_paths=int(np.sum(reflected & mask)), transmitted_paths=int(np.sum(transmitted & mask)),
        multiple_reflection_paths=int(np.sum((np.sum((events & 1)!=0,axis=0)>=2)&mask)),
        earliest_path_delay_s=float(tau[mask].min()) if mask.any() else None,
        incoherent_path_gain_sum=total,
        reflection_path_power_fraction=float(power[mask & reflected].sum()/total) if total else None,
        transmission_path_power_fraction=float(power[mask & transmitted].sum()/total) if total else None,
        power_weighted_delay_s=delay_mean, rms_path_delay_spread_s=rms)


def load_native_refresh(binding_path, link_id):
    """Load the new geometry and refreshed observations via an explicit, hash-bound root."""
    binding_path = Path(binding_path).resolve()
    b = json.loads(binding_path.read_text(encoding='utf8'))
    if b['status'] != 'NATIVE_REFRESH_COMPLETE':
        raise ValueError('REFRESH_INCOMPLETE')
    for record in b['bound_files']:
        if file_sha(record['path']) != record['sha256']:
            raise ValueError('REFRESH_BINDING_SHA_MISMATCH')
    if link_id not in b['link_ids']:
        raise ValueError('LINK_OUTSIDE_REFRESH')
    result = load_native_link(b['production_root'], link_id)
    labels = json.loads(Path(b['labels_file']).read_text(encoding='utf8'))
    matching = [r for r in labels if r['link_id'] == link_id]
    if len(matching) != 1:
        raise ValueError('REFRESH_LABEL_NOT_UNIQUE')
    result['labels'] = matching[0]
    result['geometry_root'] = b['geometry_root']
    return result

