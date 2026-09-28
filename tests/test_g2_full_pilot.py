"""Bounded S2 pilot report (RF-free) on the synthetic 2-target campaign."""
import json

import pytest

from rt_cp_uwb_py.g2_full_finish import finish_batch
from rt_cp_uwb_py.g2_full_pilot import pilot_report
from rt_cp_uwb_py.g2_full_runner import RUNTIME_CODE, attempts, file_sha
from test_g2_full_completion import ROOT, make_campaign, produce


def add_fixture(root, code=None, passed=True, calls=9):
    d = root/'02_fixtures'; d.mkdir(exist_ok=True)
    code = code or {c: file_sha(ROOT/c) for c in RUNTIME_CODE}
    (d/'LOS_FIXTURE.test.json').write_text(json.dumps(dict(code_sha256=code, passed=passed, rf_calls=calls)))


def report(root, **kw):
    return pilot_report(ROOT, root, 'IN', ['B000000'], kw.pop('rows', 2), **kw)


def test_pilot_passes_only_with_raw_production_and_fixture_for_current_keys(tmp_path):
    root, inputs, targets, batch = make_campaign(tmp_path)
    produce(root, inputs, targets, batch)
    r = report(root)
    assert r['status'] != 'S2_PILOT_PASS'
    assert 'PRODUCTION_NOT_COMPLETE_FOR_CURRENT_KEY:B000000' in r['problems']
    assert 'LOS_FIXTURE_MISSING_OR_FAILED_FOR_CURRENT_CODE' in r['problems']
    finish_batch(ROOT, root, 'IN', batch); add_fixture(root)
    r = report(root)
    assert r['status'] == 'S2_PILOT_PASS', r['problems']
    assert r['rows_verified'] == 2 and r['rf_calls_targets'] == 2*771 and r['rf_calls_fixture'] == 9
    cap = r['capacity']
    assert cap['bytes_per_row']['raw_mean'] > 0 and cap['bytes_per_row']['production_mean'] > 0
    assert cap['projection_for_remaining']['rows'] == 165009 - 2


@pytest.mark.parametrize('fixture', [dict(passed=False), dict(calls=771), dict(code={'x': 'y'})])
def test_fixture_must_have_passed_with_nine_calls_for_current_code(tmp_path, fixture):
    root, inputs, targets, batch = make_campaign(tmp_path)
    produce(root, inputs, targets, batch); finish_batch(ROOT, root, 'IN', batch); add_fixture(root, **fixture)
    assert 'LOS_FIXTURE_MISSING_OR_FAILED_FOR_CURRENT_CODE' in report(root)['problems']


def test_row_count_and_panel_readback_are_enforced(tmp_path):
    root, inputs, targets, batch = make_campaign(tmp_path)
    produce(root, inputs, targets, batch); finish_batch(ROOT, root, 'IN', batch); add_fixture(root)
    assert 'PILOT_ROWS:2!=96' in report(root, rows=96)['problems']
    # a dielectric panel whose read-back sigma is not the tan_delta rule must fail
    raw = attempts(root/'batches/B000000')[0]/'raw'
    rp = sorted(raw.glob('*.json'))[0]
    rec = json.loads(rp.read_text())
    rec['meta'].update(bindings=[dict(object='dynamic_panel', kind='dielectric')],
                       panel_material_readback=[dict(relative_permittivity=12., thickness_m=.02,
                                                     conductivity_s_m=1.0, frequency_hz=6.25e9)]*257)
    rp.write_text(json.dumps(rec))           # receipt SHA no longer matches the batch manifest
    r = report(root)
    assert r['status'] != 'S2_PILOT_PASS' and 'RAW_NOT_COMPLETE_FOR_CURRENT_KEY:B000000' in r['problems']


def test_unknown_batch_is_reported(tmp_path):
    root, inputs, targets, batch = make_campaign(tmp_path)
    r = pilot_report(ROOT, root, 'IN', ['B999999'], 2)
    assert 'UNKNOWN_BATCH:B999999' in r['problems']
