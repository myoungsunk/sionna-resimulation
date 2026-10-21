import pandas as pd,numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
D=pd.read_csv('UM_POSE_TABLE.csv.gz')  # research/powerjoint-ds-usage-map-20261021 results;deg=180/np.pi
DS=[f'ds_{o:+d}' for o in [-8,-4,-2,-1,1,2,4,8]]
EXIST=['log_fp_power','abs_s_fp','early4','early8','early16','delay_rms_ns','peak_diff_ns','eta_fp_win80','s_diff4','s_diff8','s_diff16','tap_pol_var80','jones_diversity','freq_s_var','detector_s_span','detector_delay_span_ns']
H=lambda tr,te,c,y:HistGradientBoostingRegressor(max_iter=200,learning_rate=0.05,max_leaf_nodes=15,l2_regularization=1.0,random_state=0).fit(tr[c],tr[y]).predict(te[c])
parts=[]
for R in ['R2','R4','R5']:
    tr=D[D.route!=R];te=D[D.route==R].copy()
    for y in ['e_s','e_r']:
        te[f'{y}_EX']=H(tr,te,EXIST,y);te[f'{y}_EXDS']=H(tr,te,EXIST+DS,y)
    parts.append(te)
T=pd.concat(parts)
# improvements (positive = better)
T['h_P']=np.abs((T.e_s-T.mu_s)/T.g_psi)*deg;T['h_EX']=np.abs((T.e_s-T.e_s_EX)/T.g_psi)*deg;T['h_EXDS']=np.abs((T.e_s-T.e_s_EXDS)/T.g_psi)*deg
T['head_tot']=T.h_P-T.h_EXDS;T['head_ds']=T.h_EX-T.h_EXDS
T['rng_tot']=(np.abs(T.e_r-T.mu_r)-np.abs(T.e_r-T.e_r_EXDS))*100;T['rng_ds']=(np.abs(T.e_r-T.e_r_EX)-np.abs(T.e_r-T.e_r_EXDS))*100
T['absds1']=T['ds_+1'].abs();T['q']=T.groupby('case').absds1.transform(lambda v:pd.qcut(v.rank(method='first'),5,labels=False))
T['sign']=np.where(T['ds_+1']>0,'pos','neg');T['consistent']=(np.sign(T['ds_+1'])==np.sign(T['ds_+2']))&(np.sign(T['ds_+1'])==np.sign(T['ds_+4']))
valid=T.g_psi.abs()>=0.4
def summ(df,col,vmask=None):
    d=df if vmask is None else df[vmask]
    return pd.Series({'mean':d[col].mean(),'median':d[col].median(),'frac_better':(d[col]>0).mean(),'n':len(d)})
out={}
for col,vm,unit in [('head_tot',valid,'deg'),('head_ds',valid,'deg'),('rng_tot',None,'cm'),('rng_ds',None,'cm')]:
    rows=[]
    for k,g in T.groupby('q'):
        s=summ(g,col,None if vm is None else valid[g.index]);rows.append({'stratum':f'|ds+1| Q{k+1}','range':f"{g.absds1.min():.3f}-{g.absds1.max():.3f}",**s})
    for k,g in T.groupby('sign'):
        s=summ(g,col,None if vm is None else valid[g.index]);rows.append({'stratum':f'sign {k}','range':'',**s})
    for k,g in T.groupby('consistent'):
        s=summ(g,col,None if vm is None else valid[g.index]);rows.append({'stratum':f'offset-consistent={k}','range':'',**s})
    out[col]=pd.DataFrame(rows)
    # per-case trend: Q5 mean minus Q1 mean
    tr=[]
    for case,g in T.groupby('case'):
        gg=g if vm is None else g[valid[g.index]]
        tr.append(gg[gg.q==4][col].mean()-gg[gg.q==0][col].mean())
    out[col+'_casetrend']=tr
pd.set_option('display.width',220)
for col in ['head_tot','head_ds','rng_tot','rng_ds']:
    print(f'\n=== {col} (positive = improvement) ===');print(out[col].round(3).to_string(index=False))
    t=np.array(out[col+'_casetrend']);print('cases with Q5>Q1:',int((t>0).sum()),'/7  values',np.round(t,3))
# Q-level absolute errors for context
ctx=T.groupby('q').agg(abs_es=('e_s',lambda v:np.mean(np.abs(v))),abs_er_cm=('e_r',lambda v:np.mean(np.abs(v))*100),abs_dmp_s=('d_mp_s',lambda v:np.mean(np.abs(v))),log_fp=('log_fp_power','median'))
print('\ncontext by |ds+1| quintile:');print(ctx.round(3).to_string())
T[['case','pose_id','ds_+1','ds_+2','ds_+4','q','sign','consistent','head_tot','head_ds','rng_tot','rng_ds','g_psi']].to_csv('ds_pattern_pose.csv.gz',index=False,compression='gzip')
for col in ['head_tot','head_ds','rng_tot','rng_ds']: out[col].to_csv(f'ds_pattern_{col}.csv',index=False)
