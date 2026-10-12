"""Build + run G7 sensor-v2 replay on 12 legacy cases using the frozen simulate.py unchanged except paths / worker count / no trace dump."""
import json,sys,hashlib
from pathlib import Path
import numpy as np,pandas as pd
S=Path(__file__).resolve().parent;G=S/'g7';J=G/'job'
REPO=Path('/home/user/sionna-resimulation');RUN=REPO/'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff'
ROUTES=REPO/'results/DRIVE_SIM_20261007/S1/routes'
sys.path.insert(0,str(J/'source/src'))
from qclean_uwb.drivesim import sensor_v2 as V
cases=json.loads((G/'input/BLOCK_C/CASES.json').read_text());names=[c['case'] for c in cases];assert len(names)==12
plan=json.loads((RUN/'PLAN.json').read_text());plan['cases']=names;(J/'PLAN.json').write_text(json.dumps(plan,indent=1))
rf={r:json.loads((G/'input/BLOCK_C/INPUTS'/f'rf_poses_{r}.json').read_text()) for r in ('R2','R4','R5')}
for route in ['R2','R4','R5']:   # identical to audit.py motion contract (legacy-euler only is used by simulate.py)
    df=pd.read_csv(ROUTES/f'timeline_{route}_Tnone.csv');pose=df[['x','y','yaw_body_deg']].to_numpy();pose[:,2]=np.radians(pose[:,2]);t=df.t_s.to_numpy();ids=df.pose_id.to_numpy(int)
    rp=np.array([[r['x'],r['y'],r['yaw_body_deg']] for r in rf[route]])[ids];assert np.max(abs(df[['x','y','yaw_body_deg']].to_numpy()-rp))<=1e-6
    d,a=V.motion_increments(t,pose,convention='legacy-euler');np.savez_compressed(J/'OUTPUT'/f'MOTION_{route}_legacy-euler.npz',t=t,pose=pose,ds=d,dtheta=a,pose_id=ids)
src=(RUN/'simulate.py').read_text()
for a,b in (("Path('/job')",f"Path('{J}')"),("Path('/routes/source/results/DRIVE_SIM_20261007/S1/routes')",f"Path('{ROUTES}')"),("Path('/input/BLOCK_C')",f"Path('{G}/input/BLOCK_C')"),("Path('/lut')",f"Path('{G}/lut')"),("max_workers=32","max_workers=4")):
    assert a in src,a;src=src.replace(a,b)
# do not dump per-run traces (multi-GB); metrics rows are unchanged
old="path=J/'TRACES'/phase/f'{case}_d{level}_s{seed}_{arm}_{initial}_{wb}.npz';path.parent.mkdir(parents=True,exist_ok=True);assert not path.exists();np.savez_compressed(path,**arr)\n path.with_suffix('.json').write_text(json.dumps({'row':row,'filter_config':dataclasses.asdict(cfg),'generator':cfgsensor.manifest()},indent=2));return row"
assert old in src;src=src.replace(old,"return row")
(J/'simulate_g7.py').write_text(src);print('built',len(names),'cases; simulate_g7.py sha',hashlib.sha256(src.encode()).hexdigest()[:16])
