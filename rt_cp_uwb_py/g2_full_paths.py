"""Environment path map for the full native Sionna campaign.

Reads config/sionna_full_paths.example.json. Files are resolved in place;
nothing is moved or copied. Bank NPZ files are accepted only when their
SHA256 matches BANK_MANIFEST.json npz_sha256.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath

REQUIRED_KEYS = ('relocated_inputs', 'geometry', 'bank_dir', 'bank_manifest',
                 'operating_config', 'static9_contract', 'campaign')


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def _is_absolute(text):
    return PurePosixPath(text).is_absolute() or (len(text) > 2 and text[1] == ':' and text[2] in '/\\')


def resolve_paths(config, environment, repo_root):
    """Return {key: Path} for one environment; relative entries join the env root."""
    env = config['environments'][environment]
    missing = [k for k in REQUIRED_KEYS if k not in env['paths']]
    if missing:
        raise ValueError('PATH_MAP_MISSING_KEYS:' + ','.join(missing))
    root = Path(env['root'])
    if not _is_absolute(env['root']):
        root = Path(repo_root)/root
    return {k: Path(v) if _is_absolute(v) else root/v for k, v in env['paths'].items()}


def load_paths(path_map, environment, repo_root):
    config = json.loads(Path(path_map).read_text(encoding='utf8'))
    return config, resolve_paths(config, environment, repo_root)


def resolve_banks(config, paths, verify=True):
    """Map each port to its NPZ file, checked against BANK_MANIFEST.

    Returns {port: dict(path, sha256)}. Raises on a missing file, an LFS
    pointer instead of content, port-order drift, or SHA mismatch.
    """
    manifest = json.loads(paths['bank_manifest'].read_text(encoding='utf8'))
    if manifest['ports'] != config['bank_ports']:
        raise ValueError('BANK_PORT_ORDER_MISMATCH')
    banks = {}
    for port in config['bank_ports']:
        name = f'{port}_bank.npz'
        path = paths['bank_dir']/name
        if not path.is_file():
            raise FileNotFoundError('BANK_FILE_MISSING:' + str(path))
        with path.open('rb') as stream:
            if stream.read(40).startswith(b'version https://git-lfs'):
                raise ValueError('BANK_FILE_IS_LFS_POINTER:' + str(path))
        expected = manifest['npz_sha256'][name]
        if verify and file_sha(path) != expected:
            raise ValueError('BANK_SHA_MISMATCH:' + name)
        banks[port] = dict(path=path, sha256=expected)
    return banks
