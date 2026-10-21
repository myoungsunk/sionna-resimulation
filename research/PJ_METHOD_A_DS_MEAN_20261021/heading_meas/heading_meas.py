import pandas as pd,numpy as np
from sklearn.linear_model import Ridge
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
D=pd.read_csv('UM_POSE_TABLE.csv.gz')  # from research/powerjoint-ds-usage-map-20261021 results
DS=[f'ds_{o:+d}' for o in [-8,-4,-2,-1,1,2,4,8]]
EXIST=['log_fp_power','abs_s_fp','early4','early8','early16','delay_rms_ns','peak_diff_ns','eta_fp_win80','s_diff4','s_diff8','s_diff16','tap_pol_var80','jones_diversity','freq_s_var','detector_s_span','detector_delay_span_ns']
parts=[]
for H in ['R2','R4','R5']:
    tr=D[D.route!=H];te=D[D.route==H].copy()
    t1=tr.dropna(subset=DS+['log_fp_power','e_s']);sc=StandardScaler().fit(t1[DS+['log_fp_power']]);m=Ridge(alpha=1).fit(sc.transform(t1[DS+['log_fp_power']]),t1.e_s)
    te['mu_LIN']=m.predict(sc.transform(te[DS+['log_fp_power']].fillna(0)))
    h=HistGradientBoostingRegressor(max_iter=200,learning_rate=0.05,max_leaf_nodes=15,l2_regularization=1.0,random_state=0).fit(tr[EXIST+DS],tr.e_s)
    te['mu_HGB']=h.predict(te[EXIST+DS]);parts.append(te)
T=pd.concat(parts);T['mu_POWER1']=T.mu_s;T['mu_NONE']=0.0
rng=np.random.default_rng(0);deg=180/np.pi;rows=[];boot=[]
for case,g in T.groupby('case'):
    G=g.g_psi.to_numpy();aG=np.abs(G);q50,q75=np.quantile(aG,[.5,.75])
    bx=np.floor(g.x_eval/0.4).astype(int);by=np.floor(g.y_eval/0.4).astype(int);bid=pd.factorize(pd.Series(bx.astype(str)+"_"+by.astype(str)).to_numpy())[0];nb=bid.max()+1
    eps={}
    for mdl in ['NONE','POWER1','LIN','HGB']:
        r=(g.e_s-g['mu_'+mdl]).to_numpy();e=r/G
        num=np.bincount(bid,G*r,nb);den=np.bincount(bid,G*G,nb);eb=num/np.where(den>0,den,np.nan);w=den
        eps[mdl]=(num,den)
        rows.append({'case':case,'model':mdl,'pkt_rms_deg_g50':np.sqrt(np.mean(e[aG>=q50]**2))*deg,'pkt_rms_deg_g75':np.sqrt(np.mean(e[aG>=q75]**2))*deg,
                     'pkt_median_abs_deg_g50':np.median(np.abs(e[aG>=q50]))*deg,'wls_offset_deg':np.sum(G*r)/np.sum(G*G)*deg,
                     'bin_wls_rms_deg':np.sqrt(np.nansum(w*eb**2)/np.nansum(w))*deg,'n_bins':nb})
    # paired fraction and block bootstrap of bin_wls_rms ratio vs POWER1
    eP=((g.e_s-g.mu_POWER1)/G).to_numpy()
    for mdl in ['LIN','HGB','NONE']:
        eA=((g.e_s-g['mu_'+mdl])/G).to_numpy();sel=aG>=q50
        frac=np.mean(np.abs(eA[sel])<np.abs(eP[sel]))
        numA,denA=eps[mdl];numP,denP=eps['POWER1'];rat=[]
        for _ in range(2000):
            idx=rng.integers(0,nb,nb);c=np.bincount(idx,minlength=nb)
            sA=np.nansum(c*numA**2/np.where(denA>0,denA,np.nan))/np.sum(c*denA);sP=np.nansum(c*numP**2/np.where(denP>0,denP,np.nan))/np.sum(c*denP)
            rat.append(np.sqrt(sA/sP))
        lo,hi=np.percentile(rat,[2.5,97.5])
        boot.append({'case':case,'model':mdl,'paired_frac_better_g50':frac,'bin_rms_ratio_vs_POWER1':np.sqrt((np.nansum(numA**2/np.where(denA>0,denA,np.nan))/denA.sum())/(np.nansum(numP**2/np.where(denP>0,denP,np.nan))/denP.sum())),'ci_lo':lo,'ci_hi':hi})
R=pd.DataFrame(rows);B=pd.DataFrame(boot)
pd.set_option('display.width',250)
print(R.pivot_table(index='case',columns='model',values=['bin_wls_rms_deg','pkt_rms_deg_g75','wls_offset_deg']).round(2).to_string())
print(R.pivot_table(index='case',columns='model',values=['pkt_median_abs_deg_g50']).round(2).to_string())
print(B.round(3).to_string(index=False))
R.to_csv('heading_meas_R.csv',index=False);B.to_csv('heading_meas_B.csv',index=False)
