import numpy as np, pandas as pd
R="/home/claude/myoungsunk/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001/dist_unc_m8"
EDG=np.array([0.,3.,6.,10.]); AX=10.0
def load():
    F=pd.read_csv(f"{R}/step3_sweep/dev_02/code/SWEEP_FEATURES.csv.gz")
    L=pd.read_csv(f"{R}/lut_replace/stage2/STAGE2_STATION_LABELS.csv.gz")
    assert np.allclose(F[["x_eval","y_eval","yaw_deg"]].values,L[["x_eval","y_eval","yaw_deg"]].values)
    D=pd.DataFrame(dict(x=F.x_eval,y=F.y_eval,yaw=F.yaw_deg,rho=F.rho,s=F.s_fp,e=L.e_s_s0id,a=L.a_ffd,eF=F.e_s,aF=F.a))
    D["h"]=D.s-D.e; D["psi"]=np.radians(D.yaw); D["side"]=np.where(D.x>=AX,1,-1)
    D["b"]=np.clip(np.searchsorted(EDG,D.rho,side="right")-1,0,2); D["col"]=(D.x*100).round().astype(int); D["row"]=(D.y*100).round().astype(int)
    return D
