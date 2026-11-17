import sys, json, numpy as np
SRC="/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/MOUNT45_VALIDATION_20261116/frozen_model003_src"
sys.path.insert(0, SRC)
from qclean_uwb.drivesim import hs_lut as model, observation as obs, pattern_apply as pat
U="/mnt/user-data/uploads/blockc_centerline_sweep_20261117/artifacts/BLOCK_C_CENTERLINE_SWEEP_20261117T0956Z_OT9sPHzh/results"
banks=[pat.Bank(dict(np.load(f"/home/claude/rel/{n}",allow_pickle=False))) for n in ("LP_plus45_bank.npz","LP_minus45_bank.npz")]
S=json.load(open(U+"/poses/BLOCKC_B/SAMPLES.json"))
# unique pose rows (pose_id order = H first axis)
P={}
for r in S: P.setdefault(r["pose_id"], r)
ids=np.array(sorted(P)); assert np.array_equal(ids, np.arange(len(ids)))
x=np.array([P[i]["x"] for i in ids]); y=np.array([P[i]["y"] for i in ids]); yaw=np.array([P[i]["yaw_body_deg"] for i in ids],float)
st=np.array([P[i]["station_id"] for i in ids])
A=np.array([10.,0.,2.65]); zr=0.45
delta=np.c_[x,y,np.full(len(x),zr)]-A; d=np.linalg.norm(delta,axis=1)
Hf=np.load(U+"/H/BLOCKC_B/H_full.npy",mmap_mode="r"); Hl=np.load(U+"/H/BLOCKC_B/H_LoS.npy",mmap_mode="r")
def o30(c):
    m=np.abs(c); b=m.max(axis=1).argmax(axis=1); s=np.take_along_axis(m,b[:,None,None],axis=2)[:,:,0]; pk=s.max(axis=1)
    return (s>=0.3*pk[:,None]).argmax(axis=1)
def s_at(c,i):
    p=np.abs(c[np.arange(len(c)),i,:])**2; return (p[:,0]-p[:,1])/p.sum(axis=1)
sf=[];sl=[];ss=[];il_=[];if_=[]
for a in range(0,len(ids),256):
    cf=obs.cir_batch(np.asarray(Hf[a:a+256])[...,0]); cl=obs.cir_batch(np.asarray(Hl[a:a+256])[...,0])
    il,iff=o30(cl),o30(cf); sl.append(s_at(cl,il)); sf.append(s_at(cf,iff)); ss.append(s_at(cf,il)); il_.append(il); if_.append(iff)
sf,sl,ss,il,iff=map(np.concatenate,(sf,sl,ss,il_,if_))
es=sf-sl; esame=ss-sl; dtap=iff-il
# sensitivity a = ds_LoS/dpsi (per rad) via frozen FFD model
step=0.5; g=np.empty(len(ids)); s0=np.empty(len(ids)); dirn=delta/d[:,None]
for a in range(0,len(ids),256):
    ii=range(a,min(a+256,len(ids)))
    hs=[np.stack([model.los_h(banks,dirn[i],float(yaw[i]+dy),float(d[i])) for i in ii]) for dy in (-step,0.,step)]
    cs=[obs.cir_batch(h[...,0]) for h in hs]; idx=o30(cs[1]); sm,sc,sp=(s_at(c,idx) for c in cs)
    g[a:a+len(ii)]=(sp-sm)/(2*step)*180/np.pi; s0[a:a+len(ii)]=sc
print("LoS parity p90 |s_syn - s_LoS| =", np.quantile(np.abs(s0-sl),.9))
np.savez("/home/claude/diag/station_sweep_errors.npz",x=x,y=y,yaw=yaw,st=st,d=d,es=es,esame=esame,dtap=dtap,a=g,s_los=sl,s_full=sf)
