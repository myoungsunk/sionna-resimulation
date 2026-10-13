import json,hashlib,sys,time,datetime,platform,traceback
from pathlib import Path
import numpy as np
import repair_short_range as legacy
from repair_short_range import *
from repair_short_range_v2 import *
from repair_short_range_run import cases
H=Path(__file__).resolve().parent;O=H/'out/i2_short_range_kernel_v2_01'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(n,v):(O/n).write_text(json.dumps(v,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read_cloud(n):
    with np.load(O/n,allow_pickle=False) as f:return f['samples'],f['weights']
def main():
    O.mkdir(exist_ok=False);start=now();tick=time.perf_counter();legacy.DEADLINE=tick+7200;code=1
    sources=[H/f for f in ['repair_short_range_v2.py','repair_short_range_v2_run.py','I2_SHORT_RANGE_V2_DESIGN.json','tests/test_repair_short_range_v2.py','repair_short_range.py','repair_short_range_run.py','repair_target.py','i2_s0_batch.py','i2_batch.py','out/I2_SHORT_RANGE_V2_TESTS.log']]
    real=list(cases());sources +=[p for _,_,_,pp in real for p in pp]
    protected=H/'out/i2_short_range_kernel_01/EXECUTION_RECEIPT.json';old=json.loads(protected.read_text());sources.append(protected)
    oldhash={n:sha(protected.parent/n) for n in old['output_sha256']}
    hashes={str(p.relative_to(H)):sha(p) for p in sources}
    write('FROZEN_RECEIPT.json',dict(start=start,input_sha256=hashes,command=[sys.executable,*sys.argv],python=sys.version,platform=platform.platform(),legacy_output_sha256=oldhash))
    try:
        _,p,c,_=real[0];toy={k:v.copy() for k,v in p.items()};toy.update(t_s=np.array([0.,.2]),dt_s=np.array([0.,.2]),ds_odom=np.array([0.,.04]),dtheta_gyro=np.array([0.,.015]),dtheta_odom=np.array([0.,.014]),range_m=np.array([4.,4.02]),range_mask=np.ones(2,dtype=bool))
        separate={k:v.copy() for k,v in toy.items()};separate['ds_odom']=np.array([0.,.4]);separate['range_m']=np.array([4.,4.])
        results=[]
        for idx,(name,p,c) in enumerate([('SYNTHETIC',toy,c)]+[(r,p,c) for r,p,c,_ in real]+[('SEPARATED_TOY',separate,c)]):
            print(name,'START',now(),flush=True);model=IndependentOneStep(p,c);target=S0BatchTarget(p,c,'RANGE')
            write(name+'_INPUT.json',dict(public={k:v.tolist() for k,v in p.items()},config=c))
            checks=draw_proposal(target,np.random.default_rng(35100+idx),64);mir=reflected(model,checks,target)
            density_error=float(np.max(abs(model.full(checks)-np.array([production_full(target,x) for x in checks]))))
            reflection_error=float(np.max(abs(model.full(checks)-model.full(mir))))
            if density_error>1e-8 or reflection_error>1e-10:raise AssertionError('target or reflection mismatch')
            write(name+'_TARGET_CHECKS.json',dict(full_logdensity_error=density_error,reflection_logdensity_error=reflection_error,initial_range_consumed_once=bool(not target.mask[0] and target.range_count==1)))
            h72,d72=heading_integration(model,72,power=13);basins=basin_definition(h72,d72)
            # Basin boundaries frozen before independent144-grid and sampler data.
            write(name+'_BASIN_DEFINITION.json',dict(basins,grid=72,power=13,replicates=4,heading=h72.tolist(),density=d72.tolist()))
            h72fine,d72fine=heading_integration(model,72,power=14)
            h144,d144=heading_integration(model,144)
            def grid_mass(h,d):
                x=np.zeros((len(h),7));x[:,1]=h
                return np.array([basin_mass(x,w,basins['edges']) for w in d])
            gm72=grid_mass(h72,d72);gm144=grid_mass(h144,d144);grid_agreement=mass_agreement(grid_mass(h72fine,d72fine),gm144)
            nuisance_agreement=mass_agreement(gm72,grid_mass(h72fine,d72fine))
            write(name+'_HEADING_GRID.json',dict(grid144=h144.tolist(),density144=d144.tolist(),grid_mass_agreement=grid_agreement,nuisance_resolution_agreement=nuisance_agreement))
            print(name,'HEADING END',now(),flush=True)
            refs={}
            for power in [17,19]:
                stats=[]
                for rep in range(16):
                    x,w,s=integration(model,power,rep);stats.append(s)
                    np.savez_compressed(O/f'{name}_QMC_{power}_{rep}.npz',samples=x,weights=w)
                refs[power]=stats;print(name,'QMC',power,'END',now(),flush=True)
            samples,accept=joint_mh_v2(target,model,15000+idx)
            np.savez_compressed(O/f'{name}_BATCH.npz',samples=samples)
            flat=samples.reshape(-1,7);extra=np.column_stack([model.full(flat),model.likelihood(flat,True)[2]]).reshape(16,-1,2);diag=diagnostics(samples,extra)
            bs=[dict(statistics(a,np.ones(len(a))),mcse=batch_mcse(a)) for a in samples]
            print(name,'BATCH END',diag['passes'],now(),flush=True)
            pf=[]
            for rep in range(16):
                x,w,s=particle(target,25000+idx*100+rep);pf.append(s['statistics']);write(f'{name}_PF_{rep}_DIAGNOSTICS.json',s)
                np.savez_compressed(O/f'{name}_PF_{rep}.npz',samples=x,weights=w)
                print(name,'PF',rep,'END',now(),flush=True)
            x0,w0=read_cloud(f'{name}_QMC_19_0.npz');grid=[]
            for col in features(x0).T:
                order=np.argsort(col);grid.append(np.interp(np.arange(.01,1,.01),np.cumsum(w0[order]),col[order]))
            ld=model.full(x0);order=np.argsort(-ld);threshold=np.interp([.5,.9,.95],np.cumsum(w0[order]),ld[order])
            def mode_measure(x,w):
                return np.r_[basin_mass(x,w,basins['edges']),np.bincount(reflection_branch(model,x),weights=w,minlength=2)]
            rm=[];rmode=[];pm=[];pmode=[]
            for rep in range(1,16):
                x,w=read_cloud(f'{name}_QMC_19_{rep}.npz');rm.append(measures(model,x,w,grid,threshold));rmode.append(mode_measure(x,w))
            for rep in range(16):
                x,w=read_cloud(f'{name}_PF_{rep}.npz');pm.append(measures(model,x,w,grid,threshold));pmode.append(mode_measure(x,w))
            bm=[];bmode=[];within=[];modewithin=[];crossings=[]
            for a in samples:
                w=np.full(len(a),1/len(a));bm.append(measures(model,a,w,grid,threshold));bmode.append(mode_measure(a,w))
                blocks=np.array_split(a,16);mv=[];mm=[]
                for b in blocks:
                    wb=np.full(len(b),1/len(b));mv.append(measures(model,b,wb,grid,threshold));mm.append(mode_measure(b,wb))
                within.append(np.var(mv,0,ddof=1)/16);modewithin.append(np.var(mm,0,ddof=1)/16)
                branch=reflection_branch(model,a);crossings.append(int(np.count_nonzero(branch[1:]!=branch[:-1])))
            bounds=dict(PF=simultaneous(np.array(rm),np.array(pm)),BATCH=simultaneous(np.array(rm),np.array(bm),within),PF_vs_BATCH=simultaneous(np.array(pm),np.array(bm),within))
            modebounds=dict(PF=mass_agreement(np.array(rmode),np.array(pmode)),BATCH=mass_agreement(np.array(rmode),np.array(bmode),modewithin),PF_vs_BATCH=mass_agreement(np.array(pmode),np.array(bmode),modewithin))
            exact=np.full((16,2),.5)
            modebounds['PF_exact_reflection']=mass_agreement(exact,np.array(pmode)[:,-2:])
            modebounds['BATCH_exact_reflection']=mass_agreement(exact,np.array(bmode)[:,-2:],np.array(modewithin)[:,-2:])
            modebounds['QMC_exact_reflection']=mass_agreement(exact,np.array(rmode)[:,-2:])
            comparisons=dict(resolution=compare_v2(refs[17],refs[19]),PF=compare_v2(refs[19],pf),BATCH=compare_v2(refs[19],bs),PF_vs_BATCH=compare_v2(pf,bs))
            mcmean=max(float(np.max(np.array(s['mcse']['mean'])/s['sd'])) for s in bs)
            mcq=max(float(np.max(np.array(s['mcse']['quantiles'])/np.array(s['sd'])[:,None])) for s in bs)
            failures=[]
            if not diag['passes']:failures.append('Batch rank-folded Rhat/ESS')
            if mcmean>.05 or mcq>.1:failures.append('normalized Batch MCSE')
            for method,a in comparisons.items():
                if not a['moment_pass'] or not a['sector_pass']:failures.append(method+' moments/sectors')
            for method,a in bounds.items():
                if not a['passes']:failures.append(method+' simultaneous CDF/HPD')
            for method,a in modebounds.items():
                if not a['passes']:failures.append(method+' projected basin/reflection branch masses')
            if not grid_agreement['passes']:failures.append('heading grid basin integration resolution')
            if not nuisance_agreement['passes']:failures.append('heading grid nuisance integration resolution')
            if min(crossings)==0:failures.append('unvisited reflection branch')
            pf_cov=np.mean([s['covariance'] for s in pf],0);batch_cov=np.mean([s['covariance'] for s in bs],0)
            corr=lambda a:a/np.sqrt(np.outer(np.diag(a),np.diag(a)))
            result=dict(case=name,gate='PASS' if not failures else 'INCONCLUSIVE',failed_or_missing=failures,comparison=comparisons,simultaneous=bounds,mode_comparison=modebounds,heading_grid=grid_agreement,nuisance_grid=nuisance_agreement,basin_definition=basins,branch_crossings=crossings,normalized_batch_mean_mcse=mcmean,normalized_batch_quantile_mcse=mcq,batch_diagnostics=diag,kernel=accept,qmc_statistics=refs,pf_statistics=pf,batch_statistics=bs,hpd_threshold=threshold.tolist(),covariance_difference=(pf_cov-batch_cov).tolist(),correlation_difference=(corr(pf_cov)-corr(batch_cov)).tolist(),unvisited_modes_excluded=False,I3='NOT_RUN')
            write(name+'_RESULT.json',result);results.append(result);print(name,'END',result['gate'],now(),flush=True)
        write('SHORT_RANGE_V2_GATE.json',dict(gate='PASS' if all(r['gate']=='PASS' for r in results) else 'INCONCLUSIVE',reference='REFERENCE_NOT_VALIDATED',cases=[dict(case=r['case'],gate=r['gate'],failed_or_missing=r['failed_or_missing']) for r in results],scope='one-transition finite12sigma conditional target; projected heading and exact reflection modes only',I3='NOT_RUN',I7='NOT_RUN'));code=0
    except Exception:
        (O/'ERROR.log').write_text(traceback.format_exc(),encoding='utf-8');raise
    finally:
        write('EXECUTION_RECEIPT.json',dict(start=start,end=now(),exit_code=code,elapsed_seconds=time.perf_counter()-tick,inputs_unchanged=all(sha(H/n)==v for n,v in hashes.items()),legacy_outputs_unchanged=all(sha(protected.parent/n)==v for n,v in oldhash.items()),input_sha256=hashes,output_sha256={p.name:sha(p) for p in O.iterdir() if p.is_file()}))
if __name__=='__main__':main()
