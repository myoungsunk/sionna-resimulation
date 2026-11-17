import sys,numpy as np,json
sys.path.insert(0,"/home/claude/m8"); from common import *
import m8_replay as M
e=env(); out={}
K=["x","P","prior","Pprior","H","K","Reff","nu","S"]
def diff(a,b,keys=K): return max(float(np.max(np.abs(np.asarray(a[k],float)-np.asarray(b[k],float)))) for k in keys)
worst=0
for cond in ["B0","L2_GYRO_ARW"]:
  for seed in [10,15]:
    for r in ["R2","R4","R5"]:
      p=packet(cond,seed,r); P_=PARAMS[r]; tb=table(r)
      base=dict(table=tb,sigma_b=P_["sigma_b"],condition=cond)
      ref={arm:R7.replay(p,e,arm,**m7_kwargs(arm,r,cond)) for arm in ("H2","H3","H5")}
      d2=diff(M.replay_m8(p,e,"H2",white="packet",**base),ref["H2"])
      d5=diff(M.replay_m8(p,e,"H5",white="packet",corr="q_table",q_table=P_["q_table"],**base),ref["H5"])
      t3=M.replay_m8(p,e,"H3",white="packet",corr="q_table",q_table=P_["q_table"],gm=("const",P_["sigma_rad"]),**base)
      d3=diff(t3,ref["H3"]); db=float(np.max(np.abs(t3["b_theta"]-ref["H3"]["b_theta"])))
      m_ok=all(np.array_equal(M.replay_m8(p,e,a,white="packet",**({} if a=="H2" else dict(corr="q_table",q_table=P_["q_table"])),**base)["mask"],ref[a]["mask"]) for a in ("H2","H5"))
      worst=max(worst,d2,d5,d3,db)
      print(cond,seed,r,f"H2 {d2:.1e} H5 {d5:.1e} H3 {d3:.1e} b_theta {db:.1e} masks {m_ok and np.array_equal(t3['mask'],ref['H3']['mask'])}")
print("P3 worst",worst,"PASS" if worst<1e-10 else "FAIL")
