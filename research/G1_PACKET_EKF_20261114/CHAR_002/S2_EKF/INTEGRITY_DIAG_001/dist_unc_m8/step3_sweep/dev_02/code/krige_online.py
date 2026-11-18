"""Online kriging of the polarization mean from station-sweep samples at the PRIOR pose (no truth)."""
import numpy as np, pandas as pd, json
SW=pd.read_csv("/home/claude/m8cal/SWEEP_FEATURES.csv.gz"); SW["psi"]=np.radians(SW.yaw_deg)
EDG=np.array([0,3,6,10]); SW["b"]=np.clip(np.searchsorted(EDG,SW.rho,side="right")-1,0,2)
P=json.load(open("/home/claude/m8cal/KRIGE_PARAMS.json"))
def wrap(a): return (a+np.pi)%(2*np.pi)-np.pi
BINS={}
for b in range(3):
    d=SW[SW.b==b]; BINS[b]=dict(X=d[["x_eval","y_eval","psi"]].to_numpy(),y=d.e_s.to_numpy(),mu0=float(d.e_s.mean()),prm=P[f"e_s|{b}"]["params"])
def krige_s(x,y,psi,rho,maxn=150):
    b=int(np.clip(np.searchsorted(EDG,rho,side="right")-1,0,2)); B=BINS[b]; lx,ly,lp,nug=B["prm"]; X=B["X"]
    d=np.abs(X[:,0]-x)/lx+np.abs(X[:,1]-y)/ly+np.abs(wrap(X[:,2]-psi))/lp
    idx=np.argpartition(d,maxn)[:maxn]; Xi=X[idx]
    K=np.exp(-(np.abs(Xi[:,0,None]-Xi[None,:,0])/lx+np.abs(Xi[:,1,None]-Xi[None,:,1])/ly+np.abs(wrap(Xi[:,2,None]-Xi[None,:,2]))/lp))
    w=np.linalg.solve((1-nug)*K+nug*np.eye(len(idx)),(1-nug)*np.exp(-d[idx]))
    return B["mu0"]+w@(B["y"][idx]-B["mu0"])
def make_fn(far_mu_s, near_limit=6.0):
    def fn(nav,distance,i):
        if distance<near_limit: return float(krige_s(nav[0],nav[1],nav[2],distance))
        return float(far_mu_s[i])
    return fn
