import json,glob,sys,numpy as np,pandas as pd
sys.path.insert(0,"/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001/m7_final_model_stage1")
from m7_assess import clopper_pearson
ARMS=("H0","H1","H2","H3","F1","F2","F1S","F2S")
def load(cond,mode):
    G={}
    for f in sorted(glob.glob(f"/home/claude/m8/out_sweep/{cond}/{mode}/seed*/GROUP.json")):
        g=json.load(open(f)); G[g["seed"]]=g
    return G
def nomirror(sa):
    ok_i=all(not [x for x in grp["integrity_failures"] if x!="mirror_fail"] for grp in sa["groups"].values())
    return ok_i, ok_i and sa["A_seed"]
rows=[]; seedrows=[]
for cond,mode in [("B0","own"),("L2_GYRO_ARW","own"),("B0","fixed"),("L2_GYRO_ARW","fixed"),("L2_GYRO_ARW_Q_B0_STRESS","own")]:
    G=load(cond,mode)
    if not G: continue
    for arm in ARMS:
        I=[s for s,g in G.items() if g["seed_assessments"][arm]["I_seed"]]; A=[s for s,g in G.items() if g["seed_assessments"][arm]["A_seed"]]
        J=[s for s,g in G.items() if g["seed_assessments"][arm]["J_seed"]]
        mir=sum(g["seed_assessments"][arm]["mirror_fail"] for g in G.values()); mroutes=sum(g["seed_assessments"][arm]["mirror_routes"] for g in G.values())
        Jnm=[s for s,g in G.items() if nomirror(g["seed_assessments"][arm])[1]]
        n=len(G); lo,hi=clopper_pearson(len(J),n)
        early=[s for s in J if s<15]; late=[s for s in J if s>=15]
        rows.append(dict(cond=cond,mode=mode,arm=arm,n=n,N_I=len(I),N_A=len(A),N_J=len(J),J_CI=f"[{lo:.2f},{hi:.2f}]",
                         mirror_passages=mir,mirror_routes=mroutes,J_10_14=len(early),J_15_29=len(late),
                         N_J_noMirrorTerm=len(Jnm),
                         CONDITION_PASS=(mode=="own" and len(J)>=18 and mroutes==0 and n==20)))
        for s,g in G.items():
            sa=g["seed_assessments"][arm]
            seedrows.append(dict(cond=cond,mode=mode,arm=arm,seed=s,I=sa["I_seed"],A=sa["A_seed"],J=sa["J_seed"],mirror=sa["mirror_fail"],
                fail_I=";".join(f"{k}:{','.join(v['integrity_failures'])}" for k,v in sa["groups"].items() if v["integrity_failures"]),
                fail_A=";".join(f"{k}:{','.join(v['accuracy_failures'])}" for k,v in sa["groups"].items() if v["accuracy_failures"])))
T=pd.DataFrame(rows); S=pd.DataFrame(seedrows)
pd.set_option("display.width",250); pd.set_option("display.max_rows",200)
print(T.to_string(index=False))
T.to_csv("/home/claude/m8/DECISION_TABLE_SWEEP.csv",index=False); S.to_csv("/home/claude/m8/SEED_TABLE_SWEEP.csv",index=False)
