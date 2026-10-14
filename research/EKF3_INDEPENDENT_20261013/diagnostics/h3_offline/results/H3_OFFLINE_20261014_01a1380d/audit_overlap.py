"""Read-only spatial holdout feasibility audit, no threshold changes."""
import json
import numpy as np
from scipy.spatial import cKDTree
import h3_offline as h
from run_full import load_caches,save_csv
p0=json.loads((h.ROOT/'GATES_01/VERIFIED_INPUTS.json').read_text())['p0']
data,_=load_caches(p0);rows=[]
for route in sorted({case['route'] for case in p0['cases']}):
    tree=cKDTree(np.concatenate([data[(c['id'],'los')]['truth'][:,:2] for c in p0['cases'] if c['route']==route]))
    for case in p0['cases']:
        if case['route']==route:continue
        block=data[(case['id'],'los')];mask=block['t']>=h.C['evaluation_start_s'];distance=tree.query(block['truth'][mask,:2])[0]
        rows.append(dict(heldout_route=route,training_case=case['id'],training_route=case['route'],n_candidates=len(distance),n_buffer_valid=int((distance>h.C['training_spatial_buffer_m']).sum()),minimum_distance_m=float(distance.min()),median_distance_m=float(np.median(distance)),maximum_distance_m=float(distance.max()),buffer_m=h.C['training_spatial_buffer_m']))
save_csv(h.ROOT/'SPATIAL_HOLDOUT_FEASIBILITY.csv',rows)
print(json.dumps(rows,indent=2))
