"""Retrieve only the three unsealed G-T1 parent cases from the guarded +45 RT run."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess


OUT = Path(__file__).resolve().parent
REPO = OUT.parents[1] / 'g1_rt_tb3_guarded_mount45_publication_20261116'
NAME = 'G1_RT_TB3_FINITE_FACE_MOUNT45_20261115T133901Z_gMgSBo'
EVIDENCE = f'research/G1_RT_TB3_CORRIDOR_20261113/evidence/Production/{NAME}/results'
REMOTE = f'Snowball:/home/KMS/{NAME}/results'
LOCAL = OUT / 'guarded_gt1'
OPTIONS = ['-o', 'BatchMode=yes', '-o', 'PasswordAuthentication=no', '-o', 'ConnectTimeout=15']


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def git_bytes(commit, path):
    return subprocess.check_output(['git', '-C', str(REPO), 'show', f'{commit}:{EVIDENCE}/{path}'])


def transfer(commit, case):
    h = f'H/{case}'
    p = f'poses/{case}'
    manifest = git_bytes(commit, f'{h}/MANIFEST.json')
    gate = json.loads(git_bytes(commit, 'gates/G4.json'))
    assert gate['status'] == 'PASS' and gate['cases'][case]['status'] == 'PASS'
    receipt = json.loads(manifest)
    assert receipt['mount_deg'] == 45 and receipt['case'] == case
    entries = {f'{h}/MANIFEST.json': hashlib.sha256(manifest).hexdigest(),
               f'{h}/H_full.npy': receipt['full_H_sha256'], f'{h}/H_LoS.npy': receipt['los_H_sha256'],
               f'{p}/SAMPLES.json': receipt['samples_sha256'], f'{p}/rf_poses.json': None,
               f'{p}/SCENE_ENTRY.json': None}
    for directory in (h, p):
        (LOCAL / directory).mkdir(exist_ok=True, parents=True)
        missing = [name for name in entries if Path(name).parent.as_posix() == directory and not (LOCAL / name).exists()]
        if missing:
            subprocess.run(['scp.exe', '-q', *OPTIONS, *[f'{REMOTE}/{name}' for name in missing],
                            str(LOCAL / directory)], check=True)
    for name, expected in entries.items():
        digest = sha(LOCAL / name)
        assert expected is None or digest == expected, (name, digest, expected)
        entries[name] = digest
    print(case, 'hashes verified', flush=True)
    return entries


def main():
    config = subprocess.check_output(['ssh.exe', '-G', 'Snowball'], text=True)
    assert 'user KMS' in config.splitlines(), 'Snowball must use the KMS account'
    commit = subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()
    with ThreadPoolExecutor(max_workers=3) as pool:
        entries = dict(zip(('G-T1_A', 'G-T1_B', 'G-T1_C'), pool.map(
            lambda case: transfer(commit, case), ('G-T1_A', 'G-T1_B', 'G-T1_C'))))
    with (LOCAL / 'RETRIEVAL.json').open('x', encoding='utf-8') as handle:
        json.dump({'remote': REMOTE, 'published_commit': commit, 'files': entries}, handle, indent=2)
        handle.write('\n')


if __name__ == '__main__':
    main()
