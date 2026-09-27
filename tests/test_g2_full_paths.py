import hashlib
import json
from pathlib import Path

import pytest

from rt_cp_uwb_py.g2_full_paths import REQUIRED_KEYS, load_paths, resolve_banks, resolve_paths

ROOT = Path(__file__).resolve().parents[1]
PORTS = ['RHCP', 'LHCP', 'LP_X', 'LP_Y', 'LP_plus45', 'LP_minus45']


def fake_env(tmp_path, content=b'bank'):
    (tmp_path/'bank').mkdir()
    shas = {}
    for p in PORTS:
        (tmp_path/f'{p}_bank.npz').write_bytes(content+p.encode())
        shas[f'{p}_bank.npz'] = hashlib.sha256(content+p.encode()).hexdigest()
    (tmp_path/'bank/BANK_MANIFEST.json').write_text(json.dumps(dict(ports=PORTS, npz_sha256=shas)))
    paths = {k: 'x' for k in REQUIRED_KEYS}
    paths.update(bank_dir='.', bank_manifest='bank/BANK_MANIFEST.json')
    return dict(bank_ports=PORTS, environments=dict(t=dict(root='.', paths=paths)))


def test_repo_path_map_covers_all_environments():
    config, paths = load_paths(ROOT/'config/sionna_full_paths.example.json', 'repo_checkout', ROOT)
    assert set(config['environments']) == {'repo_checkout', 'windows_workspace', 'snowball'}
    assert paths['bank_dir'] == ROOT and paths['bank_manifest'].is_file()
    win = resolve_paths(config, 'windows_workspace', ROOT)
    assert str(win['bank_dir']).startswith('D:')


def test_root_banks_resolve_in_place_with_matching_sha(tmp_path):
    config = fake_env(tmp_path)
    banks = resolve_banks(config, resolve_paths(config, 't', tmp_path))
    assert [b['path'].parent for b in banks.values()] == [tmp_path]*6


def test_bank_sha_drift_is_rejected(tmp_path):
    config = fake_env(tmp_path)
    (tmp_path/'LHCP_bank.npz').write_bytes(b'changed')
    with pytest.raises(ValueError, match='BANK_SHA_MISMATCH:LHCP'):
        resolve_banks(config, resolve_paths(config, 't', tmp_path))


def test_lfs_pointer_is_rejected(tmp_path):
    config = fake_env(tmp_path)
    (tmp_path/'RHCP_bank.npz').write_bytes(b'version https://git-lfs.github.com/spec/v1\noid sha256:0\n')
    with pytest.raises(ValueError, match='LFS_POINTER'):
        resolve_banks(config, resolve_paths(config, 't', tmp_path))
