#!/usr/bin/env python3
"""Canonical entrypoint for V02/V03 on the native tree.
Native filters.FilterConfig is legacy; the documented body bridge adds the
frozen Sensor-v2 fields via V2BodyFilterConfig. This local adapter changes no
numerical coefficient, gain, model source or stored result.
"""
from pathlib import Path
import json,runpy,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from qclean_uwb.drivesim import filters
from qclean_uwb.drivesim.body_ekf_bridge import V2BodyFilterConfig
filters.FilterConfig=V2BodyFilterConfig
if __name__=='__main__':
    script=sys.argv.pop(1)
    if script not in ['run_v02_ideal_consistency.py','run_v03_pole_recovery.py']:
        raise ValueError('Unsupported native P0 runner')
    path=Path(__file__).with_name(script)
    try:runpy.run_path(str(path),run_name='__main__')
    except Exception as e:
        if '--out' in sys.argv:
            out=Path(sys.argv[sys.argv.index('--out')+1]);out.mkdir(parents=True,exist_ok=True)
            (out/'EXECUTION_FAILURE.json').write_text(json.dumps({'exception':type(e).__name__,'message':str(e),'native_config':'V2BodyFilterConfig'},indent=2))
        raise
