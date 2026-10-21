import pandas as pd,numpy as np
from sklearn.linear_model import Ridge
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
D=pd.read_csv('UM_POSE_TABLE.csv.gz')  # research/powerjoint-ds-usage-map-20261021 results
DS=[f'ds_{o:+d}' for o in [-8,-4,-2,-1,1,2,4,8]]
EXIST=['log_fp_power','abs_s_fp','early4','early8','early16','delay_rms_ns','peak_diff_ns','eta_fp_win80','s_diff4','s_diff8','s_diff16','tap_pol_var80','jones_diversity','freq_s_var','detector_s_span','detector_delay_span_ns']
def ridge(tr,te,cols,y):
    t=tr.dropna(subset=cols+[y]);sc=StandardScaler().fit(t[cols]);m=Ridge(alpha=1).fit(sc.transform(t[cols]),t[y]);return m.predict(sc.transform(te[cols].fillna(0)))
def hgb(tr,te,cols,y):
    return HistGradientBoostingRegressor(max_iter=200,learning_rate=0.05,max_leaf_nodes=15,l2_regularization=1.0,random_state=0).fit(tr[cols],tr[y]).predict(te[cols])
parts=[]
for H in ['R2','R4','R5']:
    tr=D[D.route!=H];te=D[D.route==H].copy()
    for y in ['e_r','d_mp_r']:
        te[f'{y}|DS_LIN']=ridge(tr,te,DS,y);te[f'{y}|EXIST_LIN']=ridge(tr,te,EXIST,y);te[f'{y}|EXIST_DS_LIN']=ridge(tr,te,EXIST+DS,y)
        te[f'{y}|EXIST_HGB']=hgb(tr,te,EXIST,y);te[f'{y}|EXIST_DS_HGB']=hgb(tr,te,EXIST+DS,y)
    te['e_r|POWER1']=te.mu_r;te['e_r|NONE']=0.0;te['d_mp_r|NONE']=0.0
    parts.append(te)
T=pd.concat(parts);rng=np.random.default_rng(2);rows=[];ci=[]
for case,g in T.groupby('case'):
    bx=np.floor(g.x_eval/0.4).astype(int);by=np.floor(g.y_eval/0.4).astype(int);bid=pd.factorize(pd.Series(bx.astype(str)+'_'+by.astype(str)).to_numpy())[0];nb=bid.max()+1
    bx1=np.floor(g.x_eval/1.0).astype(int);b1=pd.factorize(pd.Series(bx1.astype(str)).to_numpy())[0]
    for y,models in [('e_r',['NONE','POWER1','DS_LIN','EXIST_LIN','EXIST_DS_LIN','EXIST_HGB','EXIST_DS_HGB']),('d_mp_r',['NONE','DS_LIN','EXIST_LIN','EXIST_DS_LIN','EXIST_HGB','EXIST_DS_HGB'])]:
        res={}
        for m in models:
            r=(g[y]-g[f'{y}|{m}']).to_numpy();res[m]=r
            lf=pd.Series(r).groupby(b1).mean()
            rows.append({'case':case,'label':y,'model':m,'rms_cm':np.sqrt(np.mean(r**2))*100,'median_abs_cm':np.median(np.abs(r))*100,'mean_cm':r.mean()*100,'win1m_rms_cm':np.sqrt(np.mean(lf**2))*100})
        sse={m:np.bincount(bid,res[m]**2,nb) for m in models};cnt=np.bincount(bid,minlength=nb)
        for a,b in [('EXIST_DS_LIN','EXIST_LIN'),('EXIST_DS_HGB','EXIST_HGB'),('DS_LIN','POWER1' if y=='e_r' else 'NONE'),('EXIST_DS_HGB','POWER1' if y=='e_r' else 'NONE')]:
            full=np.sqrt(sse[a].sum()/sse[b].sum());bs=[]
            for _ in range(2000):
                idx=rng.integers(0,nb,nb);c=np.bincount(idx,minlength=nb);bs.append(np.sqrt((c*sse[a]).sum()/(c*sse[b]).sum()))
            ci.append({'case':case,'label':y,'compare':f'{a} / {b}','rms_ratio':full,'ci_lo':np.percentile(bs,2.5),'ci_hi':np.percentile(bs,97.5)})
R=pd.DataFrame(rows);C=pd.DataFrame(ci);pd.set_option('display.width',250)
print(R[R.label=='e_r'].pivot_table(index='case',columns='model',values='rms_cm')[['NONE','POWER1','DS_LIN','EXIST_LIN','EXIST_DS_LIN','EXIST_HGB','EXIST_DS_HGB']].round(2).to_string())
print(R[R.label=='e_r'].pivot_table(index='case',columns='model',values='win1m_rms_cm')[['NONE','POWER1','DS_LIN','EXIST_LIN','EXIST_DS_LIN','EXIST_HGB','EXIST_DS_HGB']].round(2).to_string())
print(R[R.label=='e_r'].pivot_table(index='case',columns='model',values='median_abs_cm')[['POWER1','EXIST_LIN','EXIST_DS_LIN','EXIST_HGB','EXIST_DS_HGB']].round(2).to_string())
print(C.round(3).to_string(index=False))
R.to_csv('range_meas_R.csv',index=False);C.to_csv('range_meas_CI.csv',index=False)
