"""Controller for the full native campaign (plan section 7).

Local, tested here:
    --make-batches --batch-size 16   write 02_batches/BATCHES.jsonl (+ manifest); refuses silent changes
    --stage-manifest                 03_stage/STAGE.json + SHA256SUMS (untracked, regenerable) for the clean HEAD
    --stage-local                    manifest + 03_stage/tree with per-file SHA re-check (no network)

Staging byte policy: tracked, non-LFS files (code, config, geometry, small
inputs, batches) are staged from their Git blob at HEAD, so the payload is
identical on Windows and Linux checkouts (the two -text runner files keep
their Windows bytes; *.sh is LF). LFS or untracked data (FFD banks, TARGETS,
panel PLYs) are staged from the file bytes. Every item carries its SHA; the
remote side re-checks with sha256sum -c.

Remote (Snowball, KMS, Docker image pinned in RUNTIME_LOCK). NOT executed from
this environment; --dry-run prints the exact commands:
    --stage     regenerate the manifest from a clean HEAD, build 03_stage/tree, rsync, remote sha256sum -c
    --pilot     --pilot-batches ID[,ID...] required: non-empty, known, unique, <= 64; never all batches
    --launch    all batches via the nohup lane controller; refuses if one is alive
    --status    remote file counts (completion is decided by verify)
    --resume    same as --launch (idempotent: an alive controller is left alone)
    --collect   server verify (raw-policy full) -> rsync production + receipts/manifests (raw NPZ stay on the
                server) -> local verify --raw-policy receipts-only against the server verify
"""
import argparse
import datetime
import hashlib
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from rt_cp_uwb_py.g2_full_paths import file_sha, load_paths  # noqa: E402
from rt_cp_uwb_py.g2_full_runner import atomic_write_json, plan_batches  # noqa: E402

PATH_MAP = ROOT/'config/sionna_full_paths.example.json'
LOCK = ROOT/'runtime/sionna-full/RUNTIME_LOCK.json'
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'PasswordAuthentication=no', 'Snowball']
CODE_FILES = ['scripts/g2_completion/sionna_full_runtime.py', 'scripts/g2_completion/sionna_native_runtime.py',
              'scripts/g2_completion/finish_sionna_full.py', 'scripts/g2_completion/verify_sionna_full.py',
              'scripts/g2_completion/sionna_full_lanes.sh', 'config/sionna_full_paths.example.json',
              'runtime/sionna-full/RUNTIME_LOCK.json']
PILOT_MAX = 64


def git(*args, binary=False):
    out = subprocess.run(['git', *args], cwd=ROOT, capture_output=True, check=True)
    return out.stdout if binary else out.stdout.decode()


def validate_pilot(root, ids):
    """Explicit representative list: non-empty, no empty element, unique, known, <= PILOT_MAX."""
    if not ids or any(not i for i in ids):
        raise SystemExit('PILOT_BATCHES_REQUIRED: explicit non-empty representative list (no fallback to all)')
    if len(ids) != len(set(ids)):
        raise SystemExit('PILOT_BATCHES_DUPLICATE')
    known = {json.loads(l)['batch_id'] for l in (root/'02_batches'/'BATCHES.jsonl').read_text(encoding='utf8')
             .splitlines()}
    unknown = [i for i in ids if i not in known]
    if unknown:
        raise SystemExit('PILOT_BATCHES_UNKNOWN:' + ','.join(unknown))
    if len(ids) > PILOT_MAX:
        raise SystemExit('PILOT_BATCHES_TOO_MANY')
    return ids


def make_batches(root, inputs_dir, size):
    inputs = root/inputs_dir
    config = json.loads((inputs/'CONFIG.json').read_text(encoding='utf8'))
    if file_sha(inputs/'TARGETS.jsonl') != config['targets_sha256']:
        raise SystemExit('TARGETS_SHA_NOT_CONFIG')
    targets = [json.loads(l) for l in (inputs/'TARGETS.jsonl').read_text(encoding='utf8').splitlines()]
    batches = plan_batches(targets, size)
    out = root/'02_batches'; out.mkdir(exist_ok=True)
    text = ''.join(json.dumps(b, sort_keys=True) + '\n' for b in batches)
    target = out/'BATCHES.jsonl'
    if target.exists() and target.read_text(encoding='utf8') != text:
        raise SystemExit('BATCHES_CHANGED: fixed batches differ; create a new batch revision instead')
    target.write_text(text, encoding='utf8')
    atomic_write_json(out/'BATCHES_MANIFEST.json', dict(
        inputs_dir=inputs_dir, targets_sha256=config['targets_sha256'], batch_size=size, batches=len(batches),
        targets=sum(b['count'] for b in batches), last_batch_count=batches[-1]['count'],
        batches_sha256=file_sha(target), timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    return batches


def stage_manifest(root, inputs_dir, paths, config_map):
    """Manifest for the clean HEAD; see the byte policy in the module docstring."""
    if git('status', '--porcelain', '--untracked-files=no').strip():
        raise SystemExit('STAGE_REQUIRES_CLEAN_COMMITTED_CHECKOUT (tracked files)')
    head = git('rev-parse', 'HEAD').strip()
    tracked = set(git('ls-tree', '-r', '--name-only', 'HEAD').splitlines())
    remote = config_map['environments']['snowball']
    rroot = remote['root']
    items = []

    def add(local, remote_rel, expected=None):
        rel = Path(local).resolve().relative_to(ROOT).as_posix()
        lfs = rel in tracked and git('check-attr', 'filter', rel).strip().endswith('lfs')
        if rel in tracked and not lfs:
            data = git('cat-file', 'blob', f'HEAD:{rel}', binary=True)
            source = 'git_blob'
        else:
            data = Path(local).read_bytes()
            source = 'file'
        digest = hashlib.sha256(data).hexdigest()
        if expected and digest != expected:
            raise SystemExit(f'STAGE_SHA_NOT_DECLARED:{rel}')
        items.append(dict(local=rel, source=source, remote=f'{rroot}/{remote_rel}', sha256=digest, bytes=len(data)))
    code = sorted({c for c in CODE_FILES} | {t for t in tracked if t.startswith('rt_cp_uwb_py/') and t.endswith('.py')})
    for c in code:
        add(ROOT/c, f'code/{head}/{c}')   # A: revision-specific code dir; never overwrites another revision
    inputs = root/inputs_dir
    config = json.loads((inputs/'CONFIG.json').read_text(encoding='utf8'))
    declared = {'TARGETS.jsonl': config['targets_sha256'], 'POSES.json': config.get('poses_sha256'),
                'PANELS.json': config.get('panels_sha256'),
                'STATIC9_OVERLAY_CONTRACT.json': config.get('static9_overlay_sha256')}
    for p in sorted(inputs.rglob('*')):
        if p.is_file():   # F5: TARGETS/POSES/PANELS must be the canonical set named by CONFIG
            add(p, f'{inputs_dir}/{p.relative_to(inputs).as_posix()}', declared.get(p.name))
    geo = json.loads((paths['geometry']/'SCENE_MESH_MANIFEST.json').read_text(encoding='utf8'))
    add(paths['geometry']/'SCENE_MESH_MANIFEST.json', f"{remote['paths']['geometry']}/SCENE_MESH_MANIFEST.json",
        config['geometry_manifest_sha256'])
    for s_ in geo['scenes']:
        for m in s_['materials']:
            add(paths['geometry']/m['mesh'], f"{remote['paths']['geometry']}/{m['mesh']}", m['sha256'])
    for port in config_map['bank_ports']:
        add(paths['bank_dir']/f'{port}_bank.npz', f"{remote['paths']['bank_dir']}/{port}_bank.npz",
            config['bank_sha256'][f'{port}_bank.npz'])
    add(paths['bank_manifest'], remote['paths']['bank_manifest'])
    for b in ('BATCHES.jsonl', 'BATCHES_MANIFEST.json'):
        add(root/'02_batches'/b, f'02_batches/{b}')
    out = root/'03_stage'; out.mkdir(exist_ok=True)
    code_items = [i for i in items if i['remote'].startswith(f'{rroot}/code/{head}/')]
    atomic_write_json(out/'STAGE.json', dict(
        remote_root=rroot, code_revision=head, files=len(items), items=items,
        code_tree_sha256=hashlib.sha256(''.join(f"{i['local']}:{i['sha256']}\n" for i in code_items).encode())
        .hexdigest(), byte_policy='tracked non-LFS: git blob at code_revision; LFS/untracked: file bytes',
        total_bytes=sum(i['bytes'] for i in items),
        timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    sums = ''.join(f"{i['sha256']}  {i['remote'][len(rroot)+1:]}\n" for i in items)
    (out/'SHA256SUMS').write_text(sums, encoding='utf8', newline='\n')
    # Revision-named copies: the remote check and a later collect always use *this* revision's manifest.
    (out/f'SHA256SUMS.{head}').write_text(sums, encoding='utf8', newline='\n')
    (out/f'STAGE.{head}.json').write_bytes((out/'STAGE.json').read_bytes())
    return items


def build_stage_tree(root):
    """Materialise 03_stage/tree at the remote layout: blobs written, data hard-linked; SHA re-checked."""
    stage = json.loads((root/'03_stage'/'STAGE.json').read_text(encoding='utf8'))
    if stage['code_revision'] != git('rev-parse', 'HEAD').strip():
        raise SystemExit('STAGE_MANIFEST_NOT_FROM_HEAD')
    tree = root/'03_stage'/'tree'
    if tree.exists():
        shutil.rmtree(tree)  # derived, untracked view; rebuilt from the manifest every time
    for i in stage['items']:
        dst = tree/i['remote'][len(stage['remote_root'])+1:]
        dst.parent.mkdir(parents=True, exist_ok=True)
        if i['source'] == 'git_blob':
            dst.write_bytes(git('cat-file', 'blob', f"{stage['code_revision']}:{i['local']}", binary=True))
        else:
            try:
                dst.hardlink_to(ROOT/i['local'])
            except OSError:
                shutil.copy2(ROOT/i['local'], dst)
        if file_sha(dst) != i['sha256']:
            raise SystemExit(f"STAGE_TREE_SHA:{i['local']}")
    (tree/'03_stage').mkdir(exist_ok=True)
    rev = stage['code_revision']
    for name in (f'SHA256SUMS.{rev}', f'STAGE.{rev}.json'):
        (tree/'03_stage'/name).write_bytes((root/'03_stage'/name).read_bytes())
    return tree


def deployed_stage(root):
    """The manifest of the revision that was staged (pilot/launch/collect use this, not the local HEAD)."""
    stage = json.loads((root/'03_stage'/'STAGE.json').read_text(encoding='utf8'))
    rev = stage['code_revision']
    named = root/'03_stage'/f'STAGE.{rev}.json'
    if not named.is_file() or file_sha(named) != file_sha(root/'03_stage'/'STAGE.json'):
        raise SystemExit('DEPLOYED_STAGE_MANIFEST_MISSING')
    return stage


def remote_commands(action, root, inputs_dir, lanes, threads, pilot, rev):
    """Remote command lists for the deployed code revision `rev`."""
    lock = json.loads(LOCK.read_text(encoding='utf8'))
    rroot = json.loads(PATH_MAP.read_text(encoding='utf8'))['environments']['snowball']['root']
    lanes_sh = f'{rroot}/code/{rev}/scripts/g2_completion/sionna_full_lanes.sh'
    env = (f'CAMPAIGN={shlex.quote(rroot)} CODE_REV={rev} INPUTS_DIR={shlex.quote(inputs_dir)} '
           f'IMAGE={lock["docker_image"]} PY={lock["container_python"]} LANES={lanes} THREADS={threads}')
    if action == 'stage':
        tree = root/'03_stage'/'tree'
        return [SSH + [f'mkdir -p {rroot} && test ! -e {rroot}/controller/RUNNING'],
                # --ignore-existing: never overwrite anything already on the server (older revisions, results) ...
                ['rsync', '-aL', '--ignore-existing', str(tree) + '/', f'Snowball:{rroot}/'],
                # ... and prove every file equals *this* revision's manifest; a stale file with another SHA fails.
                SSH + [f'cd {rroot} && sha256sum --quiet --strict -c 03_stage/SHA256SUMS.{rev} '
                       f'&& echo STAGE_SHA_OK_{rev}']]
    if action == 'pilot':
        return [SSH + [f'{env} PILOT_IDS={shlex.quote(",".join(pilot))} bash {lanes_sh} --pilot']]
    if action in ('launch', 'resume'):
        return [SSH + [f'{env} bash {lanes_sh} --launch']]
    if action == 'status':
        return [SSH + [f'{env} bash {lanes_sh} --status']]
    if action == 'collect':
        local = root/'05_results'
        return [SSH + [f'{env} bash {lanes_sh} --server-verify'],
                ['rsync', '-a', '--include=*/', '--include=production/***', '--include=*.json',
                 '--exclude=*.npz', '--exclude=*', f'Snowball:{rroot}/batches/', str(local/'batches') + '/'],
                ['rsync', '-a', f'Snowball:{rroot}/06_validation/SERVER_VERIFY.json', str(local) + '/'],
                [sys.executable, str(ROOT/'scripts/g2_completion/verify_sionna_full.py'), '--campaign-root',
                 str(root), '--inputs-dir', inputs_dir, '--runs-dir', '05_results/batches',
                 '--raw-policy', 'receipts-only', '--server-verify', str(local/'SERVER_VERIFY.json'),
                 '--stage-manifest', str(root/'03_stage'/f'STAGE.{rev}.json'),
                 '--out', '06_validation/COLLECTED_VERIFY.json']]
    raise ValueError(action)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--campaign-root', type=Path, required=True)
    ap.add_argument('--inputs-dir', default='00_inputs_R3')
    g = ap.add_mutually_exclusive_group(required=True)
    for flag in ('make-batches', 'stage-manifest', 'stage-local', 'stage', 'pilot', 'launch', 'status', 'resume',
                 'collect'):
        g.add_argument('--' + flag, action='store_true')
    ap.add_argument('--batch-size', type=int, default=16)
    ap.add_argument('--lanes', type=int, default=2)
    ap.add_argument('--threads', type=int, default=4)
    ap.add_argument('--pilot-batches', default='')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    config_map, paths = load_paths(PATH_MAP, 'repo_checkout', ROOT)
    root = a.campaign_root if a.campaign_root.is_absolute() else ROOT/a.campaign_root
    if a.make_batches:
        b = make_batches(root, a.inputs_dir, a.batch_size)
        print(json.dumps(dict(batches=len(b), targets=sum(x['count'] for x in b), last=b[-1]['count'])))
        return
    if a.stage_manifest or a.stage_local:
        items = stage_manifest(root, a.inputs_dir, paths, config_map)
        tree = build_stage_tree(root) if a.stage_local else None
        print(json.dumps(dict(files=len(items), code_revision=git('rev-parse', 'HEAD').strip(),
                              tree=str(tree.relative_to(ROOT)) if tree else None)))
        return
    action = next(f for f in ('stage', 'pilot', 'launch', 'status', 'resume', 'collect') if getattr(a, f))
    pilot = [p for p in a.pilot_batches.split(',')] if a.pilot_batches else []
    if action == 'pilot':
        validate_pilot(root, pilot)
    if action == 'stage' and not a.dry_run:
        stage_manifest(root, a.inputs_dir, paths, config_map)   # always from the current clean HEAD
        build_stage_tree(root)
    if action == 'stage':
        rev = git('rev-parse', 'HEAD').strip() if a.dry_run else json.loads(
            (root/'03_stage'/'STAGE.json').read_text(encoding='utf8'))['code_revision']
    else:
        rev = deployed_stage(root)['code_revision']   # the revision that was staged, not the local HEAD
    cmds = remote_commands(action, root, a.inputs_dir, a.lanes, a.threads, pilot, rev)
    if a.dry_run:
        for c in cmds:
            print(' '.join(shlex.quote(x) for x in c))
        return
    for c in cmds:
        subprocess.run(c, check=True)


if __name__ == '__main__':
    main()
