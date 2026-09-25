"""Explicit finite-path synthetic channel consumer, not physical completeness."""
import hashlib
import json
from pathlib import Path
import numpy as np
from .matlab_rng import matlab_mt19937_randn
from .features import extract_first_path
from .rf_channel_closure import contribution_cir
from .g2_relocated_inputs import sha

ARMS = {'CP': [0, 1], 'LP_AXIS': [2, 3], 'LP_DIAG': [4, 5]}


def observe(h, frequencies, row, noise, detector):
    """Fixed absolute receiver noise; shared samples across paired arms."""
    h = np.asarray(h, complex)
    if h.shape != (257, 6, 6) or not np.isfinite(h).all():
        raise ValueError('FINITE_257_BY_6_BY_6_CHANNEL_REQUIRED')
    identity = dict(scene=row['scene_id'], link=row['link_id'],
                    frame=row.get('frame'), replicate=0, seed_base=noise['seed_base'])
    seed = int.from_bytes(hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).digest()[:4], 'little')
    flat = matlab_mt19937_randn(seed, 2*257*4)
    sample = (flat[:257*4]+1j*flat[257*4:]).reshape((257,2,2), order='F')*np.sqrt(noise['noise_var_H_bin']/2)
    arrays = {}; records = []
    for arm, indices in ARMS.items():
        clean = h[:, indices][:, :, indices]
        noisy = clean+sample
        cir, time = contribution_cir(noisy, frequencies)
        clean_cir, _ = contribution_cir(clean, frequencies)
        peak_by_branch = np.max(abs(cir), axis=0)
        branch = np.unravel_index(np.argmax(peak_by_branch), (2,2))
        detected = bool(peak_by_branch[branch] >= detector['threshold_value'])
        index, delay, _ = extract_first_path(cir[:, branch[0], branch[1]], time)
        record = dict(arm=arm, seed=seed,
                      state='DETECTED_CANDIDATE' if detected else 'MISSED_OR_NO_SIGNAL',
                      rx_mode=int(branch[0]), tx_mode=int(branch[1]),
                      first_path_index=index if detected else None,
                      detected_delay_s=delay if detected else None,
                      detected_range_m=delay*299792458. if detected else None,
                      range_error_m=delay*299792458.-float(np.linalg.norm(np.array(row['rx'])-row['tx'])) if detected else None,
                      peak_amplitude=float(peak_by_branch[branch]),
                      mean_received_power_w=float(np.mean(abs(clean)**2)*noise['tx_incident_power_w_per_active_mode']))
        arrays.update({arm+'_H':clean,arm+'_H_noisy':noisy,arm+'_CIR':cir,arm+'_CIR_clean':clean_cir})
        records.append(record)
    arrays.update(time_s=time, noise_H=sample, frequencies_hz=np.asarray(frequencies))
    return arrays,records


def load_scoped_link(root, link_id, *, accept_scoped_model=False):
    """Read manifest-bound new coordinates and observations through one entrypoint."""
    if not accept_scoped_model:
        raise ValueError('EXPLICIT_SCOPED_MODEL_ACCEPTANCE_REQUIRED')
    root=Path(root).resolve();manifest=json.loads((root/'MANIFEST.json').read_text(encoding='utf8'))
    def checked(name):
        p=root/name
        if p.resolve().parent!=root or manifest['outputs'].get(name)!=sha(p):
            raise ValueError('SCOPED_OUTPUT_HASH_MISMATCH')
        return p
    contract=json.loads(checked('MODEL_CONTRACT.json').read_text(encoding='utf8'))
    rows=json.loads(checked('PRODUCTION_INPUTS.json').read_text(encoding='utf8'))
    matched=[r for r in rows if r['link_id']==link_id]
    if len(matched)!=1:raise ValueError('LINK_NOT_UNIQUELY_BOUND')
    row=matched[0];detail=json.loads(checked(link_id+'_RESULT.json').read_text(encoding='utf8'))
    if row['tx']!=detail['tx'] or row['rx']!=detail['rx'] or row['scene_id']!=detail['scene_id']:
        raise ValueError('COORDINATE_BINDING_MISMATCH')
    if detail['state']!='COMPUTED_SCOPED_MODEL':raise ValueError('SCOPED_COMPUTATION_FAILED')
    with np.load(checked(link_id+'_CHANNEL.npz')) as a:data={k:a[k].copy() for k in a.files}
    return dict(input=row,result=detail,channel=data,contract=contract,
                physical_completeness_established=False)
