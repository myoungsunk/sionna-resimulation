from pathlib import Path
import json,hashlib,numpy as np,pandas as pd
root=Path(__file__).parent;remote=root/'retrieved';r=remote/'L2_ATTEMPT3';manifest=json.loads((remote/'OUTPUT_MANIFEST.json').read_text())
bad=[n for n,v in manifest.items() if not (remote/n).is_file() or hashlib.sha256((remote/n).read_bytes()).hexdigest()!=v['sha256']];assert not bad,bad
result=json.loads((r/'RESULT.json').read_text());legacy=json.loads((remote/'LEGACY_L2_CHECK.json').read_text());rows=result['rows'];z=np.load(r/'CHANNELS.npz');H=z['H'];D=z['H_direct'];D10=z['H_direct10'];f=z['freqs_hz'];n=len(f);df=f[1]-f[0];assert H.shape==(8,257,2,2) and np.isfinite(H).all() and (z['counts']==1).all()
def observe(h):
 w=.5-.5*np.cos(2*np.pi*np.arange(n)/(n-1));c=np.fft.ifft(h[:,:,0]*w[:,None],n=4*n,axis=0)*n
 branch=np.argmax(np.abs(c).max(axis=0));idx=np.flatnonzero(np.abs(c[:,branch])>=.3*np.abs(c[:,branch]).max())[0]
 pw=np.abs(c[idx])**2;return float((pw[0]-pw[1])/pw.sum()),int(idx),pw
checks=[];max_s=0.;max_pow=0.;max_retime_h=0.;max_identity=0.;max_native_h=0.;max_retime_s=0.
for i,row in enumerate(rows):
 for h,key,tap,powkey in [(H[i],'s_sionna','tap_sionna','power_sionna'),(D[i],'s_direct_actual','tap_direct','power_direct'),(D10[i],'s_direct10','tap_direct10','power_direct10')]:
  s,k,pw=observe(h);max_s=max(max_s,abs(s-row[key]));max_pow=max(max_pow,float(np.max(np.abs(pw-np.array(row[powkey])))));assert k==row[tap] and abs(s-row[key])<1e-12
 d=row['range_m'];retimed=D[i]*(d/10)*np.exp(-2j*np.pi*f*(10-d)/299792458.)[:,None,None];max_retime_h=max(max_retime_h,float(np.linalg.norm(retimed-D10[i])/np.linalg.norm(D10[i])));max_retime_s=max(max_retime_s,abs(observe(retimed)[0]-row['s_direct10']))
 a=row['s_lut']-row['s_direct10'];b=row['s_direct10']-row['s_direct_actual'];c=row['s_direct_actual']-row['s_sionna'];err=row['s_lut']-row['s_sionna'];max_identity=max(max_identity,abs(err-a-b-c))
 max_native_h=max(max_native_h,float(np.linalg.norm(H[i]-D[i])/np.linalg.norm(D[i])))
 checks.append(dict(pose_id=i,range_m=d,theta_deg=row['angles_deg'][0],s_lut=row['s_lut'],s_sionna=row['s_sionna'],s_direct_actual=row['s_direct_actual'],s_direct10=row['s_direct10'],lut_minus_sionna=err,lut_minus_direct10=a,direct10_minus_actual=b,actual_minus_sionna=c,tap_sionna=row['tap_sionna'],tap_actual=row['tap_direct'],tap10=row['tap_direct10'],violates_original_L2=abs(err)>.005))
for new,old in zip(rows,legacy['rows']):
 for k in ['x','y','yaw_deg','s_lut','s_sionna']:assert abs(new[k]-old[k])<1e-12,(i,k)
assert max_identity<1e-12 and max_retime_h<1e-10
pd.DataFrame(checks).to_csv(root/'L2_ERROR_DECOMPOSITION.csv',index=False)
out=dict(transferred_files_verified=len(manifest),L2_pose_count=len(rows),solver_calls=result['solver_calls'],path_count_all_one=True,original_L2_max=result['abs_ds_max'],original_L2_threshold=.005,original_L2_violations=sum(x['violates_original_L2'] for x in checks),original_L2_pass=False,legacy_pose_and_s_values_reproduced_tolerance=1e-12,independent_observation_max_s_error=max_s,independent_observation_max_abs_power_error=max_pow,max_direct_actual_vs_sionna_s=max(abs(x['actual_minus_sionna']) for x in checks),max_direct_actual_vs_sionna_H_relative=max_native_h,max_delay_error_s=float(np.max(abs(z['delays_s']-np.array([x['range_m']/299792458. for x in rows])[:,None]))),max_distance_retiming_H_relative_error=max_retime_h,max_distance_retiming_s_error=max_retime_s,max_decomposition_identity_error=max_identity,interpretation='only8originalposes; actual-distance direct/Sionna agreement does not repair fixed10m LUT nor full RF')
(root/'RF_VERIFICATION.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
