from pathlib import Path
import sys,json,hashlib,csv,collections
import numpy as np
J=Path('/job');R=Path('/routes/source/results/DRIVE_SIM_20261007');S2=R/'SNOWBALL_ROUTES_01a11669/S2';D=J/'BLOCK_D';D.mkdir(exist_ok=False)
l2=json.loads(Path('/previous/L2_ATTEMPT3/SAMPLES.json').read_text());rows=[]
for route in ['R2','R4','R5']:
 timeline=R/'S1/routes'/('timeline_'+route+'_Tnone.csv');rr=list(csv.DictReader(timeline.open()));allxy=np.array([[float(x['x']),float(x['y'])] for x in rr]);phases=dict(collections.Counter(x['phase'] for x in rr))
 for anchor in ['aA','aB']:
  p=S2/('G3_continuity_'+route+'_'+anchor+'.json');gate=json.loads(p.read_text());mins=[float(np.min(np.max(abs(allxy-np.array([x['x'],x['y']])),axis=1))) for x in l2]
  rows.append({'route':route,'anchor':anchor,'G3_path':str(p),'G3_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'G3_stations':gate['stations'],'stored_pass_strict':gate.get('passed_strict_prereg_tol'),'timeline_phase_counts':phases,'L2_same_pose_set':False,'L2_nearest_timeline_xy_maxnorm_m':mins,'L2_matching_xy_count_tolerance_1e-6':sum(x<=1e-6 for x in mins),'interpretation':'G3 station set is empty in stored route gate; its PASS is not evidence of a verified pose set; L2 uses8 random poses and is separate. No retrospective chronology repair.'})
(D/'G3_POSE_COMPARISON.json').write_text(json.dumps({'rows':rows,'L2_scope':'8 broadband poses, not2056 independent s','status':'verified different sets; stored G3 empty evaluation remains invalid evidence'},indent=2))
# Record original Method B path dictionary fields; retain all original traces in BLOCK_C.
sys.path.insert(0,str(J/'source/src'))
from qclean_uwb.drivesim import pattern_apply as P,rf_store as RF
from qclean_uwb.scenarios.corridor import ANCHOR_ROTATION,rot_z
banks=[]
for name in ['LP_plus45','LP_minus45']:
 with np.load('/legacy/source/'+name+'_bank.npz') as z:banks.append(P.Bank({k:z[k] for k in z.files}))
freq=banks[0].freqs_hz;poses=json.loads((R/'S1/routes/rf_poses_R2.json').read_text());original=np.load(S2/'H_R2_aA_m0.npy',mmap_mode='r');offsets=[0];coeff=[];taus=[];ang=[];inter=[];obj=[];summary=[];maxdiff=0;cache={};keys=None
for pose in poses:
 tag=RF.tag_of(pose['x'],pose['y']);path=S2/'traces_R2_aA'/(tag+'_trace.npz')
 if tag not in cache:
  tr=RF.load_trace(path);j=P.interp_jones(tr['jones'],tr['node_freq_hz'],freq[128:129],present=tr.get('present'));tx=np.stack([P.field_world(b,ANCHOR_ROTATION,tr['ang'][0],tr['ang'][1],bins=[128]) for b in banks]);cache[tag]=(tr,j,tx)
 tr,j,tx=cache[tag];keys=list(tr)
 rx=np.stack([P.field_world(b,rot_z(pose['yaw_body_deg']),tr['ang'][2],tr['ang'][3],bins=[128]) for b in banks]);a=np.einsum('rbni,bnij,tbnj->brtn',rx,j,tx)[0];tau=tr['tau'];h=np.einsum('rtn,n->rt',a,np.exp(-2j*np.pi*freq[128]*tau));delta=float(np.max(abs(h-original[pose['pose_id'],128])));maxdiff=max(maxdiff,delta);assert delta<1e-12
 n=len(tau);coeff.append(a.transpose(2,0,1));taus.append(tau);ang.append(tr['ang'].T);offsets.append(offsets[-1]+n)
 order=np.argsort(tau);first,second=order[:2];amp=np.abs(a[:,0,:]) if False else np.abs(a[:,:,first])
 summary.append({'pose_id':pose['pose_id'],'n_paths':n,'first_path_id':int(first),'second_path_id':int(second),'delay_gap_s':float(tau[second]-tau[first]),'tx0_rx0_second_over_first_amplitude':float(abs(a[0,0,second])/abs(a[0,0,first])),'tx0_rx1_second_over_first_amplitude':float(abs(a[1,0,second])/abs(a[1,0,first]))})
np.savez_compressed(D/'STORED_FULL_PATHS_R2A_m0_CENTER_BIN.npz',a=np.concatenate(coeff),tau=np.concatenate(taus),angles=np.concatenate(ang),offsets=np.array(offsets),frequency_hz=freq[128])
import pandas as pd
pd.DataFrame(summary).to_csv(D/'FIRST_SECOND_PATH_R2A_m0_CENTER_BIN.csv',index=False)
(D/'PATH_OUTPUT_PROVENANCE.json').write_text(json.dumps({'method':'offline port coefficient reconstruction from original Method B node Jones traces at center bin128; not new full RF simulation','poses':len(poses),'frequency_hz':float(freq[128]),'max_abs_H_sum_error_vs_stored_full_H':maxdiff,'original_trace_keys':keys,'angles_order':['theta_t','phi_t','theta_r','phi_r'],'angles_unit':'rad','a_layout':'flat paths,rx,tx; offsets index each pose','full_band_original_Jones_nodes':'BLOCK_C/STORED_PATH_TRACES_R2_aA','interaction_face_information':'original trace fields if present; not inferred as native labels from angles','note':'delay order separates first/second geometric paths; not first-path CIR tap or detection'},indent=2))
print('metadata and stored path coefficients complete')
