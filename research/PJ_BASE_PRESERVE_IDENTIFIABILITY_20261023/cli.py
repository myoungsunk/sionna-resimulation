"""Command interface. Default actions inspect code only; every RF stage requires explicit consent."""
from __future__ import annotations
import argparse
from pathlib import Path
import json
import sys
from .common import Workspace,read_json,write_json,file_hash,REFERENCE_SHA,BlockedError,ContractError


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['audit-code','plan','inventory','stage'])
    p.add_argument('--config',required=True,type=Path)
    p.add_argument('--stage',choices=[f'S{i}' for i in range(8)])
    p.add_argument('--execute-rf',action='store_true',help='Required for any original RF replay or fitting; never implied by audit-code')
    p.add_argument('--lock-out',type=Path)
    return p


def main(argv=None):
    a=parser().parse_args(argv);cfg=read_json(a.config);ws=Workspace(Path(cfg['work_dir']),cfg)
    if a.command=='audit-code':
        from .audit import audit
        return audit(ws)
    if a.command=='plan':
        print(json.dumps(dict(reference_sha=REFERENCE_SHA,stage_order=['S0','S1','S2','S3','S4','S5','S6','S7'],
            experiments_launched=False,training_launched=False,requires='--execute-rf plus current AUDIT PASS for each stage'),indent=2));return 0
    if a.command=='inventory':
        if not a.lock_out:raise ContractError('--lock-out is required for inventory')
        paths=[]
        for key in ('source_root','artifact_root','l4models_root','grid_root'):
            root=Path(cfg.get(key,''))
            if not cfg.get(key) or not root.is_dir():raise BlockedError(f'Missing {key}')
            paths += [p.resolve() for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
        ref=Path(cfg['reference_root'])
        paths += [ref/'research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz']
        for p in paths:
            if not p.is_file():raise BlockedError(f'Missing {p}')
        write_json(a.lock_out,dict(reference_sha=REFERENCE_SHA,files={str(p):file_hash(p) for p in sorted(set(paths))},
            provenance='Integrity lock of supplied staged files; verify source artifact run/SHA independently before use',
            origin_runs=[39256621315,38875080492,39376076166,39893308814],rf_executed=False))
        return 0
    if not a.execute_rf:
        raise ContractError('No RF work launched. stage requires explicit --execute-rf; audit-code is implementation-only.')
    if not a.stage:raise ContractError('--stage required')
    ws.require_stage('AUDIT')
    from .native import NativeAssets
    from .stages import run
    try:
        assets=NativeAssets(cfg);run(a.stage,ws,assets)
    except BlockedError as e:
        ws.receipt(a.stage,'BLOCKED',reason=str(e));raise
    except Exception as e:
        ws.receipt(a.stage,'QA_FAIL',reason=f'{type(e).__name__}: {e}');raise
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (BlockedError,ContractError) as exc:
        print(f'{type(exc).__name__}: {exc}',file=sys.stderr);raise SystemExit(2)
