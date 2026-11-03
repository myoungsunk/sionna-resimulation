import sys,types,pathlib,subprocess,numpy as np,json,math,hashlib,time
sys.dont_write_bytecode=True
W="D:/codex/MBVAR_PRR_001_20261103";rev="7e2855314de867e0481f8eb5ed1a07c48710f364"
E=pathlib.Path("D:/SLAM_bot/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/execution_33e9849")
P=E/"p2";cache=pathlib.Path("D:/codex/MBVAR_PRR_001_20261103_inputs")
src=P/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src"
sys.path[:0]=[str(src),str(P/"research/FFD_P0P3_20261016"),str(P/"research/EKF4_RANGE_S_STAGED_20261014")]
def text(path):return subprocess.check_output(["git","-C",W,"show",rev+":"+path])
def module(name,path):
 m=types.ModuleType(name);m.__file__=str(pathlib.Path(W)/path);sys.modules[name]=m
 exec(compile(text(path),m.__file__,"exec"),m.__dict__);return m
core=module("core","research/EKF4_RANGE_S_STAGED_20261014/core.py")
import source_model
from qclean_uwb.drivesim import pattern_apply as PA
banks=[]
for name,expected in [("LP_plus45_bank.npz","b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b"),("LP_minus45_bank.npz","39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9")]:
 path=E/name;assert hashlib.sha256(path.read_bytes()).hexdigest()==expected
 with np.load(path,allow_pickle=False) as a:banks.append(PA.Bank(dict(a)))
model=source_model.SourceFFD(banks=banks)
common=types.ModuleType("common");common.REPO=P;common.base_model=lambda:model;sys.modules["common"]=common
pb=module("exp_pb","research/DS_MASK_CAUSAL_X1_X2_20261026/pol_bias_model/exp_pb.py")
ctl=module("ctl_core_independent","research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_control_correction_20261029/ctl_core.py");ctl._MODEL=model
case="R4_aB_m0";spec=dict(anchor=(10.,0.,2.65),robot_z_m=.45,mount_deg=0.)
zref=np.load(cache/"research/DS_MASK_CAUSAL_X1_X2_20261026/why_ds_worse/CONTROL"/(case+"_B0.npz"),allow_pickle=False)
b=list(zref["names"]).index("OFF_BB");m=list(zref["names"]).index("OFF_MB")
t=zref["t_s"];truth=zref["truth_scoring_only"];ds,gy,dt,x0=pb.build_controls(t,truth[:,:3],"B0",0)
z=zref["nu"][:,b]+zref["h"][:,b]+zref["mu"][:,b];R=zref["R"][:,b];mu=zref["mu"][:,m]
acc=pb.gated_mask(z,zref["mu"][:,b],R,ds,gy,dt,np.r_[x0,0.],zref["Pprior"][0,b],spec,model)
D=dict(t=t,z=z,R=R,R0=R,mu=dict(MB=mu),ds=ds,gy=gy,dt=dt,x0=np.r_[x0,0.],P0=zref["Pprior"][0,b],anchor=np.array([10.,0.]),spec=spec,acc=acc,fin=np.isfinite(z).all(1))
Xpb,Ppb,_,_=pb.run(D,mu,dict(mode="var"),model)
Xct,Pct,L=ctl.run(D,"MB",ctl.R_var)
x=D["x0"].copy();p=D["P0"].copy();Xs=[];Ps=[]
for k in range(len(t)):
 sg=np.interp(np.linalg.norm(x[:2]-D["anchor"]),[0.,1.5,3.,6.,10.],[.011,.020,.050,.120,.240])
 if k:
  angle=float(gy[k]-x[3]*dt[k]);a=angle/2
  if abs(angle)<1e-4:
   c=1-angle**2/24+angle**4/1920-angle**6/322560
   dc=-angle/12+angle**3/480-angle**5/53760
  else:c=math.sin(a)/a;dc=(a*math.cos(a)-math.sin(a))/(2*a*a)
  phi=x[2]+a;u=np.array([math.cos(phi),math.sin(phi)]);v=np.array([-u[1],u[0]])
  delta=ds[k]*c*u;der=ds[k]*(dc*u+c*v/2)
  F=np.eye(4);F[:2,2]=[-delta[1],delta[0]];F[:2,3]=-dt[k]*der;F[2,3]=-dt[k]
  G=np.zeros((4,3));G[:2,0]=c*u;G[:2,1]=der;G[2,1]=1.;G[3,2]=1.
  x[:2]+=delta;x[2]=(x[2]+angle+np.pi)%(2*np.pi)-np.pi
  p=F@p@F.T+G@np.diag([2e-5*abs(ds[k]),math.radians(.015)**2*dt[k],0.])@G.T;p=(p+p.T)/2
 if acc[k]:
  h,H=model.batch(x[None],spec);h=h[0];H=H[0]
  rr=R[k].copy();rr[1,1]+=sg**2
  s=H@p@H.T+rr;s=(s+s.T)/2
  K=np.linalg.solve(s,H@p).T
  x=x+K@(z[k]-h-mu[k]);x[2]=(x[2]+np.pi)%(2*np.pi)-np.pi
  A=np.eye(4)-K@H;p=A@p@A.T+K@rr@K.T;p=(p+p.T)/2
 Xs.append(x.copy());Ps.append(p.copy())
Xs=np.array(Xs);Ps=np.array(Ps)
out=dict(case=case,bias="B0",seed=0,steps=len(t),gate_mismatch_vs_control=int(np.sum(acc!=zref["acc"][:,b])),canonical_pb_vs_ctl_state_max=float(abs(Xpb-Xct).max()),canonical_pb_vs_ctl_P_max=float(abs(Ppb-Pct).max()),independent_vs_pb_state_max=float(abs(Xs-Xpb).max()),independent_vs_pb_P_max=float(abs(Ps-Ppb).max()),state_allclose=bool(np.allclose(Xs,Xpb,atol=1e-10,rtol=1e-10)),P_allclose=bool(np.allclose(Ps,Ppb,atol=1e-10,rtol=1e-10)),shared_components=["SourceFFD observation/Jacobian","canonical sensor generator for supplied controls","raw mu/R/z"],independent_components=["motion prediction equations","covariance propagation","Joseph update and baseline assembly"])
print(json.dumps(out,indent=2))
