# Does packet R_ss already contain the multipath variance?  eps_s = z_s - h(truth) - mu (D3, raw), e_s = multipath (CHAR-001)
import numpy as np, pandas as pd
I="/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001"
C="/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_001/out"
rows=[]
for r in ["R2","R4","R5"]:
    d3=np.load(f"{I}/continuation_d2_d3/d3/B_B0_{r}.npz"); tr=np.load(f"{I}/m7_final_model_stage1/attempt_02/replay/cells/B0/own/seed10/{r}/H3/trace.npz")
    assert np.array_equal(d3["pose_id"],tr["pose_id"])
    E=pd.read_csv(f"{C}/ERRORS_{r}_aB_m0.csv.gz").set_index("pose_id").loc[d3["pose_id"]]
    eps=d3["eps"][:,1]; e=E.e_s.to_numpy(); rho=np.hypot(E.x-10,E.y).to_numpy(); Rss=tr["R_ref"][:,1,1]; Rpk=Rss  # sigma_b only on range
    th=eps-e
    for lab,m in [("<3",rho<3),("3-6",(rho>=3)&(rho<6)),(">=6",rho>=6)]:
        rows.append(dict(route=r,rho=lab,n=int(m.sum()),Rpacket_ss=np.median(Rpk[m]),E_eps2=np.mean(eps[m]**2),E_e2_mp=np.mean(e[m]**2),
                         var_eps_minus_e=np.var(th[m]),corr_eps_e=np.corrcoef(eps[m],e[m])[0,1]))
D=pd.DataFrame(rows); pd.set_option("display.width",200)
print(D.to_string(index=False,float_format=lambda v:f"{v:.2e}"))
