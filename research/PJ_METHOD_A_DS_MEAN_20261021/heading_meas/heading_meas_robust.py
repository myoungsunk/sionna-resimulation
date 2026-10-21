import pandas as pd,numpy as np
from sklearn.linear_model import Ridge
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
D=pd.read_csv('UM_POSE_TABLE.csv.gz');deg=180/np.pi
DS=[f'ds_{o:+d}' for o in [-8,-4,-2,-1,1,2,4,8]]
EXIST=['log_fp_power','abs_s_fp','early4','early8','early16','delay_rms_ns','peak_diff_ns','eta_fp_win80','s_diff4','s_diff8','s_diff16','tap_pol_var80','jones_diversity','freq_s_var','detector_s_span','detector_delay_span_ns']
parts=[]
for H in ['R2','R4','R5']:
    tr=D[D.route!=H];te=D[D.route==H].copy()
    t1=tr.dropna(subset=DS+['log_fp_power','e_s']);sc=StandardScaler().fit(t1[DS+['log_fp_power']]);m=Ridge(alpha=1).fit(sc.transform(t1[DS+['log_fp_power']]),t1.e_s)
    te['mu_LIN']=m.predict(sc.transform(te[DS+['log_fp_power']].fillna(0)))
    te['mu_HGB']=HistGradientBoostingRegressor(max_iter=200,learning_rate=0.05,max_leaf_nodes=15,l2_regularization=1.0,random_state=0).fit(tr[EXIST+DS],tr.e_s).predict(te[EXIST+DS])
    parts.append(te)
T=pd.concat(parts);T['mu_POWER1']=T.mu_s
rng=np.random.default_rng(1);out=[]
for case,g in T.groupby('case'):
    bx=np.floor(g.x_eval/0.4).astype(int);by=np.floor(g.y_eval/0.4).astype(int)
    g=g.assign(bid=pd.factorize(pd.Series(bx.astype(str)+'_'+by.astype(str)).to_numpy())[0])
    # bin validity from g only: all |g|>=0.4/rad and constant sign
    st=g.groupby('bid').g_psi.agg(lambda v:(np.abs(v).min()>=0.4) and (np.sign(v).nunique()==1))
    valid=st[st].index.to_numpy(); gv=g[g.bid.isin(valid)]
    res={}
    for mdl in ['POWER1','LIN','HGB']:
        r=gv.e_s-gv['mu_'+mdl]; G=gv.g_psi
        b=pd.DataFrame({'bid':gv.bid,'num':G*r,'den':G*G}).groupby('bid').sum(); eb=(b.num/b.den)*deg
        pk=(r/G*deg).abs()
        res[mdl]=(eb,b.den,pk,gv.bid.to_numpy())
    P=res['POWER1']
    for mdl in ['LIN','HGB']:
        A=res[mdl]; bins=P[0].index.to_numpy(); nb=len(bins)
        def stats(idx):
            sel=bins[idx]; ep=P[0].loc[sel]; ea=A[0].loc[sel]; wp=P[1].loc[sel]
            rms_ratio=np.sqrt(np.sum(wp*ea**2)/np.sum(wp*ep**2))
            med_ratio=np.median(np.abs(ea))/np.median(np.abs(ep))
            return rms_ratio,med_ratio
        full=stats(np.arange(nb)); bs=np.array([stats(rng.integers(0,nb,nb)) for _ in range(2000)])
        out.append({'case':case,'model':mdl,'valid_bins':nb,'valid_pkt_frac':len(gv)/len(g),
                    'POWER1_bin_rms_deg':np.sqrt(np.sum(P[1]*P[0]**2)/np.sum(P[1])),'model_bin_rms_deg':np.sqrt(np.sum(A[1]*A[0]**2)/np.sum(A[1])),
                    'POWER1_bin_median_deg':np.median(np.abs(P[0])),'model_bin_median_deg':np.median(np.abs(A[0])),
                    'POWER1_pkt_median_deg':np.median(P[2]),'model_pkt_median_deg':np.median(A[2]),
                    'rms_ratio':full[0],'rms_ci':f"[{np.percentile(bs[:,0],2.5):.2f}, {np.percentile(bs[:,0],97.5):.2f}]",
                    'median_ratio':full[1],'median_ci':f"[{np.percentile(bs[:,1],2.5):.2f}, {np.percentile(bs[:,1],97.5):.2f}]",
                    'max_abs_bin_err_POWER1':np.abs(P[0]).max(),'max_abs_bin_err_model':np.abs(A[0]).max()})
O=pd.DataFrame(out);pd.set_option('display.width',260);pd.set_option('display.max_columns',30)
print(O.round(2).to_string(index=False));O.to_csv('heading_meas_robust.csv',index=False)
