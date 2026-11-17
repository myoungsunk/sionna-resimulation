import sys,json,time,numpy as np
sys.path.insert(0,"/home/claude/m8"); from common import *
import m7_score
ft,swb,bm=scorers(); e=env()
def group(cond,mode,seed):
    traces={};truth={};times={}
    for r in ("R2","R4","R5"):
        p=packet(cond,seed,r); truth[r]=TRUTH[r]["truth"]; times[r]=p["t"]; traces[r]={}
        for arm in R7.ARMS:
            m="own" if (mode=="fixed" and arm=="H0") else mode
            traces[r][arm]=R7.replay(p,e,arm,**m7_kwargs(arm,r,cond,m))
    return m7_score.score_comparison(seed,cond,mode,traces,truth,times,from_trace=ft,scores_with_blocks=swb,branch_metrics=bm)
t0=time.time(); g=group("B0","own",10); print(f"{time.time()-t0:.0f}s")
ref=json.load(open(A2/"scoring/groups/B0/own/seed10/GROUP.json"))
md=0
for r in ("R2","R4","R5","pooled"):
    for arm in R7.ARMS:
        for k,v in ref["scores"]["point"][r][arm].items():
            if isinstance(v,(int,float)): md=max(md,abs(v-g["scores"]["point"][r][arm][k]))
print("point max diff",md)
from cmp_assess import compare
import pickle; pickle.dump(g,open("/tmp/m8_g_b0_10.pkl","wb"))
for arm in R7.ARMS:
    a=g["seed_assessments"][arm]; b=ref["seed_assessments"][arm]
    print(arm,"I/A/J",a["I_seed"],a["A_seed"],a["J_seed"],"| M7",b["I_seed"],b["A_seed"],b["J_seed"],"| mismatches",compare(a,b)[:3])
