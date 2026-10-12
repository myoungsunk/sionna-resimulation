"""Expanded parity of the on-demand Legacy Method-B backend against stored H for ALL 12 conditions (routes R2/R4/R5 x anchors A/B x mounts 0/45).
Positions per (route, anchor): every 10th unique position + stress positions (10 closest to the anchor axis, 5 largest |y|, 5 smallest/largest x, 10 farthest from the anchor).
Criteria fixed before the run: rel H error <= 1e-3 (full and LoS); |d s| <= 0.01; |d first-path range| <= 0.005 m; first-path tap equal (full and LoS).
usage (Sionna venv): parity_expand.py SHARD N_SHARDS"""
import sys,json,time,hashlib
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import legacy_backend as L
from qclean_uwb.drivesim import rf_store as RS
S=Path('/tmp/claude-0/-home-user-sionna-resimulation/1215cd75-99f4-55ac-b01a-7c56293627ba/scratchpad')
sys.path.insert(0,str(S))
import importlib.util
spec=importlib.util.spec_from_file_location('obs_frozen',str(S/'obs_frozen.py'));OBS=importlib.util.module_from_spec(spec);sys.modules['obs_frozen']=OBS;spec.loader.exec_module(OBS)
FR=Path('/home/user/sionna-resimulation/results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C');DA=S/'deliv/research/V01B_DATA_REQUEST_20261011/DELIVERY_A_20261012';DL=S/'dl_release'
FQ=np.load(FR/'freqs_hz.npy');ANCH={'aA':4.0,'aB':10.0}
def stored(case):
    for p in (FR/'FULL_RF'/f'H_{case}.npy',DA/f'H_{case}.npy'):
        if p.exists():return np.load(p,mmap_mode='r')
    raise FileNotFoundError(case)
def stored_los(case):
    for p in (FR/f'H_LoS_{case}.npy',DL/f'H_LoS_{case}.npy'):
        if p.exists():return np.load(p,mmap_mode='r')
    raise FileNotFoundError(case)
def sample_positions(poses,anchor_x):
    tags={};order=[]
    for p in poses:
        t=RS.tag_of(p['x'],p['y'])
        if t not in tags:tags[t]=[];order.append((t,p['x'],p['y']))
        tags[t].append(p)
    xy=np.array([[x,y] for _,x,y in order]);d=np.hypot(xy[:,0]-anchor_x,xy[:,1])
    pick=set(range(0,len(order),10))|set(np.argsort(d)[:10])|set(np.argsort(-np.abs(xy[:,1]))[:5])|set(np.argsort(xy[:,0])[:5])|set(np.argsort(-xy[:,0])[:5])|set(np.argsort(-d)[:10])
    return [(order[i][0],order[i][1],order[i][2],tags[order[i][0]],('stress' if i%10 else 'grid')) for i in sorted(pick)]
if __name__=='__main__':
    shard,nshard=int(sys.argv[1]),int(sys.argv[2]);jobs=[(r,a) for r in ('R2','R4','R5') for a in ('aA','aB')]
    rows=[]
    for ji,(route,anc) in enumerate(jobs):
        if ji%nshard!=shard:continue
        poses=json.load(open(S/f'rf_poses_{route}.json'));be=L.LegacyMethodBAtPose(out_dir=S/f'rt_scene_par_{route}_{anc}',anchor_x_m=ANCH[anc],mount_deg=0.)
        Hs={m:stored(f'{route}_{anc}_m{m}') for m in (0,45)};HL={m:stored_los(f'{route}_{anc}_m{m}') for m in (0,45)}
        for tag,x,y,ps,kind in sample_positions(poses,ANCH[anc]):
            tr=be.trace(x,y)
            for m in (0,45):
                for p in ps:
                    yaw=p['yaw_body_deg']+m;full=RS.h_for_antenna_yaws(tr,be.banks,[yaw])[0];los=RS.h_for_antenna_yaws(be._los_only(tr),be.banks,[yaw])[0]
                    ref=np.asarray(Hs[m][p['pose_id']]);refl=np.asarray(HL[m][p['pose_id']])
                    o=OBS.observe(np.stack([full,ref]),FQ,None,None,tx=0);ol=OBS.observe(np.stack([los,refl]),FQ,None,None,tx=0)
                    rows.append(dict(route=route,anchor=anc,mount=m,pose_id=int(p['pose_id']),tag=tag,kind=kind,horiz_dist_anchor=float(np.hypot(x-ANCH[anc],y)),rel_full=float(np.linalg.norm(full-ref)/np.linalg.norm(ref)),rel_los=float(np.linalg.norm(los-refl)/np.linalg.norm(refl)),
                        d_range_full=float(abs(o['range_m'][0]-o['range_m'][1])),d_s_full=float(abs(o['s'][0]-o['s'][1])),tap_equal_full=bool(o['index'][0]==o['index'][1]),
                        d_range_los=float(abs(ol['range_m'][0]-ol['range_m'][1])),d_s_los=float(abs(ol['s'][0]-ol['s'][1])),tap_equal_los=bool(ol['index'][0]==ol['index'][1])))
            print(route,anc,tag,kind,len(rows),flush=True)
            Path(HERE/f'parity_expand_shard{shard}.json').write_text(json.dumps(rows))
