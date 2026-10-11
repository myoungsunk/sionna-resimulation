#!/usr/bin/env python3
"""Canonical P0 native-tree entrypoint with transparent, archived adapters.
No in-place edits of original sensor-v2 or historical results. Exact executed
source and SHA are saved. V03 v1 is retained as superseded diagnostic only.
"""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
if __name__=='__main__':
    script=sys.argv.pop(1)
    if script not in ['run_v02_ideal_consistency.py','run_v03_pole_recovery.py']:
        raise ValueError('Unsupported native P0 runner')
    path=Path(__file__).with_name(script);source=path.read_text();changes=[]
    needle='from qclean_uwb.drivesim.filters import FilterConfig'
    assert source.count(needle)==1
    source=source.replace(needle,'from qclean_uwb.drivesim.body_ekf_bridge import V2BodyFilterConfig as FilterConfig')
    changes.append('Native documented V2BodyFilterConfig instead of incompatible legacy FilterConfig')
    if script=='run_v03_pole_recovery.py':
        source=source.replace('from pole_safe_model import PoleSafeModel','from pole_safe_model_v2 import PoleSafeModelV2 as PoleSafeModel')
        source=source.replace('for theta in [1.,3.]:','for theta in [2.,3.]:')
        changes.append('V2 Cartesian core covers full theta0 bad cell <=2deg; test splice boundaries 2 and 3deg')
    out=Path(sys.argv[sys.argv.index('--out')+1]);out.mkdir(parents=True,exist_ok=True)
    srcout=out/'execution_source';srcout.mkdir(exist_ok=True)
    for p in path.parent.glob('*.py'):(srcout/p.name).write_bytes(p.read_bytes())
    (srcout/('EXECUTED_'+script)).write_text(source)
    rec={'source_script':script,'original_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
         'executed_sha256':hashlib.sha256(source.encode()).hexdigest(),'adapters':changes,
         'native_base':'5a50fa9f0813a3dd0f9ca53e26da3cd3fbcfada9'}
    (out/'EXECUTED_SOURCE_RECEIPT.json').write_text(json.dumps(rec,indent=2))
    try:exec(compile(source,str(path),'exec'),{'__file__':str(path),'__name__':'__main__'})
    except Exception as e:
        (out/'EXECUTION_FAILURE.json').write_text(json.dumps({'exception':type(e).__name__,'message':str(e),'native_config':'V2BodyFilterConfig'},indent=2))
        raise
