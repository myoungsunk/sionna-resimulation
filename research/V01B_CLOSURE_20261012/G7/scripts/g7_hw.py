import sys,os,json
sys.path.insert(0,'g7/job_pub');import numpy as np,pandas as pd
import simulate_g7 as S
pub=pd.read_csv('/home/user/sionna-resimulation/results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/OUTPUT/09_V2_main.csv')
tasks=[('R2_aA_m0',0,s,'D','stochastic','unknown','main') for s in range(20)]+[('R5_aB_m0',1,s,'D','stochastic','unknown','main') for s in range(20)]
rows=[S.single(t) for t in tasks];n=pd.DataFrame(rows)
bad=0;mx=0
for r in rows:
    p=pub[(pub.case==r['case'])&(pub.drift==r['drift'])&(pub.seed==r['seed'])&(pub.arm==r['arm'])].iloc[0]
    d=max(abs(r[c]-p[c]) for c in ['heading_rmse_deg','pos_rmse_m','nees_mean']);mx=max(mx,d);bad+=d>1e-9
print(os.environ.get('OPENBLAS_CORETYPE','default'),'differing >1e-9:',bad,'of',len(rows),'max diff %.2e'%mx)
