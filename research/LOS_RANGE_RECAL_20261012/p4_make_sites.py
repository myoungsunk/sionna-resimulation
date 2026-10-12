"""P4 step 1 (run BEFORE any blind channel exists): draw the frozen blind TEST sites. New physical XY (never a route site), one random yaw per site.
Rules are those written into TRAIN_VAL_TEST_SITE_SPLIT.json at P0. usage: p4_make_sites.py OUT.json"""
import json,sys,hashlib
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[2];G7=ROOT/'research/V01B_CLOSURE_20261012/G7/out'
split=json.load(open(Path(__file__).parent/'out_p0_p5/R1/P0/TRAIN_VAL_TEST_SITE_SPLIT.json'))['TEST_blind']
l=pd.read_csv(G7/'02_LABELS_EVAL_ONLY_12.csv',usecols=['true_x','true_y']).drop_duplicates();route_xy=l.to_numpy()
rng=np.random.default_rng(split['seed']);sites=[];tries=0
while len(sites)<split['n_sites']:
    tries+=1;x=rng.uniform(1.5,18.5);y=rng.uniform(-0.70,0.70)
    if np.min(np.hypot(route_xy[:,0]-x,route_xy[:,1]-y))<0.05:continue
    if min(np.hypot(x-4.0,y),np.hypot(x-10.0,y))<0.30:continue
    if any(np.hypot(x-s['x'],y-s['y'])<0.03 for s in sites):continue
    sites.append(dict(site_id=f'T{len(sites):03d}',x=round(float(x),4),y=round(float(y),4),yaw_deg=round(float(rng.uniform(-180,180)),4)))
out=dict(rules=split,n_sites=len(sites),draws=tries,sites=sites);out['sha256_of_sites']=hashlib.sha256(json.dumps(sites,sort_keys=True).encode()).hexdigest()
Path(sys.argv[1]).write_text(json.dumps(out,indent=1));print(len(sites),'sites',tries,'draws',out['sha256_of_sites'][:12]);print('min distance to any route site: %.3f m'%min(np.min(np.hypot(route_xy[:,0]-s['x'],route_xy[:,1]-s['y'])) for s in sites))
