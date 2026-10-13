import json,hashlib,sys,time,datetime,platform,traceback
from pathlib import Path
import numpy as np
from scipy.stats import t as student_t
from repair_short_range import *
import repair_short_range as kernel
H=Path(__file__).resolve().parent;O=H/'out/i2_short_range_kernel_01'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(n,v):(O/n).write_text(json.dumps(v,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def cases():
 for route in ['R2','R4']:
  cell='A2_3_GAUSS_LEVEL_'+route+'_d2_s8000';root=H/'out/i2_s0_run_01'/cell
  p0=root/'RANGE_0.05_5_public.npz';c0=root/'RANGE_0.05_5_config.json'
  with np.load(p0,allow_pickle=False) as f:p={k:f[k][:2] for k in f.files}
  c=json.loads(c0.read_text());yield route,p,c,[p0,c0]
 defunused=0

def compare(refs,others):
 a=np.array([r['mean'] for r in refs]);b=np.array([r['mean'] for r in others]);sd=np.sqrt((np.mean([np.square(r['sd']) for r in refs],axis=0)+np.mean([np.square(r['sd']) for r in others],axis=0))/2)
 def variance(key,between):
  if 'mcse' not in others[0]:return between
  within=np.sum(np.square([r['mcse'][key] for r in others]),axis=0)/16
  return np.maximum(between,within)
 bv=variance('mean',b.var(axis=0,ddof=1)/4);err=np.sqrt(a.var(axis=0,ddof=1)/4+bv);mean=(abs(a.mean(0)-b.mean(0))+1.96*err)/sd
 lr=np.array([np.log(r['sd']) for r in refs]);lo=np.array([np.log(r['sd']) for r in others]);ratio=np.exp(abs(lr.mean(0)-lo.mean(0))+1.96*np.sqrt(lr.var(0,ddof=1)/4+np.maximum(lo.var(0,ddof=1)/4,np.sum([np.square(np.array(r.get("mcse",{}).get("sd",np.zeros(8)))/np.array(r["sd"])) for r in others],axis=0)/16)))
 qa=np.array([r['quantiles'] for r in refs]);qb=np.array([r['quantiles'] for r in others]);qe=(abs(qa.mean(0)-qb.mean(0))+1.96*np.sqrt(qa.var(0,ddof=1)/4+variance("quantiles",qb.var(0,ddof=1)/4)))/sd[:,None]
 sa=np.array([r['sector_mass'] for r in refs]);sb=np.array([r['sector_mass'] for r in others]);sector=abs(sa.mean(0)-sb.mean(0))+student_t.ppf(1-.05/24,3)*np.sqrt(sa.var(0,ddof=1)/4+variance("sector_mass",sb.var(0,ddof=1)/4))
 return dict(mean_upper_sd=mean.tolist(),sd_ratio_upper=ratio.tolist(),quantile_upper_sd=qe.tolist(),sector_simultaneous_upper=sector.tolist(),moment_pass=bool(max(mean)<=.25 and max(ratio)<=1.25 and np.max(qe)<=.1),sector_pass=bool(max(sector)<=.05),MC_method='independent-replicate SE; sector Bonferroni t(df3) conservative approximate bound')

def main():
 O.mkdir(exist_ok=False);start=now();tick=time.perf_counter();code=1;kernel.DEADLINE=tick+7200
 sources=[H/'repair_short_range.py',Path(__file__),H/'I2_SHORT_RANGE_DESIGN.json',H/'tests/test_repair_short_range.py',H/'i2_s0_batch.py',H/'i2_batch.py',H/'repair_target.py',H/'out/I2_SHORT_RANGE_TESTS.log',H/'out/I2_SHORT_RANGE_TEST_RECEIPT.json',H/'tests/test_repair_target.py',H/'tests/test_i2_s0_batch.py']
 real=list(cases());sources += [p for _,_,_,pp in real for p in pp];hashes={str(p.relative_to(H)):sha(p) for p in sources}
 write('FROZEN_RECEIPT.json',dict(start=start,input_sha256=hashes,command=[sys.executable,*sys.argv],python=sys.version,platform=platform.platform()))
 try:
  route,p,c,_=real[0];toy={k:v.copy() for k,v in p.items()};toy.update(t_s=np.array([0.,.2]),dt_s=np.array([0.,.2]),ds_odom=np.array([0.,.04]),dtheta_gyro=np.array([0.,.015]),dtheta_odom=np.array([0.,.014]),range_m=np.array([4.,4.02]),range_mask=np.ones(2,dtype=bool))
  results=[]
  for idx,(name,p,c) in enumerate([('SYNTHETIC',toy,c)]+[(r,p,c) for r,p,c,_ in real]):
   print(name,'START',now(),flush=True);model=IndependentOneStep(p,c);target=S0BatchTarget(p,c,'RANGE');write(name+'_INPUT.json',dict(public={k:v.tolist() for k,v in p.items()},config=c,synthetic=name=='SYNTHETIC'))
   check=draw_proposal(target,np.random.default_rng(35000+idx),64);ld=model.full(check);pd=np.array([production_full(target,a) for a in check]);flux=[]
   for x,y in zip(check[::2],check[1::2]):
    lx,ly=production_full(target,x),production_full(target,y);qx,qy=proposal_log(target,x),proposal_log(target,y);lr=mh_log_ratio(ly,lx,qx,qy);flux.append(abs(lx+qy+min(0,lr)-ly-qx-min(0,-lr)))
   density_check=dict(seed=35000+idx,n=64,max_absolute_full_logdensity_error=float(np.max(abs(ld-pd))),max_log_flux_balance_error=max(flux),initial_range_consumed_once=bool(not target.mask[0] and target.range_count==1))
   write(name+'_TARGET_DENSITY_CHECKS.json',density_check)
   if density_check['max_absolute_full_logdensity_error']>1e-8 or density_check['max_log_flux_balance_error']>1e-10:raise AssertionError('fulltarget/proposal validation failed')
   refs={};cloud=[]
   for power in [17,19]:
    stats=[]
    for rep in range(4):
     x,w,s=integration(model,power,rep);stats.append(s)
     if power==19:cloud.append((x,w))
     np.savez_compressed(O/f'{name}_QMC_{power}_{rep}.npz',samples=x,weights=w)
    refs[power]=stats;print(name,'QMC',power,'END',flush=True)
   samples,accept=joint_mh(target,14000+idx);diag=diagnostics(samples)
   for retained in [16000,32000]:
    if diag['passes']:break
    samples,accept=joint_mh(target,14000+idx,retained=retained);diag=diagnostics(samples)
   np.savez_compressed(O/f'{name}_BATCH.npz',samples=samples);flat=samples.reshape(-1,7);extra=np.column_stack([model.full(flat),model.likelihood(flat,True)[2]]).reshape(4,-1,2);diag=diagnostics(samples,extra);bs=[dict(statistics(a,np.ones(len(a))),mcse=batch_mcse(a)) for a in samples];print(name,'BATCH END',diag['passes'],flush=True)
   pf=[];pc=[]
   for rep in range(4):
    x,w,s=particle(target,24000+idx*10+rep);pf.append(s['statistics']);write(f'{name}_PF_{rep}_DIAGNOSTICS.json',s);pc.append((x,w));np.savez_compressed(O/f'{name}_PF_{rep}.npz',samples=x,weights=w);print(name,'PF',rep,'END',flush=True)
   # Frozen CDF grid and HPD levels computed from first independent QMC
   # replicate, evaluated only on heldout reference replicas 1..3.
   x0,w0=cloud[0];features=lambda x:np.column_stack([x[:,0],np.sin(x[:,1]),np.cos(x[:,1]),x[:,2:]])
   ff=features(x0);grid=[]
   for col in ff.T:
    order=np.argsort(col);grid.append(np.interp(np.arange(.01,1,.01),np.cumsum(w0[order]),col[order]))
   dens=model.full(x0);order=np.argsort(-dens);threshold=np.interp([.5,.9,.95],np.cumsum(w0[order]),dens[order])
   def measures(x,w):
    f=features(x);cdf=np.array([[(w*(f[:,j]<=q)).sum() for q in grid[j]] for j in range(f.shape[1])]).ravel();hpd=np.array([(w*(model.full(x)>=q)).sum() for q in threshold]);return np.r_[cdf,hpd]
   rm=np.array([measures(x,w) for x,w in cloud[1:]]);pm=np.array([measures(x,w) for x,w in pc]);bm=np.array([measures(a,np.ones(len(a))/len(a)) for a in samples]);bounds={}
   for method,mm in [('PF',pm),('BATCH',bm)]:
    mv=mm.var(0,ddof=1)/4
    if method=='BATCH':
     within=[]
     for a in samples:
      blocks=np.array_split(a,16);bs0=np.array([measures(bb,np.ones(len(bb))/len(bb)) for bb in blocks]);within.append(bs0.var(0,ddof=1)/16)
     mv=np.maximum(mv,np.sum(within,axis=0)/16)
    se=np.sqrt(rm.var(0,ddof=1)/3+mv);upper=abs(rm.mean(0)-mm.mean(0))+student_t.ppf(1-.05/(2*len(se)),2)*se
    bounds[method]=dict(cdf_upper=float(max(upper[:-3])),hpd_upper=upper[-3:].tolist(),method='heldout independent-replicate Bonferroni t df2; MCMC between-chain error does not prove mixing')
   failures=['disconnected density basin evidence NOT_ESTABLISHED']
   if not diag['passes']:failures.append('rank Rhat or bulk/tail ESS failure')
   if not compare(refs[17],refs[19])['moment_pass']:failures.append('QMC resolution moment agreement failure')
   for method,stats0 in [('BATCH',bs),('PF',pf)]:
    chk=compare(refs[19],stats0)
    if not chk['moment_pass']:failures.append(method+' mean/SD/quantile agreement failure')
    if not chk['sector_pass']:failures.append(method+' sector agreement failure')
    if bounds[method]['cdf_upper']>.05 or max(bounds[method]['hpd_upper'])>.05:failures.append(method+' simultaneous CDF/HPD bound failure')
   mcse_mean=max(float(np.max(np.array(s['mcse']['mean'])/np.array(s['sd']))) for s in bs);mcse_q=max(float(np.max(np.array(s['mcse']['quantiles'])/np.array(s['sd'])[:,None])) for s in bs)
   if mcse_mean>.05 or mcse_q>.1:failures.append('Batch normalized MCSE gate failure')
   pf_cov=np.mean([s['covariance'] for s in pf],axis=0);batch_cov=np.mean([s['covariance'] for s in bs],axis=0)
   correlation=lambda cov:cov/np.sqrt(np.outer(np.diag(cov),np.diag(cov)))
   joint=dict(PF_vs_BATCH=compare(pf,bs),correlation_difference=(correlation(pf_cov)-correlation(batch_cov)).tolist(),covariance_difference=(pf_cov-batch_cov).tolist(),max_abs_correlation_difference=float(np.max(abs(correlation(pf_cov)-correlation(batch_cov)))),claim='descriptive; no invented correlation gate')
   result=dict(case=name,joint_comparison=joint,normalized_batch_mean_mcse=mcse_mean,normalized_batch_quantile_mcse=mcse_q,failed_or_missing=failures,qmc_statistics=refs,batch_statistics=bs,pf_statistics=pf,batch_diagnostics=diag,acceptance=accept,resolution=compare(refs[17],refs[19]),PF=compare(refs[19],pf),BATCH=compare(refs[19],bs),simultaneous=bounds,hpd_threshold=threshold.tolist(),disconnected_basins='NOT_ESTABLISHED; no unvisited-mode exclusion',gate='INCONCLUSIVE',reason='; '.join(failures),I3='NOT_RUN')
   write(name+'_RESULT.json',result);results.append(result);print(name,'END',now(),flush=True)
  write('SHORT_RANGE_GATE.json',dict(gate='INCONCLUSIVE',reference='REFERENCE_NOT_VALIDATED',cases=[dict(case=r['case'],batch_diagnostics=r['batch_diagnostics'],resolution=r['resolution'],PF=r['PF'],BATCH=r['BATCH'],simultaneous=r['simultaneous']) for r in results],I3='NOT_RUN',I7='NOT_RUN'));code=0
 except Exception:
  (O/'ERROR.log').write_text(traceback.format_exc(),encoding='utf-8');raise
 finally:
  write('EXECUTION_RECEIPT.json',dict(start=start,end=now(),exit_code=code,elapsed_seconds=time.perf_counter()-tick,inputs_unchanged=all(sha(H/n)==v for n,v in hashes.items()),input_sha256=hashes,output_sha256={p.name:sha(p) for p in O.iterdir() if p.is_file()}))
if __name__=='__main__':main()








