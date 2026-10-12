"""Validate the on-demand Legacy Method-B backend against stored H (FULL_RF, LoS) at delivered poses. Run with the Sionna venv python."""
import sys,json,time
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
import legacy_backend as L
from qclean_uwb.drivesim.body_pose_channel import RFPoseRequest
S=Path('/tmp/claude-0/-home-user-sionna-resimulation/1215cd75-99f4-55ac-b01a-7c56293627ba/scratchpad')
FR=Path('/home/user/sionna-resimulation/results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C')
out={}
for case,route,anc,mount in (('R2_aA_m0','R2',4.0,0),('R4_aB_m0','R4',10.0,0)):
    poses=json.load(open(S/f'rf_poses_{route}.json'));H=np.load(FR/'FULL_RF'/f'H_{case}.npy',mmap_mode='r');HL=np.load(FR/f'H_LoS_{case}.npy',mmap_mode='r')
    be=L.LegacyMethodBAtPose(out_dir=S/f'rt_scene_{case}',anchor_x_m=anc,mount_deg=mount);rows=[]
    for i in np.linspace(0,len(poses)-1,5).astype(int):
        p=poses[int(i)];req=RFPoseRequest(packet_id=f'v{i}',t_s=0.,true_pose_xyyaw=(p['x'],p['y'],np.radians(p['yaw_body_deg'])),mount_deg=float(mount),station_id=0,point_index=0)
        ch=be.generate(req);ref=np.asarray(H[int(i)]);refl=np.asarray(HL[int(i)])
        rows.append(dict(pose=int(i),rel_full=float(np.linalg.norm(ch.H_full-ref)/np.linalg.norm(ref)),rel_los=float(np.linalg.norm(ch.H_los-refl)/np.linalg.norm(refl))))
        print(case,rows[-1],flush=True)
    out[case]=dict(rows=rows,trace_calls=be.calls,sec_per_trace=be.seconds/be.calls)
json.dump(out,open(Path(__file__).resolve().parent/'backend_validation.json','w'),indent=1);print(json.dumps({k:dict(max_rel_full=max(r['rel_full'] for r in v['rows']),max_rel_los=max(r['rel_los'] for r in v['rows']),sec_per_trace=v['sec_per_trace']) for k,v in out.items()}))
