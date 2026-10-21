import numpy as np, pandas as pd, warnings
from sklearn.linear_model import Ridge
warnings.filterwarnings('ignore')
PK=pd.read_csv('results_hpath/HP_PACKETS.csv.gz'); OFFS=[-8,-4,-2,-1,1,2,4,8]
new={}
for o in OFFS:
    new[f'dF_{o:+d}']=PK[f'sF_{o:+d}']-PK['sF_+0']; new[f'dM_{o:+d}']=PK[f'sMGT_{o:+d}']-PK['sMGT_+0']
for o in OFFS: new[f'dRes_{o:+d}']=new[f'dF_{o:+d}']-new[f'dM_{o:+d}']
PK=pd.concat([PK,pd.DataFrame(new)],axis=1)
DF=[f'dF_{o:+d}' for o in OFFS]; DR=[f'dRes_{o:+d}' for o in OFFS]
def ho(df,cols):
    p=np.full(len(df),np.nan)
    for r in df.route.unique():
        tr=(df.route!=r).to_numpy(); m=Ridge(alpha=1e-3).fit(df.loc[tr,cols].fillna(0),df.e_s[tr]); p[~tr]=m.predict(df.loc[~tr,cols].fillna(0))
    return p
PK['pF']=ho(PK,DF); PK['pR']=ho(PK,DR)
r2=lambda y,p:1-np.sum((y-p)**2)/np.sum((y-y.mean())**2)
fs=PK.fp_shift_tap
PK['st']=np.select([(fs==0)&(PK.mlr_fp_full_db<-15),(fs==0),fs.abs()==1,fs.abs()<=3],['A_clean','B_overlap_fp0','C_fp_pm1','D_fp_2to3'],'E_fp_ge4')
PK['flat']=PK[['dRes_+1','dRes_+2','dRes_+4']].abs().max(axis=1)<0.05
tot=np.sum(PK.e_s**2); q80=PK.e_s.abs().quantile(.8)
def summ(g):
    big=g[g.e_s.abs()>=q80]
    return pd.Series({'n':len(g),'share_n':len(g)/len(PK),'share_es2':np.sum(g.e_s**2)/tot,'rms_es':np.sqrt(np.mean(g.e_s**2)),'mlr_fp_db_med':g.mlr_fp_full_db.median(),
      'R2_dF':r2(g.e_s,g.pF),'R2_dRes':r2(g.e_s,g.pR),'n_big':len(big),'big_flat_frac':big.flat.mean() if len(big) else np.nan,'big_flat_es2_share_of_total':np.sum(big[big.flat].e_s**2)/tot})
S=PK.groupby('st').apply(summ); print(S.round(3).to_string())
print('ALL',summ(PK).round(3).to_dict())
B=PK[PK.st=='B_overlap_fp0'].copy(); B['dbin']=pd.cut(B.mp_peak_excess_tap,[-50,1,2,3,8,50],labels=['<=1','2','3','4-8','>8'])
print(B.groupby('dbin').apply(summ).round(3).to_string())
B['mbin']=pd.cut(B.mlr_fp_full_db,[-15,-9,-5,0,50]); print(B.groupby('mbin').apply(summ).round(3).to_string())
S.to_csv('results_hpath/HA_STRATA_FP.csv')
print(PK.groupby('case').apply(lambda g: pd.Series({k: np.sum(g[g.st==k].e_s**2)/np.sum(g.e_s**2) for k in sorted(PK.st.unique())})).round(2).to_string())
