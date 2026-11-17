import sys,numpy as np,math
sys.path.insert(0,"/home/claude/m8"); from common import *
import m8_replay as M
e=env(); worst={}
def upd(k,v): worst[k]=max(worst.get(k,0.),float(v))
for cond in ["B0","L2_GYRO_ARW"]:
  for r in ["R2","R4","R5"]:
    p=packet(cond,10,r); tb=table(r); c1=np.array(tb["c1"]); c0=np.array(tb["c0"]); ed=np.array(tb["edges"])
    for arm in ["F0","F1","F2"]:
        tr=M.replay_m8(p,e,arm,table=tb,sigma_b=PARAMS[r]["sigma_b"],condition=cond,**M.ARM_MODES[arm])
        b=np.clip(np.searchsorted(ed,tr["distance"],side="right")-1,0,2); a=tr["a"]
        Cv=c1[b]*a*a+c0[b]
        W_exp={"F0":Cv,"F1":0*Cv,"F2":0*Cv}[arm]; V_exp={"F0":0*Cv,"F1":Cv,"F2":c0[b]}[arm]
        # P4: replacement — no packet R_ss, no sigma_b^2 in s channel; range channel = packet R_rr
        upd("P4_W",np.max(np.abs(tr["W"]-W_exp))); upd("P4_V",np.max(np.abs(tr["V"]-V_exp)))
        upd("P4_Rss",np.max(np.abs(tr["Reff"][:,1,1]-(W_exp+V_exp+tr["causal"]))))
        upd("P4_Rrr",np.max(np.abs(tr["Reff"][:,0,0]-p["R"][:,0,0]))); upd("P4_Rrs",np.max(np.abs(tr["Reff"][:,0,1])))
        # P5: independent causal sum
        cs=np.zeros(len(tr["t"])); hist=[]
        for i in range(len(cs)):
            hist=[j for j in hist if tr["t"][i]-tr["t"][j]<=10.][-100:]
            cs[i]=sum(2*math.sqrt(V_exp[i]*V_exp[j])*math.exp(tr["hazard"][j]-tr["hazard"][i]) for j in hist)
            if tr["mask"][i] and arm!="F0": hist.append(i)
        upd("P5_causal",np.max(np.abs(cs-tr["causal"])))
        # NIS / mask reconstruction, rejected => posterior = prior
        upd("P5_mask",np.sum(tr["mask"]!=(tr["nis"]<=R7.GATE_2D)))
        rej=~tr["mask"]; upd("P5_reject_x",np.max(np.abs(tr["x"][rej]-tr["prior"][rej])) if rej.any() else 0)
        PP=tr["P_aug"] if arm=="F2" else tr["P"]
        upd("P5_sym",np.max(np.abs(PP-PP.swapaxes(1,2))))
        ev=np.linalg.eigvalsh(PP[:,:PP.shape[1],:PP.shape[1]] if arm=="F2" else PP); upd("P5_minEig_neg",max(0,-ev.min()))
        if arm=="F2":
            upd("P5_Peta_gt1",max(0,tr["P_eta"].max()-1)); 
            upd("P5_load",np.max(np.abs(tr["gm_load"]-np.sqrt(c1[b]))))
        upd("P_range_exposure_outside",np.mean(~tr["in_table_range"]))
for k,v in worst.items(): print(k,v)
ok=all(worst[k]<1e-10 for k in worst if k.startswith(("P4","P5")) and k!="P5_minEig_neg") and worst["P5_minEig_neg"]<1e-12
print("P4/P5","PASS" if ok else "CHECK")
