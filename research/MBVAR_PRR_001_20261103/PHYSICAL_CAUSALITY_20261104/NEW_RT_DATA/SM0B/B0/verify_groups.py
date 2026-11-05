import numpy as np, json,hashlib,csv
from pathlib import Path
p=Path('.')
lines=Path('SHA256SUMS.txt').read_text().splitlines()
for l in lines:
 h,k=l.split('  ',1);assert hashlib.sha256(Path(k).read_bytes()).hexdigest()==h
rows=[]
def cir(h):return np.fft.ifft(h*np.hanning(257)[:,None],n=1028,axis=0)*257
def s(v):a,b=abs(v)**2;return (a-b)/(a+b)
for pid in (194,234):
 d=Path(f'out/R4B_{pid}_Full');m=json.loads((d/'object_map.json').read_text());q=json.loads((d/'receipt.json').read_text());tap=q['tap'];groups={};counts={}
 for i in range(257):
  z=np.load(d/'bins'/f'{i:03d}.npz');t=z['tau'];n=len(t);o=z['objects'].reshape(-1,n);it=z['interactions'].reshape(-1,n);phase=np.exp(np.complex64(-2j*np.pi*float(z['freq']))*t);a=z['a'][:,0,:]*phase
  for j in range(n):
   ids=tuple((m[str(int(v))],int(w)) for v,w in zip(o[:,j],it[:,j]) if v!=np.iinfo(o.dtype).max)
   groups.setdefault(ids,np.zeros((257,2),complex))[i]+=a[:,j]
   counts[ids]=counts.get(ids,0)+1
 v={g:cir(h)[tap] for g,h in groups.items()};F=sum(v.values());L=v[()];Q=F-L
 for g,h in v.items():
  if not g:continue
  power=2*(L.conjugate()*h).real+(h.conjugate()*Q).real
  rows.append(dict(pose=pid,chain=str(g),path_instances=counts[g],tap=tap,power_plus=power[0],power_minus=power[1],delta_s_leave_out=s(F)-s(F-h)))
 assert np.allclose(sum(2*(L.conjugate()*h).real+(h.conjugate()*Q).real for g,h in v.items() if g),abs(F)**2-abs(L)**2,atol=1e-12)
with open('RAY_GROUP_COMPLEX_CONTRIBUTIONS.csv','w',newline='') as f:
 w=csv.DictWriter(f,rows[0]);w.writeheader();w.writerows(rows)
print(len(lines),len(rows));print(Path.cwd())
