from pathlib import Path
import numpy as np,pandas as pd,json
ROOT=Path(__file__).resolve().parent
LABELS=['0-.5','.5-1','1-1.5','1.5-2','2-3','3-4','4-6','6-8','8-inf'];PRIMARY=['R2_aA_m45','R4_aA_m0','R4_aB_m0'];KEY=['case','bias','arm']
def rms(s):return float(np.sqrt(np.mean(np.asarray(s)**2))) if len(s) else np.nan
def med(s):return float(s.median()) if s.notna().sum()>=30 else np.nan
def percentile(s,q):return float(s.quantile(q)) if s.notna().sum()>=30 else np.nan
def calc(kind,g):
 n=len(g);o=dict(n=n,eligible=n>=30,d_gt_med=float(g.d_gt_m.median()) if n else np.nan)
 if kind=='C1':
  for col,name in [('ds_dbeta_per_deg','ds_dbeta'),('ds_dpsi_per_deg','ds_dpsi'),('h_tan_per_m','h_tan'),('h_rad_per_m','h_rad')]:
   v=g[col].abs();o[name+'_med']=med(v);o[name+'_p10']=percentile(v,.1);o[name+'_p90']=percentile(v,.9)
  o.update(kappa_med=med(g.kappa),kappa_p10=percentile(g.kappa,.1),kappa_p90=percentile(g.kappa,.9),frac_same_sign=float((g.ds_dbeta_per_deg*g.ds_dpsi_per_deg>0).mean()) if n>=30 else np.nan,n_valid_kappa=int(g.kappa.notna().sum()),fp_margin_med=med(g.fp_margin))
 elif kind=='C1B':
  for c in ['ds_pos','ds_psi','r_base']:o['rms_'+c]=rms(g[c]) if n>=30 else np.nan
  den=o['rms_r_base'];o.update(lambda_pos=o['rms_ds_pos']/den if den>1e-12 else np.nan,lambda_psi=o['rms_ds_psi']/den if den>1e-12 else np.nan,sqrt_V_rms=float(np.sqrt(g.V.mean())) if n>=30 else np.nan)
 elif kind=='C2':
  for c in ['psi','tan','rad','b']:o['share_'+c+'_med']=med(g['share_'+c])
  o['n_valid_share']=int(g.share_psi.notna().sum())
  for c in ['dpsi_pol_deg','dbeta_pol_deg','dt_pol_cm','dr_pol_cm','dpsi_rng_deg','dt_rng_cm','dr_rng_cm']:o['sum_'+c]=float(g[c].sum()) if n>=30 else np.nan
  o['HsKs_med']=med(g.HsKs)
 elif kind=='C3':
  for suffix in ['', '_prior']:
   for c,ec,sc in [('t','e_t_cm','sigma_t_cm'),('r','e_r_cm','sigma_r_cm'),('psi','psi_err_deg','sigma_psi_deg')]:
    e=g[ec+suffix];z=g['z_'+c+suffix];o.update({f'rms_e_{c}{suffix}':rms(e) if n>=30 else np.nan,f'mean_e_{c}{suffix}':float(e.mean()) if n>=30 else np.nan,f'sigma_{c}_med{suffix}':med(g[sc+suffix]),f'rms_z_{c}{suffix}':rms(z) if n>=30 else np.nan,f'mean_z_{c}{suffix}':float(z.mean()) if n>=30 else np.nan,f'cov95_{c}{suffix}':float((abs(z)<1.96).mean()) if n>=30 else np.nan})
   o['rho_t_psi_med'+suffix]=med(g['rho_t_psi'+suffix])
 return o

def main():
 assert json.loads((ROOT/'CALC_GATE.json').read_text())['status']=='PASS';allframes={};summ={};groups={};account=[];checks=[]
 for kind,out in [('C1','C1_HS_BY_BIN.csv'),('C1B','C1B_BY_BIN.csv'),('C2','C2_ALLOC_BY_BIN.csv'),('C3','C3_CALIB_BY_BIN.csv')]:
  df=pd.read_csv(ROOT/(kind+'_PACKETS.csv.gz'));allframes[kind]=df;res=[];grp=[]
  for key,g0 in df.groupby(KEY):
   g=g0[g0.scoring & (g0.accepted if kind=='C2' else True)]
   for population,q in [('all',g0),('scoring',g0[g0.scoring]),('scoring_accepted',g0[g0.scoring & g0.accepted])]:
    counts=q.groupby('bin').size();assert int(counts.sum())==len(q)
    account.append(dict(file=kind,case=key[0],bias=key[1],arm=key[2],population=population,n=len(q),sum_bin_n=int(counts.sum())))
   nsum=0;validbins=[]
   for label in LABELS:
    gg=g[g.bin==label];row=dict(zip(KEY,key));row.update(bin=label,**calc(kind,gg));res.append(row);nsum+=len(gg)
    if len(gg)>=30:validbins.append(label)
   assert nsum==len(g);checks.append(dict(name='K6_'+kind+'_'+'_'.join(key),packet_rows=len(g0),eligible_rows=len(g),sum_summary_n=nsum,pass_check=True))
   for label,lo,hi in [('near',0,1.5),('mid',1.5,4),('far',4,np.inf)]:
    raw=g[(g.d_gt_m>=lo)&(g.d_gt_m<hi)];gg=raw[raw.bin.isin(validbins)];row=dict(zip(KEY,key));row.update(bin_group=label,n_before_bin_exclusion=len(raw),n_excluded_small_bins=len(raw)-len(gg),**calc(kind,gg));grp.append(row)
  sd=pd.DataFrame(res);gd=pd.DataFrame(grp)
  # Delta values on MB rows only; BB is the reference, not a zero-filled synthetic observation.
  metrics=[c for c in sd if c not in KEY+['bin','n','eligible','d_gt_med'] and not c.startswith('n_')]
  bb=sd[sd.arm=='BB'].set_index(['case','bias','bin'])
  for metric in metrics:
   sd['delta_'+metric]=[float(row[metric])-float(bb.loc[(row['case'],row['bias'],row['bin']),metric]) if row['arm']=='MB' else np.nan for _,row in sd.iterrows()]
  sd.to_csv(ROOT/out,index=False,na_rep='NA');gd.to_csv(ROOT/f'{kind}_GROUPS.csv',index=False,na_rep='NA');summ[kind]=sd;groups[kind]=gd
 pd.DataFrame(account).to_csv(ROOT/'K6_COUNTS.csv',index=False)
 # Full all-time packet count identities and paired RF residual identity.
 nrows=[len(x) for x in allframes.values()];assert len(set(nrows))==1
 c1b=allframes['C1B'];paired=c1b.pivot(index=['case','arm','pose_id'],columns='bias',values='r_base');assert np.array_equal(paired.B0.to_numpy(),paired.L2.to_numpy())
 decisions=[]
 for key,g in groups['C1'].groupby(KEY):
  case,bias,arm=key
  def cell(kind,group):return groups[kind][(groups[kind].case==case)&(groups[kind].bias==bias)&(groups[kind].arm==arm)&(groups[kind].bin_group==group)].iloc[0]
  for group in ['near','mid','far']:
   a,b,c,d=[cell(k,group) for k in ['C1','C1B','C2','C3']];far=cell('C3','far')
   qs=[('Q1','kappa_med',a.kappa_med,'0.5 <= value <= 2',lambda v:.5<=v<=2,a.n),('Q1b','lambda_pos',b.lambda_pos,'value > 3',lambda v:v>3,b.n),('Q2','share_psi_med',c.share_psi_med,'value > .5 and > share_tan_med',lambda v:v>.5 and v>c.share_tan_med,c.n),('Q3','rms_z_t',d.rms_z_t,'value > 2 and > far rms_z_t',lambda v:v>2 and v>far.rms_z_t,d.n)]
   for question,metric,value,threshold,test,n in qs:
    available=np.isfinite(value) and n>=30 and (question!='Q3' or np.isfinite(far.rms_z_t)) and (question!='Q2' or np.isfinite(c.share_tan_med))
    primary=case in PRIMARY;deciding=group=='near' and arm=='BB' and primary
    result=('SUPPORT' if test(value) else 'NOT_SUPPORT') if available and deciding else 'NA';note='primary descriptive operational decision' if deciding and available else 'insufficient samples/denominator or unavailable far comparison' if deciding else 'descriptive only (auxiliary case, MB or non-near group)'
    decisions.append(dict(question=question,case=case,bias=bias,arm=arm,bin_group=group,metric=metric,value=value,threshold=threshold,result=result,n=n,n_before_bin_exclusion=int(cell({'Q1':'C1','Q1b':'C1B','Q2':'C2','Q3':'C3'}[question],group).n_before_bin_exclusion),share_tan_med=c.share_tan_med if question=='Q2' else np.nan,far_rms_z_t=far.rms_z_t if question=='Q3' else np.nan,note=note))
 dec=pd.DataFrame(decisions);dec.to_csv(ROOT/'DECISIONS.csv',index=False,na_rep='NA');route=[]
 for q in ['Q1','Q1b','Q2','Q3']:
  for case in PRIMARY:
   d=dec[(dec.question==q)&(dec.case==case)&(dec.arm=='BB')&(dec.bin_group=='near')].set_index('bias');v=list(d.result);status='SUPPORT' if all(x=='SUPPORT' for x in v) else 'NOT_SUPPORT' if all(x=='NOT_SUPPORT' for x in v) else 'NA' if 'NA' in v else 'MIXED'
   route.append(dict(question=q,case_group=case,B0=d.loc['B0','result'],L2=d.loc['L2','result'],group_result=status,B0_value=d.loc['B0','value'],L2_value=d.loc['L2','value']))
 pd.DataFrame(route).to_csv(ROOT/'ROUTE_DECISIONS.csv',index=False,na_rep='NA')
 # Equivalent errors: provide both stated targets, do not assume an unspecified e* target.
 es=[];c1=allframes['C1'];merged=c1.merge(c1b[['case','bias','arm','k','r_base']],on=['case','bias','arm','k'],validate='one_to_one')
 for key,g0 in merged.groupby(KEY+['bin']):
  g=g0[g0.scoring];n=len(g);sig=rms(g.r_base);ht=abs(g.h_tan_per_m);hp=abs(g.ds_dpsi_per_deg);noise=np.divide(sig*100,ht,out=np.full(n,np.nan),where=ht>1e-12);one=np.divide(hp*100,ht,out=np.full(n,np.nan),where=ht>1e-12);approx=np.divide(sig*100*g.d_est_m*np.pi/180,hp,out=np.full(n,np.nan),where=hp>1e-12)
  es.append(dict(zip(KEY+['bin'],key))|dict(n=n,e_noise_cm_med=float(np.nanmedian(noise)) if n>=30 and np.isfinite(noise).sum()>=30 else np.nan,e_noise_kappa1_cm_med=float(np.nanmedian(approx)) if n>=30 and np.isfinite(approx).sum()>=30 else np.nan,e_1deg_cm_med=float(np.nanmedian(one)) if n>=30 and np.isfinite(one).sum()>=30 else np.nan))
 pd.DataFrame(es).to_csv(ROOT/'E_STAR_BY_BIN.csv',index=False,na_rep='NA')
 # All metrics delta for pooled groups, preserve NA.
 delta=[]
 for kind,gd in groups.items():
  bb=gd[gd.arm=='BB'].set_index(['case','bias','bin_group'])
  for _,row in gd[gd.arm=='MB'].iterrows():
   b=bb.loc[(row['case'],row['bias'],row['bin_group'])]
   for metric in gd.columns:
    if metric in KEY+['bin_group','eligible'] or metric.startswith('n'):continue
    delta.append(dict(stage=kind,case=row['case'],bias=row['bias'],bin_group=row['bin_group'],metric=metric,BB=b[metric],MB=row[metric],delta=float(row[metric])-float(b[metric])))
 pd.DataFrame(delta).to_csv(ROOT/'MB_MINUS_BB.csv',index=False,na_rep='NA')
 old=json.loads((ROOT/'CHECKS.json').read_text());old['checks'].extend(checks);old['K6_all_packet_rows']=nrows[0];old['paired_RF_residual_identical']=True;(ROOT/'CHECKS.json').write_text(json.dumps(old,indent=2))
 (ROOT/'SUMMARY_GATE.json').write_text(json.dumps(dict(status='PASS',packet_rows=nrows[0],decisions=len(dec),route_groups=route),indent=2,allow_nan=True))
 print(pd.DataFrame(route).to_string(index=False))
if __name__=='__main__':main()
