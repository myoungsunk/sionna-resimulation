"""F1 and status checks on the real lane controller with a fake docker (no RF, no network)."""
import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LANES = ROOT/'scripts/g2_completion/sionna_full_lanes.sh'
# The lane controller runs on the Linux host (Snowball). These tests execute it with POSIX bash and a fake
# docker on PATH (':'-separated); on Windows run them under WSL/Linux instead.
pytestmark = pytest.mark.skipif(os.name == 'nt', reason='requires POSIX bash and PATH semantics (Snowball host)')


@pytest.fixture
def campaign(tmp_path):
    camp = tmp_path/'camp'; (camp/'02_batches').mkdir(parents=True)
    (camp/'02_batches/BATCHES.jsonl').write_text(
        ''.join(json.dumps(dict(batch_id=f'B{i:06d}', count=1, target_ids=[str(i)])) + '\n' for i in range(3)))
    bindir = tmp_path/'bin'; bindir.mkdir()
    (bindir/'docker').write_text('#!/usr/bin/env bash\necho "$@" >> "$FAKE_DOCKER_LOG"\nexit 0\n')
    (bindir/'docker').chmod(0o755)
    env = dict(os.environ, PATH=f'{bindir}:{os.environ["PATH"]}', CAMPAIGN=str(camp), CODE_REV='rev0', INPUTS_DIR='IN',
               IMAGE='sha256:test', PY='/opt/rt-env/bin/python', LANES='2', THREADS='1', HOST_PY='python3',
               FAKE_DOCKER_LOG=str(tmp_path/'docker.log'))
    return camp, env, tmp_path/'docker.log'


def run(args, env, extra=None):
    return subprocess.run(['bash', str(LANES), *args], env=dict(env, **(extra or {})), capture_output=True, text=True)


def calls(log):
    return log.read_text().splitlines() if log.exists() else []


@pytest.mark.parametrize('ids,message', [(None, 'PILOT_IDS_REQUIRED'), ('', 'PILOT_IDS_REQUIRED'),
                                         ('B000001,B000001', 'DUPLICATE'), ('B000009', 'UNKNOWN'),
                                         ('B000000,', 'EMPTY_ELEMENT')])
def test_pilot_rejects_missing_or_invalid_list_before_any_container(campaign, ids, message):
    camp, env, log = campaign
    extra = {} if ids is None else dict(PILOT_IDS=ids)
    r = run(['--pilot'], env, extra)
    assert r.returncode != 0 and message in r.stderr and calls(log) == []


def test_pilot_runs_only_the_listed_batch(campaign):
    camp, env, log = campaign
    r = run(['--pilot'], env, dict(PILOT_IDS='B000001'))
    assert r.returncode == 0, r.stderr
    c = calls(log)
    assert len(c) == 2 and all('B000001' in x for x in c)
    assert 'sionna_full_runtime.py' in c[0] and 'finish_sionna_full.py' in c[1]
    assert all(f'{camp}/code/rev0:{camp}/code/rev0:ro' in x for x in c)   # revision-specific code mount
    assert not any('B000000' in x or 'B000002' in x for x in c)


def test_status_works_before_any_output(campaign):
    camp, env, log = campaign
    r = run(['--status'], env)
    assert r.returncode == 0, r.stderr
    s = json.loads(r.stdout)
    assert s['batches'] == 3 and s['complete_files'] == 0 and s['finished_files'] == 0 and not s['controller_alive']


def test_existing_finished_file_does_not_skip_container_checks(campaign):
    camp, env, log = campaign
    fin = camp/'batches/B000001/production'; fin.mkdir(parents=True)
    (fin/'FINISHED.json').write_text('{}')     # stale marker: completion is decided inside the container
    assert run(['--pilot'], env, dict(PILOT_IDS='B000001')).returncode == 0
    assert len(calls(log)) == 2


def test_controller_validates_pilot_before_building_commands(tmp_path):
    import sys
    sys.path.insert(0, str(ROOT/'scripts/g2_completion'))
    import run_sionna_full as ctl
    (tmp_path/'02_batches').mkdir()
    (tmp_path/'02_batches/BATCHES.jsonl').write_text(json.dumps(dict(batch_id='B000000')) + '\n')
    for bad in ([], [''], ['B000000', 'B000000'], ['B000001']):
        with pytest.raises(SystemExit):
            ctl.validate_pilot(tmp_path, bad)
    assert ctl.validate_pilot(tmp_path, ['B000000']) == ['B000000']
    out = subprocess.run([sys.executable, str(ROOT/'scripts/g2_completion/run_sionna_full.py'), '--campaign-root',
                          str(tmp_path), '--pilot', '--dry-run'], capture_output=True, text=True)
    assert out.returncode != 0 and 'PILOT_BATCHES_REQUIRED' in out.stderr and 'ssh' not in out.stdout


def test_preflight_fixture_and_report_modes_use_the_revision_code_and_validate(campaign):
    camp, env, log = campaign
    assert run(['--los-fixture'], env).returncode == 0
    c = calls(log)
    assert len(c) == 1 and '--los-fixture-only' in c[0] and f'{camp}/code/rev0' in c[0] and '--batch-id' not in c[0]
    r = run(['--pilot-report'], env, dict(PILOT_IDS='B000001'))
    assert r.returncode != 0 and len(calls(log)) == 1          # EXPECTED_ROWS required
    r = run(['--pilot-report'], env, dict(PILOT_IDS='', EXPECTED_ROWS='16'))
    assert r.returncode != 0 and 'PILOT_IDS_REQUIRED' in r.stderr and len(calls(log)) == 1
    r = run(['--pilot-report'], env, dict(PILOT_IDS='B000001,B000002', EXPECTED_ROWS='32'))
    assert r.returncode == 0, r.stderr
    last = calls(log)[-1]
    assert 'report_sionna_pilot.py' in last and '--batches B000001,B000002' in last and '--expected-rows 32' in last
    r = run(['--preflight'], env)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)['code_rev'] == 'rev0'
