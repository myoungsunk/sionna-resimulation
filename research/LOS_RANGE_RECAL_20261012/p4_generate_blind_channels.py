"""P4 step 2 (Sionna venv): generate Legacy Method-B channels (Full + LoS, mount 0/45) at the frozen blind sites for both anchors, using the validated on-demand backend.
Output: shard npz with H arrays + a manifest. NO truth is written here. usage: p4_generate_blind_channels.py SITES.json OUT_DIR SHARD NSHARD"""
import sys,json,hashlib,time
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE.parent/'STAGE_C_PILOT_20261012'))
import legacy_backend as L
from qclean_uwb.drivesim import rf_store as RS
sites=json.load(open(sys.argv[1]))['sites'];out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True);shard,nshard=int(sys.argv[3]),int(sys.argv[4])
jobs=[(an,s) for an in (4.0,10.0) for s in sites];mine=[j for i,j in enumerate(jobs) if i%nshard==shard]
be={};keys=[];HF=[];HL=[];t0=time.time()
for an,s in mine:
    if an not in be:be[an]=L.LegacyMethodBAtPose(out_dir=out/f'scene_{shard}_{int(an)}',anchor_x_m=an,mount_deg=0.)
    b=be[an];tr=b.trace(s['x'],s['y'])
    for m in (0,45):
        yaw=s['yaw_deg']+m;HF.append(RS.h_for_antenna_yaws(tr,b.banks,[yaw])[0]);HL.append(RS.h_for_antenna_yaws(b._los_only(tr),b.banks,[yaw])[0]);keys.append((s['site_id'],an,m))
    print(shard,s['site_id'],an,'%.0fs'%(time.time()-t0),flush=True)
np.savez_compressed(out/f'shard{shard}.npz',H_full=np.array(HF),H_los=np.array(HL),site_id=np.array([k[0] for k in keys]),anchor_x=np.array([k[1] for k in keys]),mount=np.array([k[2] for k in keys]))
(out/f'shard{shard}_receipt.json').write_text(json.dumps(dict(n=len(keys),seconds=time.time()-t0,backend_provenance=next(iter(be.values())).provenance if be else None,command=' '.join(sys.argv)),indent=1,default=str))
