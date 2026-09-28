"""Audit A: re-staging must never report success on stale server files (no network)."""
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/g2_completion'))
import run_sionna_full as ctl  # noqa: E402


def test_stage_commands_never_overwrite_and_check_this_revision_manifest(tmp_path):
    cmds = ctl.remote_commands('stage', tmp_path, '00_inputs_R3', 2, 4, [], 'abc123')
    rsync = next(c for c in cmds if c[0] == 'rsync')
    assert '--ignore-existing' in rsync
    check = ' '.join(cmds[-1])
    assert 'sha256sum --quiet --strict -c 03_stage/SHA256SUMS.abc123' in check
    pilot = ' '.join(ctl.remote_commands('pilot', tmp_path, '00_inputs_R3', 2, 4, ['B000001'], 'abc123')[0])
    assert 'CODE_REV=abc123' in pilot and '/code/abc123/scripts/g2_completion/sionna_full_lanes.sh' in pilot


def emulate_ignore_existing(src, dst):
    for p in src.rglob('*'):
        if p.is_file():
            q = dst/p.relative_to(src)
            if not q.exists():
                q.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(p, q)


@pytest.mark.skipif(shutil.which('sha256sum') is None, reason='coreutils sha256sum (Snowball host tool) required')
def test_stale_server_file_fails_this_revisions_check(tmp_path):
    def tree(rev, content):
        t = tmp_path/f'tree_{rev}'
        (t/f'code/{rev}').mkdir(parents=True); (t/'input').mkdir(); (t/'03_stage').mkdir()
        (t/f'code/{rev}/run.py').write_bytes(content); (t/'input/data.bin').write_bytes(b'data-' + rev.encode())
        sums = ''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(t).as_posix()}\n'
                       for p in sorted(t.rglob('*')) if p.is_file() and '03_stage' not in p.parts)
        (t/f'03_stage/SHA256SUMS.{rev}').write_text(sums)
        return t
    server = tmp_path/'server'; server.mkdir()
    emulate_ignore_existing(tree('rev1', b'v1'), server)
    ok = subprocess.run(['sha256sum', '--quiet', '--strict', '-c', '03_stage/SHA256SUMS.rev1'], cwd=server)
    assert ok.returncode == 0
    emulate_ignore_existing(tree('rev2', b'v2'), server)   # input/data.bin differs and is NOT overwritten
    stale = subprocess.run(['sha256sum', '--quiet', '--strict', '-c', '03_stage/SHA256SUMS.rev2'], cwd=server,
                           capture_output=True, text=True)
    assert stale.returncode != 0 and 'input/data.bin' in stale.stdout + stale.stderr
    assert (server/'code/rev1/run.py').read_bytes() == b'v1' and (server/'code/rev2/run.py').read_bytes() == b'v2'
