from common import *
import traceback
MIN_DERIV=1e-3
def field(model,case,x,uu=None,rr=None,gradient=False):
 hs=[];js=[]
 for k in range(0,len(x),64):
  S.stopcheck();model.explicit=None if uu is None else (uu[k:k+64],rr[k:k+64])
  h,j=model.batch(x[k:k+64],case,gradient=gradient);hs.append(h[:,1])
  if gradient:js.append(j[:,1,2])
 model.explicit=None
 return np.concatenate(hs),np.concatenate(js) if gradient else None
def equivalent(model,case,x,truepsi,target):
 n=len(x);answer=np.full(n,np.nan);residual=np.full(n,np.nan);slope=np.full(n,np.nan);reason=np.full(n,'NO_ROOT',dtype='U16');work=x.copy()
 def f(ids,angles,grad=False):
  xx=work[ids].copy();xx[:,2]=truepsi[ids]+np.radians(angles)
  val,der=field(model,case,xx,gradient=grad);return val-target[ids],der
 ids=np.arange(n);f0,_=f(ids,np.zeros(n));zero=abs(f0)<=1e-9
 answer[zero]=0;residual[zero]=f0[zero]
 last=np.column_stack([f0,f0]);done=zero.copy()
 for radius in np.arange(.5,20.01,.5):
  ids=np.flatnonzero(~done)
  if not len(ids):break
  candidates=np.full((len(ids),2),np.nan)
  for si,sign in enumerate([-1,1]):
   cur,_=f(ids,np.full(len(ids),sign*radius));prev=last[ids,si]
   hit=(cur*prev<=0)|(abs(cur)<=1e-9)
   hi_ids=ids[hit]
   if len(hi_ids):
    # Resolve candidate brackets on a 0.125-degree subgrid, closest-first.
    found=np.zeros(len(hi_ids),bool);oldf=prev[hit]
    for sub in range(1,5):
     angle=sign*(radius-.5+.125*sub);newf,_=f(hi_ids,np.full(len(hi_ids),angle));cross=(oldf*newf<=0)|(abs(newf)<=1e-9);active=np.flatnonzero(cross&~found)
     if len(active):
      ai=hi_ids[active];lo=np.full(len(ai),sign*(radius-.5+.125*(sub-1)));hi=np.full(len(ai),angle);fl=oldf[active].copy();fh=newf[active].copy()
      root=(lo+hi)/2;fr=np.full(len(ai),np.inf);converged=np.zeros(len(ai),bool)
      for it in range(32):
       pending=np.flatnonzero(~converged)
       if not len(pending):break
       # Bracket-preserving secant acceleration; midpoint fallback.
       ll=lo[pending];hh=hi[pending];ff=fl[pending];gg=fh[pending]
       fraction=np.divide(-ff,gg-ff,out=np.full(len(pending),.5),where=gg!=ff)
       fraction=np.where((fraction>.001)&(fraction<.999),fraction,.5)
       mid=ll+fraction*(hh-ll);fm,_=f(ai[pending],mid);root[pending]=mid;fr[pending]=fm
       converged[pending]=(abs(fm)<=1e-10)|(abs(hh-ll)<=1e-8)
       left=ff*fm<=0;hi[pending]=np.where(left,mid,hh);fh[pending]=np.where(left,fm,gg);lo[pending]=np.where(left,ll,mid);fl[pending]=np.where(left,ff,fm)
      valid=abs(fr)<=1e-9
      found[active[valid]]=True
      mapped=np.searchsorted(ids,ai[valid]);candidates[mapped,si]=root[valid]
     oldf=newf
   last[ids,si]=cur
  anyroot=np.isfinite(candidates).any(axis=1)
  if anyroot.any():
   pick=np.argmin(np.where(np.isfinite(candidates),abs(candidates),np.inf),axis=1);answer[ids[anyroot]]=candidates[np.arange(len(ids))[anyroot],pick[anyroot]];done[ids[anyroot]]=True
  if int(radius*2)%10==0:S.event('A_ROOT_SEARCH',case=case['id'],radius_deg=float(radius),remaining=int((~done).sum()))
 ids=np.flatnonzero(np.isfinite(answer))
 if len(ids):
  fr,der=f(ids,answer[ids],True);residual[ids]=fr;slope[ids]=der;reason[ids]='VALID';weak=abs(der)<MIN_DERIV;reason[ids[weak]]='LOW_SLOPE';answer[ids[weak]]=np.nan
 return answer,residual,slope,reason
def arrays(z,case):
 mask=z['t_s']>=30;x=z['x'][mask];truth=z['truth_scoring_only'][mask];a=np.asarray(case['anchor']);eraw=x[:,:,:2]-truth[:,None,:2]
 radial=truth[:,:2]-a[:2];d=np.linalg.norm(radial,axis=1);ur=radial/d[:,None];ut=np.column_stack([-ur[:,1],ur[:,0]])
 er=np.einsum('nji,ni->nj',eraw,ur);et=np.einsum('nji,ni->nj',eraw,ut)
 b,e,r=geometry(truth,case);bh,eh,rh=geometry(x,case)
 ps=wrap(np.degrees(x[:,:,2]-truth[:,None,2]));be=wrap(np.degrees(bh-b[:,None]));ph=wrap(ps-be)
 check('beta_sign_exact',be,wrap(np.degrees(np.arctan2(et,d[:,None]+er))),1e-10)
 xy=np.sum(eraw**2,axis=2);gap=np.mean(xy,axis=0)-np.mean(er**2+et**2,axis=0);check('XY_identity_m2',gap,np.zeros_like(gap),1e-12)
 return dict(psi=ps,beta=be,phi=ph,er=er*100,et=et*100,epsilon=np.degrees(eh-e[:,None]),range=(rh-r[:,None])*100,xy2=xy*10000,beta_small_approx=np.degrees(et/d[:,None]),wrap_residual=ps-be-ph),x,truth,(b,e,r,bh,eh,rh)
def stats(v):
 v=v[np.isfinite(v)]
 return dict(bias=float(v.mean()),std=float(v.std()),rmse=float(np.sqrt(np.mean(v*v)))) if len(v) else dict(bias=np.nan,std=np.nan,rmse=np.nan)
def metric_rows(a,case,bias,names,alphas):
 rows=[]
 for j,name in enumerate(names):
  row=dict(case=case['id'],route=case['route'],bias=bias,arm=str(name),alpha=float(alphas[j]),n=len(a['psi']))
  for k in ['psi','beta','phi','er','et','epsilon','range']:
   row.update({k+'_'+key:value for key,value in stats(a[k][:,j]).items()})
  row['xy_rmse_cm']=float(np.sqrt(a['xy2'][:,j].mean()));row['wrap_count']=int((abs(a['wrap_residual'][:,j])>1e-10).sum());row['bias_identity_residual']=float(a['psi'][:,j].mean()-a['beta'][:,j].mean()-a['phi'][:,j].mean())
  if row['wrap_count']==0:assert abs(row['bias_identity_residual'])<=1e-12
  if 'psi_eq' in a:
   row.update({'eq_'+key:value for key,value in stats(a['psi_eq'][:,j]).items()});row['undefined_fraction']=float(np.isnan(a['psi_eq'][:,j]).mean());row['eq_interpretable']=row['undefined_fraction']<=.1
  rows.append(row)
 return rows
def main():
 assert json.loads((ROOT/'A0_GATE.json').read_text())['status']=='PASS';preserve()
 write('A_CODE_LOCK.json',{str(p):S.sha(p) for p in [Path(__file__),ROOT/'PROTOCOL.md',ROOT/'A_NUMERICS_ADDENDUM.md']})
 _,model=models();rows=[];contrib=[];ratios=[];ref=pd.read_csv(E1/'SCORES.csv');dest=ROOT/'A';dest.mkdir(exist_ok=True)
 for case in V.MANIFEST['cases']:
  for bias in ['B0','L2']:
   stem=f'{case["id"]}_{bias}';z=load(E1/'E1'/f'{stem}.npz');a,x,true,geo=arrays(z,case);b,e,r,bh,eh,rh=geo;n,j=x.shape[:2]
   row0=metric_rows(a,case,bias,z['names'],[0,.25,.5,.75,1]);old=ref[(ref.stage=='E1')&(ref.case==case['id'])&(ref.bias==bias)].set_index('alpha')
   for row in row0:
    check('A_heading',row['psi_rmse'],old.loc[row['alpha'],'heading_rmse_deg']);check('A_range',row['range_rmse'],old.loc[row['alpha'],'range_rmse_cm']);check('A_XY',row['xy_rmse_cm']/100,old.loc[row['alpha'],'xy_rmse_m'])
   target,_=field(model,case,true);xp=x.reshape(-1,4).copy();tp=np.repeat(true[:,2],j);xp[:,2]=tp
   targetflat=np.repeat(target,j);eq,res,slope,reason=equivalent(model,case,xp,tp,targetflat)
   a['psi_eq']=eq.reshape(n,j);a['root_residual']=res.reshape(n,j);a['root_slope_per_rad']=slope.reshape(n,j);a['root_reason']=reason.reshape(n,j)
   base_b=np.repeat(b,j);base_e=np.repeat(e,j);base_r=np.repeat(r,j)
   sb,_=field(model,case,xp,unitvec(bh.ravel(),base_e),base_r)
   se,_=field(model,case,xp,unitvec(base_b,eh.ravel()),base_r)
   sr,_=field(model,case,xp,unitvec(base_b,base_e),rh.ravel())
   sp,_=field(model,case,xp)
   for key,val in [('ds_beta',sb),('ds_epsilon',se),('ds_r',sr),('ds_pos',sp)]:a[key]=(val-targetflat).reshape(n,j)
   a['ds_interaction']=a['ds_pos']-a['ds_beta']-a['ds_epsilon']-a['ds_r']
   rows.extend(metric_rows(a,case,bias,z['names'],[0,.25,.5,.75,1]))
   for ji,alpha in enumerate([0,.25,.5,.75,1]):
    rec=dict(case=case['id'],bias=bias,alpha=alpha)
    for k in ['ds_beta','ds_epsilon','ds_r','ds_pos','ds_interaction']:rec[k+'_bias']=float(a[k][:,ji].mean());rec[k+'_max_abs']=float(abs(a[k][:,ji]).max())
    denom=abs(rec['ds_pos_bias']);rec['interaction_ratio']=abs(rec['ds_interaction_bias'])/denom if denom>=1e-9 else None;rec['shares_interpretable']=denom>=1e-9 and rec['interaction_ratio']<=.3;contrib.append(rec)
   valid=np.isfinite(a['psi_eq'][:,0])&np.isfinite(a['psi_eq'][:,4]);missing=1-float(valid.mean());num=float((a['psi_eq'][valid,4]-a['psi_eq'][valid,0]).mean()) if valid.any() else None;den=float((a['psi'][valid,4]-a['psi'][valid,0]).mean()) if valid.any() else None;denall=float((a['psi'][:,4]-a['psi'][:,0]).mean())
   ratios.append(dict(case=case['id'],bias=bias,common_undefined=missing,numerator_deg=num,denominator_common_deg=den,denominator_E1_all_deg=denall,k_eq=num/den if missing<=.1 and abs(den)>=.05 else None,k_eq_E1_all=num/denall if missing<=.1 and abs(denall)>=.05 else None))
   np.savez_compressed(dest/f'{stem}.npz',t_s=z['t_s'][z['t_s']>=30],names=z['names'],**a)
   pd.DataFrame(rows).to_csv(ROOT/'A_METRICS.csv',index=False);pd.DataFrame(contrib).to_csv(ROOT/'A_INPUT_CONTRIBUTIONS.csv',index=False);pd.DataFrame(ratios).to_csv(ROOT/'A_EQ_RATIOS.csv',index=False);write('A_CHECKS.json',S.checks);S.event('A_CASE_PASS',case=case['id'],bias=bias)
 preserve();write('A_GATE.json',dict(status='PASS',metric_rows=len(rows),conditions=14,meaning='Numerical/metric checks only; undefined roots remain excluded.'));S.event('A_COMPLETE')
if __name__=='__main__':
 try:main()
 except BaseException as e:write('A_FAILURE.json',dict(error=str(e),traceback=traceback.format_exc()));raise
