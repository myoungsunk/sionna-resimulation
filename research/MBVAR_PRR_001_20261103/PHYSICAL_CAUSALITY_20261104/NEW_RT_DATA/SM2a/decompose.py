import csv,hashlib,io,json,tarfile
from pathlib import Path
import numpy as np
root=Path(__file__).resolve().parent
def load(folder,prefixes):
 archive=folder/'evidence.tar.gz'
 assert hashlib.sha256(archive.read_bytes()).hexdigest()==(folder/'ARCHIVE_SHA256.txt').read_text().split()[0]
 files={}
 with tarfile.open(archive,'r|gz') as t:
  for m in t:
   if m.isfile() and any(m.name.startswith('out/'+p+'/') for p in prefixes):
    files[m.name[4:]]=t.extractfile(m).read()
 return files
def cir(h):return np.fft.ifft(h*np.hanning(257)[:,None],n=1028,axis=0)*257
def signed(v):
 power=abs(v)**2
 return float((power[0]-power[1])/power.sum())
def detect(c):
 mag=abs(c);branch=mag.max(axis=0).argmax()
 return int(np.flatnonzero(mag[:,branch]>=.3*mag[:,branch].max())[0])
def write(name,rows):
 with (root/name).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
new=[-35.7,0.,35.7,180.]
files=load(root,[f'yaw_{y}_{m}' for y in new for m in ['Full','LoS']])
files.update(load(root.parent/'SM0B/B1',['R4B_168_Full','R4B_168_LoS']))
summary=[];terms=[];cross=[];margins=[]
for yaw in new+[-31.700092]:
 base=f'yaw_{yaw}' if yaw in new else 'R4B_168'
 def get(mode,name):return files[f'{base}_{mode}/{name}']
 fmap=json.loads(get('Full','object_map.json'));groups={}
 for i in range(257):
  z=np.load(io.BytesIO(get('Full',f'bins/{i:03d}.npz')))
  n=len(z['tau']);o=z['objects'].reshape(-1,n);it=z['interactions'].reshape(-1,n)
  field=z['a'][:,0,:]*np.exp(np.complex64(-2j*np.pi*float(z['freq']))*z['tau'])
  for j in range(n):
   chain=tuple((fmap[str(int(v))],int(w)) for v,w in zip(o[:,j],it[:,j]) if v!=np.iinfo(o.dtype).max)
   groups.setdefault(chain,np.zeros((257,2),complex))[i]+=field[:,j]
 Fz=np.load(io.BytesIO(get('Full','RAW_H.npz')));Lz=np.load(io.BytesIO(get('LoS','RAW_H.npz')))
 F=cir(Fz['H'][:,:,0]);L=cir(Lz['H'][:,:,0]);cs={k:cir(v) for k,v in groups.items()}
 error=np.linalg.norm(sum(groups.values())-Fz['H'][:,:,0])/np.linalg.norm(Fz['H'][:,:,0])
 assert error<1e-6
 tf,tl=detect(F),detect(L)
 fixed=signed(F[tl])-signed(L[tl]);selection=signed(F[tf])-signed(F[tl])
 direct_error=np.linalg.norm(groups[()]-Lz['H'][:,:,0])/np.linalg.norm(Lz['H'][:,:,0])
 summary.append(dict(yaw=yaw,full_tap=tf,los_tap=tl,delta_s=signed(F[tf])-signed(L[tl]),
  fixed_los_tap_delta_s=fixed,selection_delta_s=selection,closure_residual=fixed+selection-(signed(F[tf])-signed(L[tl])),
  group_sum_rel_error=error,direct_vs_native_los_rel_error=direct_error,chains=len(groups)))
 for label,tap in [('los_tap',tl),('full_tap',tf)]:
  D=cs[()][tap];R=sum(v[tap] for k,v in cs.items() if k)
  for port in range(2):
   cross.append(dict(yaw=yaw,at=label,tap=tap,port=port,direct_power=abs(D[port])**2,reflection_power=abs(R[port])**2,
    direct_reflection_cross=2*(D[port].conjugate()*R[port]).real,total_power=abs(D[port]+R[port])**2))
  for k,v in cs.items():
   if not k:continue
   removed=F-v
   terms.append(dict(yaw=yaw,at=label,chain=str(k),tap=tap,group_power_plus=abs(v[tap,0])**2,
    group_power_minus=abs(v[tap,1])**2,leave_out_delta_s=signed(F[tap])-signed(removed[tap]),
    leave_out_detected_tap=detect(removed)))
 for mode,c in [('Full',F),('LoS',L)]:
  mag=abs(c);branch=int(mag.max(axis=0).argmax());threshold=.3*mag[:,branch].max()
  for tap in range(min(tf,tl)-1,max(tf,tl)+1):
   margins.append(dict(yaw=yaw,mode=mode,tap=tap,selected_branch=branch,amplitude=float(mag[tap,branch]),
    threshold=float(threshold),margin=float(mag[tap,branch]-threshold)))
write('MECHANISM_SPLIT.csv',summary);write('INTERFERENCE_POWER.csv',cross)
write('PATH_ABLATIONS.csv',terms);write('THRESHOLD_MARGINS.csv',margins)
print(json.dumps(summary,indent=2))
