import sys,json,time,os,numpy as np
from multiprocessing import Pool
sys.path.insert(0,"/home/claude/m8")
OUT="/home/claude/m8/out"
COMPACT=("t","x","mask","nis","a","distance","Reff","nu","S","K","W","V","causal","tbin","b_g","eta","P_eta","b_theta","gm_load","s_infl","alpha")
def job(key):
    cond,mode,seed=key
    d=f"{OUT}/{cond}/{mode}/seed{seed}"
    if os.path.exists(d+"/GROUP.json"): return key,"reuse",0
    from common import packet,TRUTH,PARAMS,env,scorers,m7_kwargs,table,fixed_mask,R7
    import m8_replay as M, m8_score as S
    e=env(); ft,swb,bm=scorers(); t0=time.time()
    traces={};truth={};times={}
    for r in ("R2","R4","R5"):
        p=packet(cond,seed,r); truth[r]=TRUTH[r]["truth"]; times[r]=p["t"]; traces[r]={}
        for arm in ("H0","H1","H2","H3"):
            m="own" if (mode=="fixed" and arm in ("H0",)) else mode
            kw=m7_kwargs(arm,r,cond,"own")
            if m=="fixed": kw["fixed_mask"]=fixed_mask(r)
            traces[r][arm]=R7.replay(p,e,arm,**kw)
        for arm in ("F0","F1","F2"):
            kw=dict(table=table(r),sigma_b=PARAMS[r]["sigma_b"],condition=cond,**M.ARM_MODES[arm])
            if mode=="fixed": kw["fixed_mask"]=fixed_mask(r)
            traces[r][arm]=M.replay_m8(p,e,arm,**kw)
    g=S.score8(seed,cond,mode,traces,truth,times,from_trace=ft,scores_with_blocks=swb,branch_metrics=bm)
    os.makedirs(d,exist_ok=True)
    comp={}
    for r in traces:
        for arm in ("H2","H3","F0","F1","F2"):
            tr=traces[r][arm]
            for k in COMPACT:
                if k in tr: comp[f"{r}/{arm}/{k}"]=np.asarray(tr[k]).astype(np.float32) if np.asarray(tr[k]).dtype.kind=="f" else np.asarray(tr[k])
            comp[f"{r}/{arm}/P33"]=np.asarray(tr["P"])[:,:3,:3].astype(np.float32)
    np.savez_compressed(d+"/compact.npz",**comp)
    json.dump(g,open(d+"/GROUP.json","w"),default=lambda o: o.item() if hasattr(o,"item") else (o.tolist() if hasattr(o,"tolist") else str(o)))
    return key,"done",time.time()-t0
if __name__=="__main__":
    which=sys.argv[1]
    keys=[]
    if which in("main","all"): keys+=[(c,"own",s) for c in ("B0","L2_GYRO_ARW") for s in range(10,30)]
    if which in("fixed","all"): keys+=[(c,"fixed",s) for c in ("B0","L2_GYRO_ARW") for s in range(10,15)]
    if which in("stress","all"): keys+=[("L2_GYRO_ARW_Q_B0_STRESS","own",s) for s in range(10,30)]
    if which=="one": keys=[("B0","own",10)]
    with Pool(2) as pool:
        for key,st,dt in pool.imap_unordered(job,keys):
            print(json.dumps(dict(key=key,status=st,sec=round(dt,1))),flush=True)
