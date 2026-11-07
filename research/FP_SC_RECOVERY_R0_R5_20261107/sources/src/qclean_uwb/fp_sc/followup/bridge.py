"""Lossless candidate-to-Evidence bridge. No selection/history/physics execution.

rf support is a PROPOSED ranking score, not probability or a trust threshold.
Archived pools lack complex phase: phase_available=False records this explicitly.
"""
import json
import math
from dataclasses import dataclass, asdict
import numpy as np
from ..candidates import CandidateConfig, MODES, _digest
from ..candidate_revision import ARMS, REVISION, generate_revision
from .contracts import ContractError
from .selection import Candidate, Evidence

BRIDGE = 'FP_SC_VAB_BRIDGE_R1'
SEMANTICS = 'CIR_SUPPORT_R1_NOT_SELECTOR_SCORE'
RECIPE = {'version': BRIDGE, 'eligibility': 'raw_valid&&!overflow&&polarization_valid&&supported',
          'ranking': 'max(clip(kind_strength/G)*clip(tap_amplitude/peak_amplitude))',
          'kind_strength': {'BILATERAL': 'prominence', 'LEFT_RISE': 'left_rise'},
          'history': 'NOT_VALIDATED_FALSE', 'selector_ready': False}
RECIPE_SHA = _digest(RECIPE)


@dataclass(frozen=True)
class BridgeConfig:
    arm: str
    mode: str
    candidate_config_sha256: str
    recipe_sha256: str = RECIPE_SHA

    def validate(self):
        if self.arm not in ARMS or self.mode not in MODES:
            raise ContractError('BRIDGE_ARM_OR_MODE')
        if self.recipe_sha256 != RECIPE_SHA:
            raise ContractError('BRIDGE_RECIPE_MISMATCH')
        if len(self.candidate_config_sha256) != 64:
            raise ContractError('BRIDGE_CONFIG_HASH_REQUIRED')


def candidate_config_sha(arm, config):
    return _digest(config if arm == 'V0' else {'revision': REVISION, 'arm': arm, 'config': config})


def adapt_pool(pool, config: BridgeConfig, cir=None):
    config.validate()
    if pool['mode'] != config.mode:
        raise ContractError('BRIDGE_MODE_MISMATCH')
    expected = candidate_config_sha(config.arm, pool['config'])
    if expected != config.candidate_config_sha256:
        raise ContractError('BRIDGE_CANDIDATE_CONFIG_MISMATCH')
    raw = pool['raw']
    # The R1 producer intentionally returns legacy empty pools on invalid input.
    if config.arm != 'V0' and raw['valid']:
        if (pool.get('candidate_revision') != REVISION or pool.get('arm') != config.arm or
                pool.get('support_semantics_version') != SEMANTICS or
                pool.get('candidate_config_sha256') != expected):
            raise ContractError('BRIDGE_REVISION_MISMATCH')
    elif config.arm == 'V0' and pool.get('candidate_revision'):
        raise ContractError('BRIDGE_UNEXPECTED_REVISION')
    if raw['valid'] and (not math.isfinite(raw['peak']) or raw['peak'] <= 0):
        raise ContractError('BRIDGE_INVALID_PEAK')
    if bool(pool['overflow']) != (len(pool['candidates']) > pool['config']['maximum_usable_candidates']):
        raise ContractError('BRIDGE_OVERFLOW_MISMATCH')
    if cir is not None:
        cir = np.asarray(cir)
        if cir.shape != (1028, 2) or not np.iscomplexobj(cir):
            raise ContractError('BRIDGE_CIR_SHAPE')
    output = []
    for r in pool['candidates']:
        n = r['tap']; records = r['support_records']
        valid_s = bool(r['polarization_valid'])
        if valid_s and (r['signed_s'] is None or not math.isfinite(r['signed_s']) or abs(r['signed_s']) > 1):
            raise ContractError('BRIDGE_INVALID_SIGNED_S')
        if r['supported'] and not records:
            raise ContractError('BRIDGE_SUPPORT_WITHOUT_PROVENANCE')
        if sorted(set(s['group_id'] for s in records)) != r['group_ids']:
            raise ContractError('BRIDGE_GROUP_PROVENANCE')
        legacy, ranking = [], []
        for s in records:
            kind = s.get('support_kind', 'BILATERAL' if config.arm == 'V0' else None)
            if kind not in ('BILATERAL', 'LEFT_RISE') or s['rx'] not in (0, 1):
                raise ContractError('BRIDGE_SUPPORT_KIND_OR_RX')
            strength = s['prominence'] if kind == 'BILATERAL' else s['left_rise']
            numbers = (strength, s['prominence'], s['peak_amplitude'], s['tap_amplitude'])
            if not all(math.isfinite(x) and x >= 0 for x in numbers) or s['peak_amplitude'] <= 0:
                raise ContractError('BRIDGE_INVALID_SUPPORT_NUMBER')
            legacy.append(min(1., s['prominence']/raw['peak']) * math.exp(-abs(n-s['edge_tap'])))
            ranking.append(min(1., strength/raw['peak']) * min(1., s['tap_amplitude']/s['peak_amplitude']))
        reason = ('ORIGINAL_INVALID' if not raw['valid'] else 'OVERFLOW' if pool['overflow'] else
                  'POLARIZATION_INVALID' if not valid_s else 'NO_CIR_SUPPORT' if not r['supported'] else 'ELIGIBLE')
        phase = float(np.angle(cir[n, 0]*cir[n, 1].conjugate())) if cir is not None else 0.
        output.append(Candidate(n, r['signed_s'] if valid_s else 0., max(ranking, default=0.),
            tuple(r['group_ids']), bool(r['supported']), phase,
            selection_eligible=reason == 'ELIGIBLE', exclusion_reason=reason, polarization_valid=valid_s,
            source_signed_s=r['signed_s'], support_records_json=json.dumps(records, sort_keys=True, allow_nan=False),
            legacy_support=max(legacy, default=0.), phase_available=cir is not None))
    if [c.tap for c in output] != pool['candidate_taps']:
        raise ContractError('BRIDGE_TAP_LIST_MISMATCH')
    identity = {**asdict(config), 'bridge_revision': BRIDGE, 'candidate_revision': 'E1_ORIGINAL' if config.arm == 'V0' else REVISION,
                'support_semantics_version': SEMANTICS, 'mapping_recipe_sha256': None,
                'mapping_status': 'NOT_VALIDATED', 'raw_json': raw, 'pool_status': pool['status'],
                'candidate_metadata': [{k: v for k, v in r.items() if k != 'support_records'} for r in pool['candidates']]}
    return Evidence(raw.get('tap'), raw.get('signed_s'), bool(raw['valid']), bool(pool['overflow']),
                    tuple(output), pool['pool_hash'], json.dumps(identity, sort_keys=True, allow_nan=False), False)


class RevisionEvidenceAdapter:
    """Actual Evidence interface, explicitly configured; no SourceFFD/recursion.

    To compose with OriginalAdapter, use its new revision_evidence delegate.
    """
    def __init__(self, arm='VAB', mode='TWO_PORT_UNION'):
        if arm not in ARMS or mode not in MODES:
            raise ContractError('BRIDGE_ARM_OR_MODE')
        self.arm, self.mode = arm, mode

    def evidence(self, cir, variance=0.):
        cfg = CandidateConfig(noise_var_per_bin=variance)
        pool = generate_revision(cir, self.arm, cfg)[self.mode]
        return adapt_pool(pool, BridgeConfig(self.arm, self.mode, candidate_config_sha(self.arm, asdict(cfg))), cir)
