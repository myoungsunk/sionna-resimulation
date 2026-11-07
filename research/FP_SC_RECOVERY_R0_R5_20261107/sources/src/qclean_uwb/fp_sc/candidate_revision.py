"""E1 candidate revision R1 only; not installed in the followup adapter."""
from copy import deepcopy
import numpy as np
from . import candidates as base

ARMS = ('V0', 'VA', 'VB', 'VAB')
REVISION = 'FP_SC_E1_CANDIDATE_R1'


def generate_revision(cir, arm, config=base.CandidateConfig()):
    if arm not in ARMS:
        raise ValueError('UNKNOWN_REVISION_ARM')
    original = base.generate_pools(cir, config)
    if arm == 'V0':
        return original
    source = original['TWO_PORT_UNION']
    if not source['raw']['valid']:
        return original
    amplitude = np.abs(cir)
    noise = source['noise_amplitude_floor']
    numeric = source['numeric_amplitude_floor']
    global_peak = source['raw']['peak']
    lobes = deepcopy(source['lobes'])
    for lobe in lobes:
        p, v, rx = lobe['peak_tap'], lobe['left_local_valley'], lobe['rx']
        peak = lobe['peak_amplitude']
        lobe['original_reason'] = lobe['reason']
        lobe['original_candidate_taps'] = list(lobe['candidate_taps'])
        lobe['left_rise'] = float(peak - amplitude[v, rx])
        lobe['support_kind'] = 'BILATERAL' if lobe['eligible'] else 'NONE'
        rescued = (arm in ('VB', 'VAB') and lobe['reason'] == 'BELOW_PROMINENCE'
                   and not lobe['boundary'] and peak >= max(noise, numeric)
                   and amplitude[v, rx] < config.leading_edge_fraction * peak
                   and lobe['left_rise'] >= max(noise, config.eta_prominence * global_peak))
        if rescued:
            edge = v + int(np.flatnonzero(amplitude[v:p+1, rx] >= config.leading_edge_fraction * peak)[0])
            threshold = max(noise, numeric, config.local_candidate_fraction * peak)
            lobe.update(edge_tap=edge, candidate_amplitude_floor=float(threshold),
                        candidate_taps=[n for n in (edge-1, edge, edge+1)
                                        if v <= n <= p and amplitude[n, rx] >= threshold],
                        reason='LEFT_RISE_SUPPORTED', support_kind='LEFT_RISE')
            lobe['eligible'] = bool(lobe['candidate_taps'])
        if lobe['eligible'] and arm in ('VA', 'VAB'):
            lobe['candidate_taps'] = sorted(set(lobe['candidate_taps']) | {
                n for n in range(lobe['edge_tap'], p+1)
                if amplitude[n, rx] >= lobe['candidate_amplitude_floor']})
    by_id = {l['lobe_id']: l for l in lobes}
    result = {}
    for mode in base.MODES:
        pool = base._pool(mode, cir, source['raw'], lobes, config, noise, numeric)
        for candidate in pool['candidates']:
            for support in candidate['support_records']:
                lobe = by_id[support['lobe_id']]
                support.update(support_kind=lobe['support_kind'], left_rise=lobe['left_rise'],
                               left_local_valley=lobe['left_local_valley'],
                               right_local_valley=lobe['right_local_valley'])
        pool.update(candidate_revision=REVISION, arm=arm, support_semantics_version='CIR_SUPPORT_R1_NOT_SELECTOR_SCORE',
                    candidate_config_sha256=base._digest({'revision':REVISION,'arm':arm,'config':pool['config']}))
        del pool['pool_hash']
        pool['pool_hash'] = base._digest(pool)
        result[mode] = pool
    return result
