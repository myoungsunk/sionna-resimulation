"""Controller for the full native campaign (plan section 7).

Local, tested here:
    --make-batches --batch-size 16      write 02_batches/BATCHES.jsonl (+ manifest); refuses silent changes
    --stage-manifest                    list every file to stage with SHA and remote path (03_stage/STAGE.json)

Remote (Snowball, KMS, Docker image pinned in RUNTIME_LOCK). NOT executed from
this environment; --dry-run prints the exact commands:
    --stage     rsync code snapshot, inputs, geometry, banks; re-hash remotely
    --pilot     run the listed pilot batches through runtime + finish
    --launch    start the nohup lane controller (sionna_full_lanes.sh); refuses if one is alive
    --status    read remote STATUS/COMPLETE/FINISHED counts
    --resume    same as --launch but only when no controller is alive (idempotent)
    --collect   rsync finished batches back, then verify SHAs locally
"""
import argparse
import datetime
import json
import shlex
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
              'scripts/g2_completion/sionna_full_lanes.sh', 'config/sionna_full_paths.example.json']


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
    remote = config_map['environments']['snowball']
    rroot = remote['root']
    items = []

    def add(local, remote_rel):
        items.append(dict(local=str(Path(local).relative_to(ROOT)), remote=f'{rroot}/{remote_rel}',
                          sha256=file_sha(local)))
    for c in CODE_FILES + ['rt_cp_uwb_py/' + p.name for p in sorted((ROOT/'rt_cp_uwb_py').glob('*.py'))
                           if p.name != '__init__.py'] + ['rt_cp_uwb_py/__init__.py']:
        if (ROOT/c).is_file() and not any(i['local'] == c for i in items):
            add(ROOT/c, f'code/{c}')
    inputs = root/inputs_dir
    for p in sorted(inputs.rglob('*')):
        if p.is_file():
            add(p, f'{inputs_dir}/{p.relative_to(inputs).as_posix()}')
    geo = json.loads((paths['geometry']/'SCENE_MESH_MANIFEST.json').read_text(encoding='utf8'))
    add(paths['geometry']/'SCENE_MESH_MANIFEST.json', f"{remote['paths']['geometry']}/SCENE_MESH_MANIFEST.json")
    for s in geo['scenes']:
        for m in s['materials']:
            add(paths['geometry']/m['mesh'], f"{remote['paths']['geometry']}/{m['mesh']}")
    for port in config_map['bank_ports']:
        add(paths['bank_dir']/f'{port}_bank.npz', f"{remote['paths']['bank_dir']}/{port}_bank.npz")
    add(paths['bank_manifest'], remote['paths']['bank_manifest'])
    for b in ('BATCHES.jsonl', 'BATCHES_MANIFEST.json'):
        add(root/'02_batches'/b, f'02_batches/{b}')
    out = root/'03_stage'; out.mkdir(exist_ok=True)
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    atomic_write_json(out/'STAGE.json', dict(remote_root=rroot, files=len(items), items=items, git_head=head,
                                             total_bytes=sum((ROOT/i['local']).stat().st_size for i in items)))
    sums = ''.join(f"{i['sha256']}  {i['remote'][len(rroot)+1:]}\n" for i in items)
    (out/'SHA256SUMS').write_text(sums, encoding='utf8')
    return items


def build_stage_tree(root):
    """Hard-link every staged file at its remote relative path under 03_stage/tree (no data copy)."""
    stage = json.loads((root/'03_stage'/'STAGE.json').read_text(encoding='utf8'))
    tree = root/'03_stage'/'tree'
    for i in stage['items']:
        dst = tree/i['remote'][len(stage['remote_root'])+1:]
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            if file_sha(dst) != i['sha256']:
                raise SystemExit(f'STAGE_TREE_STALE:{dst}')
            continue
        try:
            dst.hardlink_to(ROOT/i['local'])
        except OSError:
            dst.symlink_to(ROOT/i['local'])
    (tree/'03_stage').mkdir(exist_ok=True)
    (tree/'03_stage'/'SHA256SUMS').write_bytes((root/'03_stage'/'SHA256SUMS').read_bytes())
    return tree


def remote_commands(action, root, inputs_dir, lanes, threads, pilot):
    lock = json.loads(LOCK.read_text(encoding='utf8'))
    rroot = json.loads(PATH_MAP.read_text(encoding='utf8'))['environments']['snowball']['root']
    lanes_sh = f'{rroot}/code/scripts/g2_completion/sionna_full_lanes.sh'
    env = (f'CAMPAIGN={shlex.quote(rroot)} INPUTS_DIR={shlex.quote(inputs_dir)} IMAGE={lock["docker_image"]} '
           f'PY={lock["container_python"]} LANES={lanes} THREADS={threads}')
    if action == 'stage':
        tree = root/'03_stage'/'tree'
        return [SSH + [f'mkdir -p {rroot} && test ! -e {rroot}/controller/RUNNING'],
                ['rsync', '-aL', '--ignore-existing', str(tree) + '/', f'Snowball:{rroot}/'],
                SSH + [f'cd {rroot} && sha256sum --quiet -c 03_stage/SHA256SUMS && echo STAGE_SHA_OK']]
    if action == 'pilot':
        return [SSH + [f'{env} BATCH_IDS={",".join(pilot)} bash {lanes_sh} --foreground']]
    if action in ('launch', 'resume'):
        return [SSH + [f'{env} bash {lanes_sh} --launch']]
    if action == 'status':
        return [SSH + [f'{env} bash {lanes_sh} --status']]
    if action == 'collect':
        return [['rsync', '-a', '--include=*/', '--include=production/***', '--include=COMPLETE.json',
                 '--include=MANIFEST.json', '--include=STATUS.json', '--exclude=*',
                 f'Snowball:{rroot}/batches/', str(root/'05_results'/'batches') + '/']]
    raise ValueError(action)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--campaign-root', type=Path, required=True)
    ap.add_argument('--inputs-dir', default='00_inputs_R3')
    g = ap.add_mutually_exclusive_group(required=True)
    for flag in ('make-batches', 'stage-manifest', 'stage', 'pilot', 'launch', 'status', 'resume', 'collect'):
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
    if a.stage_manifest:
        items = stage_manifest(root, a.inputs_dir, paths, config_map)
        print(json.dumps(dict(files=len(items))))
        return
    action = next(f for f in ('stage', 'pilot', 'launch', 'status', 'resume', 'collect') if getattr(a, f))
    if action == 'stage' and not a.dry_run:
        dirty = subprocess.run(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT,
                               capture_output=True, text=True).stdout.strip()
        if dirty:
            raise SystemExit('STAGE_REQUIRES_CLEAN_COMMITTED_CHECKOUT')
        stage = json.loads((root/'03_stage'/'STAGE.json').read_text(encoding='utf8'))
        head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        if stage.get('git_head') != head:
            raise SystemExit('STAGE_MANIFEST_NOT_FROM_HEAD: rerun --stage-manifest')
        build_stage_tree(root)
    cmds = remote_commands(action, root, a.inputs_dir, a.lanes, a.threads,
                           [p for p in a.pilot_batches.split(',') if p])
    if a.dry_run:
        for c in cmds:
            print(' '.join(shlex.quote(x) for x in c))
        return
    for c in cmds:
        subprocess.run(c, check=True)


if __name__ == '__main__':
    main()
