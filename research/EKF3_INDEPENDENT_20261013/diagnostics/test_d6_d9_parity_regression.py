"""Bitwise frozen initialization: catches the observed recursive parity regression."""
import numpy as np
from d6_d9_common import DiagnosticFilter
from run_d5_regimes import P0_COV

def test_initial_covariance_preserves_frozen_float_values_and_ownership():
    assert .01 != .1**2  # the actual root cause, not a relaxed tolerance
    for bias in (False, True):
        f = DiagnosticFilter(np.zeros(3), bias_state=bias)
        assert np.array_equal(f.Ppose, P0_COV)
        assert not np.shares_memory(f.Ppose, P0_COV)
        f.Ppose[0, 0] = 10
        assert P0_COV[0, 0] == .1**2


def test_e1_outer_fold_contract_rejects_old_or_wrong_fold():
    import pytest
    from d9_quality_aware_fusion import validate_e1_outer_fold
    from d6_d9_common import P3_SHA256, P3_MODEL
    import json, hashlib
    root = dict(e1_outer_fold_contract='SINGLE_OUTER_ROUTE_EXCLUDED_FOLD_FOR_ALL_LABELS',
                e1_frozen_model_sha256=P3_SHA256, e1_model_family_selection_nested=False)
    coeff = json.loads(P3_MODEL.read_text())['loro_fold_params']['R2']['E1']
    sha = hashlib.sha256(json.dumps(coeff, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    fold = dict(e1_label_outer_excluded_route='R2', e1_outer_coefficients_sha256=sha)
    validate_e1_outer_fold(root, fold, 'R2')
    for bad_root, bad_fold in [({}, fold), (root, {}),
            (root, dict(e1_label_outer_excluded_route='R4')),
            (root | {'e1_frozen_model_sha256': 'bad'}, fold)]:
        with pytest.raises(RuntimeError, match='outer-fold'):
            validate_e1_outer_fold(bad_root, bad_fold, 'R2')
