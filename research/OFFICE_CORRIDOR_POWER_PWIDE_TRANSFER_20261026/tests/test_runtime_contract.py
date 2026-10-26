"""Offline regressions for the three Stage-1 blockers; no real RF execution."""
import importlib.util
import json
import subprocess
import sys
import tarfile
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from office_transfer_core import restore_release_snapshot, sha256
from runtime_contract import (verify_checkout, verify_loaded_modules,
                              configure_replay, verify_replay_bindings)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path/'repo';root.mkdir()
    def run(*args):
        return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
    run('init','-q')
    (root/'source_model.py').write_text('VALUE = 1\n')
    run('add','source_model.py')
    run('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','fixture')
    return root,run('rev-parse','HEAD'),run


def test_checkout_clean_and_untracked_rf_allowed(repo):
    root,head,_=repo
    (root/'rf.npy').write_bytes(b'synthetic')
    assert verify_checkout(root,head,'TEST')==head


@pytest.mark.parametrize('change',['modified','staged','staged_reverted','deleted','shadow'])
def test_checkout_rejects_source_changes(repo,change):
    root,head,run=repo
    if change=='deleted':(root/'source_model.py').unlink()
    elif change=='shadow':(root/'v_replay.py').write_text('VALUE=9')
    else:
        (root/'source_model.py').write_text('VALUE=2')
        if change in ('staged','staged_reverted'):run('add','source_model.py')
        if change=='staged_reverted':(root/'source_model.py').write_text('VALUE = 1\n')
    with pytest.raises(ValueError,match='DIRTY_TRACKED|UNTRACKED_SOURCE'):
        verify_checkout(root,head,'TEST')


def test_checkout_wrong_revision_or_nested_directory(repo):
    root,head,_=repo
    with pytest.raises(ValueError,match='COMMIT_MISMATCH'):verify_checkout(root,'0'*40,'TEST')
    nested=root/'sub';nested.mkdir()
    with pytest.raises(ValueError,match='ROOT_MISMATCH'):verify_checkout(nested,head,'TEST')


def test_modules_must_be_frozen_tracked_source(repo,tmp_path,monkeypatch):
    root,_,_=repo
    mod=SimpleNamespace(__file__=str(root/'source_model.py'))
    monkeypatch.setitem(sys.modules,'source_model',mod)
    assert 'source_model' in verify_loaded_modules(root)
    (root/'source_model.py').write_text('VALUE=9')
    with pytest.raises(ValueError,match='MODIFIED_RUNTIME'):verify_loaded_modules(root)
    mod.__file__=str(tmp_path/'source_model.py')
    with pytest.raises(ValueError,match='FOREIGN_RUNTIME'):verify_loaded_modules(root)
    mod.__file__=str(root/'shadow.py');Path(mod.__file__).write_text('VALUE=1')
    with pytest.raises(ValueError,match='UNTRACKED_RUNTIME'):verify_loaded_modules(root)


def test_replay_paths_explicit_and_imported_values_checked(tmp_path,monkeypatch):
    for key in ('PJ_SOURCE_ROOT','PJ_ART','PJ_OUT'):monkeypatch.delenv(key,raising=False)
    root=tmp_path/'repo';root.mkdir();art=tmp_path/'art';art.mkdir();out=tmp_path/'out'
    paths=configure_replay(root,art,out)
    V=SimpleNamespace(ROOT=root,ART=art,OUT=out)
    verify_replay_bindings(V,paths)
    V.ROOT=tmp_path/'other'
    with pytest.raises(ValueError,match='IMPORTED_REPLAY'):verify_replay_bindings(V,paths)
    with pytest.raises(ValueError,match='ENV_CONFLICT'):configure_replay(root,art,tmp_path/'else')
    with pytest.raises(ValueError,match='OVERLAPS_INPUT'):configure_replay(root,art,root/'out')
    with pytest.raises(ValueError,match='ARTIFACT_DIRECTORY_MISSING'):configure_replay(root,tmp_path/'missing',out)


@pytest.fixture
def archive(tmp_path):
    path=tmp_path/'release.tar.gz'
    with tarfile.open(path,'w:gz') as tar:
        for name,body in [('O01/CASES/test/H_FULL.npy',b'full'),('O01/RADIO_POSE.csv',b'pose')]:
            entry=tarfile.TarInfo(name);entry.size=len(body);tar.addfile(entry,BytesIO(body))
    return path,sha256(path)


def test_extraction_consumed_by_original_t2_receipt_index(archive,tmp_path):
    path,digest=archive;out=tmp_path/'extract'
    restore_release_snapshot(path,out,digest)
    fixture=Path(__file__).parent/'fixtures/t2_receipt_index.py'
    spec=importlib.util.spec_from_file_location('original_t2_receipt',fixture)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    records,receipts=mod.receipt_index(out)
    assert len(records)==2 and len(receipts)==1
    assert all(p.is_file() and sha256(p)==h for p,h in records.items())
    assert restore_release_snapshot(path,out,digest)==out


@pytest.mark.parametrize('change',['same_size','size','extra','incomplete'])
def test_extraction_cache_fail_closed(archive,tmp_path,change):
    path,digest=archive;out=tmp_path/'extract'
    restore_release_snapshot(path,out,digest)
    file=out/'data/O01/CASES/test/H_FULL.npy'
    if change=='same_size':file.write_bytes(b'evil')
    elif change=='size':file.write_bytes(b'longer')
    elif change=='extra':(out/'data/extra').write_bytes(b'x')
    else:(out/'ARCHIVE_CONTENTS_AND_SHA.json').unlink()
    before=file.read_bytes()
    with pytest.raises(ValueError):restore_release_snapshot(path,out,digest)
    assert file.read_bytes()==before
