"""Fail-closed binding of frozen code and explicit replay directories."""
import os
import subprocess
import sys
from pathlib import Path


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args],
                                   text=True, stderr=subprocess.PIPE).strip()


def verify_checkout(checkout, expected, label):
    root = Path(checkout).resolve()
    try:
        top = Path(git(root, 'rev-parse', '--show-toplevel')).resolve()
        current = git(root, 'rev-parse', 'HEAD')
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError(f'{label}_GIT_CHECKOUT_UNVERIFIED: {root}') from exc
    if top != root:
        raise ValueError(f'{label}_CHECKOUT_ROOT_MISMATCH')
    if current != expected:
        raise ValueError(f'{label}_COMMIT_MISMATCH: expected={expected} got={current}')
    # Both index and working tree, including deleted tracked files.
    if (git(root, 'diff', '--name-only') or
            git(root, 'diff', '--cached', '--name-only')):
        raise ValueError(f'{label}_DIRTY_TRACKED_CHECKOUT')
    # Untracked RF outputs are allowed; executable import shadows are not.
    untracked = git(root, 'ls-files', '--others', '--exclude-standard').splitlines()
    if any(Path(p).suffix.lower() in {'.py', '.pyw', '.pyd', '.so'} for p in untracked):
        raise ValueError(f'{label}_UNTRACKED_SOURCE')
    return current


MODULES = {'p2_replay', 'p1r_eval', 'strict_common', 'v_replay', 'p0_initial',
           'source_model', 'r2_bias_replay', 'features', 'n4b_rf_errors',
           'm_core', 'hpath_lut', 'p3_rf_adapter4'}


def verify_loaded_modules(root):
    root = Path(root).resolve()
    records = {}
    for name, module in list(sys.modules.items()):
        if name not in MODULES and not name.startswith('qclean_uwb'):
            continue
        location = getattr(module, '__file__', None)
        if not location or not Path(location).resolve().is_relative_to(root):
            raise ValueError('FOREIGN_RUNTIME_MODULE:'+name)
        path = Path(location).resolve()
        relative = path.relative_to(root).as_posix()
        try:
            expected = git(root, 'rev-parse', 'HEAD:'+relative)
            actual = git(root, 'hash-object', '--path='+relative, str(path))
        except subprocess.CalledProcessError as exc:
            raise ValueError('UNTRACKED_RUNTIME_MODULE:'+name) from exc
        if actual != expected:
            raise ValueError('MODIFIED_RUNTIME_MODULE:'+name)
        records[name] = {'path': str(path), 'git_blob': actual}
    return records


def reject_foreign_modules(root):
    verify_loaded_modules(root)


def configure_replay(root, artifacts, output):
    paths = {k: Path(v).resolve() for k, v in
             [('PJ_SOURCE_ROOT', root), ('PJ_ART', artifacts), ('PJ_OUT', output)]}
    if not paths['PJ_ART'].is_dir():
        raise ValueError('TARGET_ARTIFACT_DIRECTORY_MISSING')
    out = paths['PJ_OUT']
    if any(out == paths[k] or out.is_relative_to(paths[k]) or paths[k].is_relative_to(out)
           for k in ('PJ_SOURCE_ROOT', 'PJ_ART')):
        raise ValueError('REPLAY_OUTPUT_OVERLAPS_INPUT')
    for key, path in paths.items():
        if key in os.environ and Path(os.environ[key]).resolve() != path:
            raise ValueError('REPLAY_ENV_CONFLICT:'+key)
    reject_foreign_modules(paths['PJ_SOURCE_ROOT'])
    for key, path in paths.items():
        os.environ[key] = str(path)
    return {k: str(v) for k, v in paths.items()}


def verify_replay_bindings(V, paths):
    for attr, key in [('ROOT', 'PJ_SOURCE_ROOT'), ('ART', 'PJ_ART'), ('OUT', 'PJ_OUT')]:
        if Path(getattr(V, attr)).resolve() != Path(paths[key]):
            raise ValueError('IMPORTED_REPLAY_PATH_MISMATCH:'+attr)
