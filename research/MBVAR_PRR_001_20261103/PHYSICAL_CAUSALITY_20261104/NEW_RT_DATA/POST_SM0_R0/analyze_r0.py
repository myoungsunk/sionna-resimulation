import csv, hashlib, io, json, sys, tarfile
from pathlib import Path
import numpy as np
root=Path(__file__).parent
def sha(x):return hashlib.sha256(x).hexdigest()
def save(name,rows):
 with (root/(name+'.csv')).open('w',newline='') as f:
  w=csv.DictWriter(f,rows[0]);w.writeheader();w.writerows(rows)
def doc(name,x):(root/(name+'.json')).write_text(json.dumps(x,indent=2))
def cir(h):return np.fft.ifft(h[:,:,0]*np.hanning(257)[:,None],n=1028,axis=0)*257
def observe(c):
 amp=abs(c);rx=int(amp.max(0).argmax());threshold=.3*amp[:,rx].max()
 return int(np.flatnonzero(amp[:,rx]>=threshold)[0]),rx,threshold
def s(v):
 power=abs(v)**2
 return (power[0]-power[1])/power.sum()
def norm(x):return float(np.linalg.norm(x))
data={};rays=[];fields=[];powers=[];taps=[];controls=[];hashes={};errors=[]
bundle=Path(sys.argv[1]);expected=dict(line.split('  ')[::-1] for line in (bundle/'BUNDLE_SHA256.txt').read_text().splitlines())
for name in ['previous_failure.tar.gz','rerun.tar.gz']:
 p=bundle/name;assert sha(p.read_bytes())==expected[name];hashes[name]=expected[name]
 with tarfile.open(p) as t:
  sums={k:h for h,k in (l.split('  ',1) for l in t.extractfile('OUTPUT_SHA256.txt').read().decode().splitlines())}
  for k,h in sums.items():assert sha(t.extractfile(k).read())==h
  if name.startswith('previous'):continue
  for k,h in sums.items():
   if not k.endswith('.npz'):continue
   arm,pose,rep=Path(k).parent.name.split('-');pose=int(pose);rep=int(rep[1:])
   m=json.load(t.extractfile(str(Path(k).parent.as_posix())+'/MANIFEST.json'))
   z=np.load(io.BytesIO(t.extractfile(k).read()));H=z['H_complex_rx_rx_tx'];freq=z['frequencies_hz'];off=z['offsets'];tau=z['path_delay_s'];a=z['path_coefficient'];groups={}
   assert np.array_equal(np.diff(off),z['path_counts']) and off[0]==0 and off[-1]==len(tau)
   for fi,f in enumerate(freq):
    lo,hi=off[fi:fi+2];ph=np.exp(np.complex64(-2j*np.pi*f)*tau[lo:hi]);ray=a[lo:hi]*ph[:,None,None]
    for j in range(lo,hi):
     ids=[int(i) for i in z['path_objects'][j] if i!=4294967295];lab=tuple(ids)
     assert all(i in (1,2) for i in ids) and z['path_valid'][j].all()
     g=groups.setdefault(lab,np.zeros_like(H));g[fi]+=ray[j-lo]
     row=dict(arm=arm,pose=pose,repeat=rep,bin=fi,path=j-lo,offset=lo,count=hi-lo,objects=str(ids),interactions=str(z['path_interactions'][j].tolist()),valid=True,delay_s=tau[j].item())
     for rx,tx in np.ndindex(2,2):
      v=a[j,rx,tx];row[f'a{rx}{tx}_re']=float(v.real);row[f'a{rx}{tx}_im']=float(v.imag)
     rays.append(row)
   errors.append(norm(sum(groups.values())-H)/norm(H))
   c=cir(H);tap,rx,th=observe(c)
   assert tap==m['observation']['fp_tap'] and abs(s(c[tap])-m['observation']['s'])<1e-10
   hashes[k]=dict(raw=h,H=sha(H.tobytes()));data[arm,pose,rep]=(H,c,tap,rx,th,groups,freq)
arms=['C00_DIRECT','C01_FLOOR','C10_PARALLEL_PLATE','C11_OBLIQUE_PLATE']
assert len(data)==32 and max(errors)<1e-6
for (arm,p,r),(H,c,t,rx,th,g,freq) in sorted(data.items()):
 assert np.array_equal(H,data[arm,p,1-r][0])
 if arm==arms[0]:continue
 base=arms[0] if arm==arms[1] else arms[1]
 B,b,u,_,_,gb,_=data[base,p,r];D=H-B
 for chain,h in gb.items():assert np.array_equal(g[chain],h)
 key=dict(arm=arm,base=base,pose=p,repeat=r)
 for fi,i,j in np.ndindex(D.shape):
  v=D[fi,i,j];v0=B[fi,i,j];v1=H[fi,i,j]
  fields.append(dict(**key,bin=fi,freq_Hz=freq[fi],rx=i,tx=j,delta_re=v.real,delta_im=v.imag,amplitude_change=abs(v1)-abs(v0),phase_delta_rad=np.angle(v1*v0.conjugate()),delta_power=abs(v1)**2-abs(v0)**2,interference=2*(v*v0.conjugate()).real))
 fixed=s(c[u])-s(b[u]);selection=s(c[t])-s(c[u]);total=s(c[t])-s(b[u])
 assert abs(total-fixed-selection)<1e-12
 taps.append(dict(**key,base_tap=u,new_tap=t,delta_r_m=(t-u)*299792458/(1028*1950000),fixed_delta_s=fixed,selection_delta_s=selection,total_delta_s=total,detector_rx=rx,threshold=th,amp_at_old=abs(c[u,rx]),amp_before_new=abs(c[t-1,rx]),amp_at_new=abs(c[t,rx])))
 for i in (0,1):
  v0=b[u,i];v=c[u,i]-v0;cross=2*(v0.conjugate()*v).real
  powers.append(dict(**key,tap=u,rx=i,group='all_added',added_power=abs(v)**2,cross_power=cross,delta_power=abs(c[u,i])**2-abs(v0)**2))
 for chain in g.keys()-gb.keys():
  part=cir(g[chain])[u]
  for i in (0,1):
   rest=c[u,i]-part[i]
   powers.append(dict(**key,tap=u,rx=i,group=str(chain),added_power=abs(part[i])**2,cross_power=2*(rest.conjugate()*part[i]).real,delta_power=abs(c[u,i])**2-abs(rest)**2))
 eq=np.array_equal(H,B)
 if arm!=arms[1]:assert eq==(p in (500,525) or (arm==arms[3] and p==194))
 controls.append(dict(**key,added_chains=str(sorted(g.keys()-gb.keys())),identical_H=eq,relative_H=norm(D)/norm(B),delta_tap=t-u,delta_s=total))
for name,rows in [('R0_RAY_INTERACTIONS',rays),('R0_PLATE_VS_FLOOR_H',fields),('R0_TAP_RESELECTION',taps),('R0_COHERENT_POWER_TERMS',powers),('R0_POS_NEG_CONTROLS',controls)]:save(name,rows)
save('R0_FP_FIXED_VS_RERUN',taps)
doc('R0_INPUT_HASHES',hashes);doc('R0_QA',dict(pr34='e2ff5b3e00202b941b21fdb0087acf8ff6bbdd82',native_calls=0,keys=len(data),max_ray_relative_L2=max(errors),repeat_identical=16))
for z in taps:
 if z['repeat']==0 and z['arm']!=arms[1]:print(z['pose'],z['arm'],z['base_tap'],z['new_tap'],z['fixed_delta_s'],z['selection_delta_s'],z['total_delta_s'])
