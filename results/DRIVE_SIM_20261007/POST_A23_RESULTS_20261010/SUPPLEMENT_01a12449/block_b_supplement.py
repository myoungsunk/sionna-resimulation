from pathlib import Path
import sys,json,hashlib,itertools
import numpy as np,pandas as pd
J=Path('/job');sys.path.insert(0,str(J/'source/src'));out=J/'BLOCK_B';out.mkdir(exist_ok=False)
from qclean_uwb.drivesim import hs_lut as L,observation as O,pattern_apply as P
from qclean_uwb.scenarios.corridor import CorridorSetup,ANCHOR_ROTATION,rot_z
banks=[]
for name in ['LP_plus45','LP_minus45']:
 with np.load('/legacy/source/'+name+'_bank.npz') as z:banks.append(P.Bank({k:z[k] for k in z.files}))
z=np.load('/previous/L2_ATTEMPT3/CHANNELS.npz');freq=z['freqs_hz'];n=len(freq);df=freq[1]-freq[0];dt=1/(4*n*df)
lut=np.load('/legacy/source/results/DRIVE_SIM_20261007/S4/hs_lut_2deg.npy');samples=json.loads(Path('/previous/L2_ATTEMPT3/SAMPLES.json').read_text());res=json.loads(Path('/previous/L2_ATTEMPT3/RESULT.json').read_text())
def chain(h):
 cir=np.fft.ifft(h[:,:,0]*np.hanning(n)[:,None],n=4*n,axis=0)*n;mag=abs(cir);peak=mag.max(axis=0);branch=int(peak.argmax());idx=[];cross=[]
 for b in range(2):
  th=.3*peak[b];k=int(np.flatnonzero(mag[:,b]>=th)[0]);idx.append(k)
  u=float(k if k==0 else k-1+(th-mag[k-1,b])/(mag[k,b]-mag[k-1,b]));cross.append(u)
 k=idx[branch];pw=abs(cir[k])**2;s=float((pw[0]-pw[1])/pw.sum())
 return {'s':s,'tap':k,'branch':branch,'P1':float(pw[0]),'P2':float(pw[1]),'branch_taps':idx,'branch_cross_linear':cross,'branch_subtap_offset':[cross[b]-idx[b] for b in range(2)]}
def vertex(i,j,k):
 # Match original builder's explicit phi_rx, including its pole convention.
 th,pt,pr=np.deg2rad([2*i,-180+2*j,-180+2*k]);d=ANCHOR_ROTATION@np.array([np.sin(th)*np.cos(pt),np.sin(th)*np.sin(pt),np.cos(th)]);v=-d
 tht,pht=np.arccos(d[2]),np.arctan2(d[1],d[0]);tx=P.field_world(banks[0],ANCHOR_ROTATION,np.array([tht]),np.array([pht]))[:,0,:]
 tr=np.arccos(v[2]);az=np.arctan2(v[1],v[0]);rot=rot_z(np.rad2deg(az-pr));t,p=P.sph_basis(np.array([tr]),np.array([pr]));rx=[]
 for b in banks:
  et,ep=b.sample(np.array([tr]),np.array([pr]));local=et[:,0,None]*t[0]+ep[:,0,None]*p[0];rx.append(P.SCALE*local@rot.T)
 h=np.zeros((n,2,2),complex);h[:,:,0]=np.einsum('rbi,bi->br',np.array(rx),tx)*(L.C0/freq/(4*np.pi*10)*np.exp(-2j*np.pi*freq*10/L.C0))[:,None]
 c=chain(h);assert abs(c['s']-lut[i,j,k])<1e-11,(i,j,k,c['s'],lut[i,j,k]);return c
rows=[];vertexrows=[];cache={};setup=CorridorSetup()
for i,p in enumerate(samples):
 row={'pose_id':i,'distance_m':p['range_m'],'anchor_xyz':json.dumps(setup.anchor_position.tolist()),'rx_xyz':json.dumps(setup.robot_position(p['x'],p['y']).tolist()),'yaw_deg':p['yaw_deg'],'mount_deg':0}
 theta,a,b=p['angles_deg'];t=np.clip(theta/2,0,45-1e-9);af=(a+180)/2;bf=(b+180)/2;i0,j0,k0=int(np.floor(t)),int(np.floor(af)),int(np.floor(bf));ft,fa,fb=t-i0,af-j0,bf-k0
 row.update(theta_deg=theta,phi_tx_deg=a,phi_rx_deg=b,theta_pre_snap_deg=theta,phi_tx_pre_snap_deg=a,phi_rx_pre_snap_deg=b,theta_cell_start_deg=i0*2,phi_tx_cell_start_deg=-180+2*(j0%180),phi_rx_cell_start_deg=-180+2*(k0%180),s_lut=res['rows'][i]['s_lut'])
 for name,key in [('sionna','H'),('los_exact','H_direct'),('direct10','H_direct10')]:
  c=chain(z[key][i]);row['s_'+name]=c['s']
  for k,v in c.items():row[name+'_'+k]=json.dumps(v) if isinstance(v,list) else v
 weights=[];taps=[];vs=[]
 for di,dj,dk in itertools.product([0,1],repeat=3):
  ijk=(i0+di,(j0+dj)%180,(k0+dk)%180);w=(ft if di else 1-ft)*(fa if dj else 1-fa)*(fb if dk else 1-fb)
  if ijk not in cache:cache[ijk]=vertex(*ijk)
  c=cache[ijk];weights.append(w);taps.append(c['tap']);vs.append(c['s']);vertexrows.append({'pose_id':i,'di':di,'dj':dj,'dk':dk,'theta_deg':ijk[0]*2,'phi_tx_deg':-180+2*ijk[1],'phi_rx_deg':-180+2*ijk[2],'weight':w,'tap':c['tap'],'s_vertex':c['s'],'s_stored':float(lut[ijk]),'selected_branch':c['branch'],'P1':c['P1'],'P2':c['P2']})
 assert abs(np.dot(weights,vs)-row['s_lut'])<1e-11
 row.update(vertex_taps=json.dumps(taps),vertex_weights=json.dumps(weights),exact_minus_sionna=row['s_los_exact']-row['s_sionna'],geometry_delay_fractional_tap=p['range_m']/L.C0/dt)
 rows.append(row)
pd.DataFrame(rows).to_csv(out/'BROADBAND_POSES.csv',index=False);pd.DataFrame(vertexrows).to_csv(out/'LUT_VERTICES.csv',index=False)
calls=[{'pose_id':i,'frequency_bin':fi,'frequency_hz':float(f),'distance_m':samples[i]['range_m'],'H_real':json.dumps(z['H'][i,fi].real.tolist()),'H_imag':json.dumps(z['H'][i,fi].imag.tolist()),'delay_s':float(z['delays_s'][i,fi]),'broadband_row':i,'s_scope':'pose-wide; not an independent per-frequency s'} for i in range(8) for fi,f in enumerate(freq)]
pd.DataFrame(calls).to_csv(out/'SOLVER_CALLS.csv',index=False)
err=np.array([abs(r['exact_minus_sionna']) for r in rows]);top=np.argsort(err)[-3:][::-1]
(out/'VERIFICATION.json').write_text(json.dumps({'poses':8,'solver_calls':len(calls),'LUT_vertices':64,'max_s_difference':float(err.max()),'absolute_difference_quantiles':dict(zip(['min','p25','median','p75','max'],np.quantile(err,[0,.25,.5,.75,1]).tolist())),'max_three_rows':[rows[i] for i in top],'threshold_subtap_definition':'linear interpolation of magnitude on interval k-1,k where branch first crosses 30 percent of its own peak; diagnostic only, original observation uses integer k of selected strongest branch','LUT_vertex_method':'exact original builder explicit azimuth convention; no LUT modification','source':'offline derived from archived native channels; no new L2 RF calls'},indent=2))
print('block B complete',flush=True)
