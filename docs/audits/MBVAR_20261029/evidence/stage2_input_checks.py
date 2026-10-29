import urllib.request,io,numpy as np,json,hashlib,concurrent.futures
ref='9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13'
repo='https://media.githubusercontent.com/media/myoungsunk/sionna-resimulation/'+ref+'/'
raw='https://raw.githubusercontent.com/myoungsunk/sionna-resimulation/'+ref+'/'
base='research/DS_MASK_CAUSAL_X1_X2_20261026/'
blk='results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/'
expected=json.loads('{"R2_aA_m0_B0.npz":"df8ac0c18d1829fb57e6c71c86888e634a20f47ae0705df21624e1783590b37e","R2_aA_m0_L2.npz":"55fe34ee7016e64119aadbde006f839cef2bc90f4cefe92510bc1a77c75ff55a","R2_aA_m45_B0.npz":"08443ed214057b5ec0d9a233f3877b261441e797a6446a173bd08eac6ac5d147","R2_aA_m45_L2.npz":"25e6928e6369bf5bf60c085c2d5515e1241a1b356c07601a88bb9d35e4e97b00","R2_aB_m0_B0.npz":"e1013f6949f9c7b01643d6daf13c447e76c020d5f19a222ce12a08251699c3ac","R2_aB_m0_L2.npz":"b2214668ae6aa1530b4e4b4e6a28249bc2c8f49d76f78d8f038013a6da239922","R4_aA_m0_B0.npz":"b999d12690c4ec03473d7ee37072c91a9349e1d3488ff1f5fba5f06ec3b8b1d2","R4_aA_m0_L2.npz":"d6f950ee8e6da80ebcd820d909ebd391fb61e33578ba0420be801683c96a1b81","R4_aB_m0_B0.npz":"f1a2e6c98b0485b464db26a9697a4212dbdfe90deef3132fe312693f29e1180e","R4_aB_m0_L2.npz":"c4b75927534934969755f4f63000cf151e84b8c4392ef54919d6c45874dcb34e","R5_aA_m0_B0.npz":"5fea1a984fd70cee35ef0bc75b46d3713f32eab1c7ec9c63cd4e5a2bea1f39fa","R5_aA_m0_L2.npz":"5cb09f346ddba41b7389b3a791090d00413c61b1c95a69455f0bac98c619cc43","R5_aB_m0_B0.npz":"596a76e42ba54629a8c97a2837906259238a240ec1d20d94fd5221c9781250e3","R5_aB_m0_L2.npz":"b88c517d6388a159b684c619c18ab0fda5ccb30a849b1540c2315c5fe1a62bd5"}')
def gettrace(name):
 data=urllib.request.urlopen(repo+base+'why_ds_worse/CONTROL/'+name,timeout=45).read()
 with np.load(io.BytesIO(data),allow_pickle=False) as q:z={k:q[k] for k in q.files}
 t=z['t_s'];ids=z['pose_id'];dt=np.diff(t);n=len(t);jb=list(z['names']).index('OFF_BB');jm=list(z['names']).index('OFF_MB')
 zz=z['nu']+z['h']+z['mu'];valid=np.isfinite(zz[:,jb]).all(1);acc=z['acc'][:,jb].astype(bool);sel=(t>=30-1e-9)&valid&acc;ix=np.flatnonzero(sel)
 gaps=np.diff(t[ix]);out=dict(name=name,sha256=hashlib.sha256(data).hexdigest(),hash_match=hashlib.sha256(data).hexdigest()==expected[name],bytes=len(data),n=n,t0=float(t[0]),tend=float(t[-1]),time_nonfinite=int((~np.isfinite(t)).sum()),dt_nonpositive=int((dt<=0).sum()),dt_max_deviation_02=float(np.max(np.abs(dt-.2))),pose_duplicates=n-len(np.unique(ids)),pose_first=int(ids[0]),pose_last=int(ids[-1]),row_shapes_ok=all(z[k].shape[0]==n for k in ['pose_id','truth_scoring_only','x','P','prior','Pprior','h','H','K','mu','R','nu','acc']),finite_z=int(valid.sum()),base_accepted=int(acc.sum()),scoring_selected=len(ix),selected_nonadjacent_pairs=int((np.diff(ix)!=1).sum()),selected_max_gap_s=float(gaps.max()) if len(gaps) else None,z_cross_arm_maxdiff=float(np.max(np.abs(zz-zz[:,[jb]]))),mu_s_BB_MB_maxdiff=float(np.max(np.abs(z['mu'][:,jb,1]-z['mu'][:,jm,1]))),R_BB_MB_maxdiff=float(np.max(np.abs(z['R'][:,jb]-z['R'][:,jm]))))
 return name,z,out
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:arr=list(ex.map(gettrace,expected))
zs={name:z for name,z,o in arr};out=[o for _,_,o in arr];pairs=[]
cases=sorted(set(n.rsplit('_',1)[0] for n in expected))
for c in cases:
 a=zs[c+'_B0.npz'];b=zs[c+'_L2.npz'];j=list(a['names']).index('OFF_BB');z0=a['nu'][:,j]+a['h'][:,j]+a['mu'][:,j];z2=b['nu'][:,j]+b['h'][:,j]+b['mu'][:,j]
 pairs.append(dict(case=c,time_equal=bool(np.array_equal(a['t_s'],b['t_s'])),pose_equal=bool(np.array_equal(a['pose_id'],b['pose_id'])),truth_maxdiff=float(np.max(np.abs(a['truth_scoring_only'][:,:3]-b['truth_scoring_only'][:,:3]))),z_maxdiff=float(np.max(np.abs(z0-z2))),mu_maxdiff=float(np.max(np.abs(a['mu']-b['mu']))),R_maxdiff=float(np.max(np.abs(a['R']-b['R']))),base_mask_diff=int(np.sum(a['acc'][:,j]!=b['acc'][:,j]))))
samples=[]
for c in cases:
 data=urllib.request.urlopen(raw+blk+c+'/SAMPLES.json',timeout=45).read();s=json.loads(data);sid=[int(v['pose_id']) for v in s];lookup={v:i for i,v in enumerate(sid)};a=zs[c+'_B0.npz'];ids=a['pose_id'];missing=[int(v) for v in ids if int(v) not in lookup];sel=[s[lookup[int(v)]] for v in ids if int(v) in lookup]
 gt=a['truth_scoring_only'];xy=np.array([[v['x'],v['y']] for v in sel]);yaw=np.deg2rad([v['yaw_body_deg'] for v in sel])
 samples.append(dict(case=c,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),n_samples=len(s),sample_id_duplicates=len(sid)-len(set(sid)),missing_trace_ids=missing,n_trace=len(ids),sample_row_indices_equal_trace_ids=bool(np.array_equal([lookup[int(v)] for v in ids],ids)),max_abs_xy_diff=float(np.max(np.abs(xy-gt[:,:2]))),max_abs_wrapped_yaw_diff_rad=float(np.max(np.abs(np.angle(np.exp(1j*(yaw-gt[:,2]))))))))
print(json.dumps(dict(source_ref=ref,traces=out,pairs=pairs,samples=samples,total_trace_bytes=sum(o['bytes'] for o in out)),allow_nan=False))
