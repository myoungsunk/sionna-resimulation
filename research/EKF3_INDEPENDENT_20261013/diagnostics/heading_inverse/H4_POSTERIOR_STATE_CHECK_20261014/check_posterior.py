"""Independent posterior replay; never changes saved estimates or gate tolerances."""
import sys, json, time, gzip
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'OPT'))
import run_heading as base

TOL = 1e-8

def posterior(prior, gain, innovation, applied):
    raw = prior + np.einsum('nij,nj->ni', gain, innovation)
    raw[~applied] = prior[~applied]
    result = raw.copy()
    result[:, 2] = base.wrap(result[:, 2])
    return result, raw

def errors(expected, stored):
    e = expected - stored
    e[:, 2] = base.wrap(e[:, 2])
    return np.abs(e)

def tests():
    p = np.array([[1.,2.,np.pi-.01],[1.,2.,-np.pi+.01],[1.,2.,.3]])
    k = np.tile(np.array([[1.],[2.],[1.]]),(3,1,1))
    v = np.array([[.02],[-.02],[10.]])
    expected, raw = posterior(p,k,v,np.array([True,True,False]))
    assert expected[0,2] < 0 and expected[1,2] > 0
    assert np.max(errors(expected[2:],p[2:])) == 0
    same = expected.copy(); same[:,2] += 2*np.pi
    assert np.max(errors(expected,same)) < 1e-14
    bad = expected.copy(); bad[0,0] += 2*TOL
    assert np.max(errors(expected,bad)) > TOL
    bad = expected.copy(); bad[0,2] += 2*TOL
    assert np.max(errors(expected,bad)) > TOL
    # Joint block and non-unit robust weight: direct gain equals information solve.
    P=np.diag([.2,.3,.1]); H=np.array([[.4,.2,1.],[1.,-.3,0.]])
    R=np.diag([.02,.1]); nu=np.array([.1,-.2])
    for weight in [1.,.2]:
        eff=R/weight; K=np.linalg.solve(H@P@H.T+eff,H@P).T
        delta=np.linalg.solve(np.linalg.inv(P)+H.T@np.linalg.solve(eff,H),H.T@np.linalg.solve(eff,nu))
        assert np.max(np.abs(K@nu-delta)) < 1e-14
    return dict(status='PASS',checks=['positive_wrap','negative_wrap','rejected_unchanged','equivalent_angle','corrupted_position_detected','corrupted_heading_detected','joint_gaussian_gain','joint_robust_gain'])

def run(smoke=False):
    started=time.time(); out=HERE/('SMOKE' if smoke else 'FULL');out.mkdir(exist_ok=False)
    test=tests();base.dump(out/'TEST_RECEIPT.json',test)
    original=json.loads((HERE.parent/'OPT/FULL/RECEIPT.json').read_text())
    for p,h in original['source_sha256'].items(): assert base.sha(p)==h,p
    p0=base.input_gate();lut=base.original_lut(p0)
    cases=p0['cases'][:1] if smoke else p0['cases']; stages=base.STAGES[:1] if smoke else base.STAGES
    caches={(c['id'],ch):dict(np.load(base.INPUT/(c['id']+'_'+ch+'.npz'))) for c in cases for ch in ['los','full']}
    groups=[]; tracehash={};total=0
    with gzip.open(out/'STATE_RESIDUALS.csv.gz','wt',newline='',compresslevel=1) as rawout:
      for stage,condition,level in stages:
        path=base.TRACE/stage/'RF_COMPONENT_TRACE.csv.gz'
        digest=base.sha(path);assert digest==original['trace_sha256'][str(path)]
        tracehash[str(path)]=digest
        frames=[]
        for chunk in pd.read_csv(path,chunksize=50000,float_precision='round_trip'):
            mask=chunk.case.isin([c['id'] for c in cases]) & chunk.model.isin(base.MODELS) & chunk.arm.isin(['A','C']) & chunk.seed.isin([0] if smoke else [0,1,2])
            frames.append(chunk[mask])
        allg=pd.concat(frames,ignore_index=True);motions={}
        for key,g in allg.groupby(['case','channel','range_model','seed','arm','model'],sort=False):
            cid,ch,rm,seed,arm,name=key;c=next(c for c in cases if c['id']==cid)
            if (cid,seed) not in motions: motions[cid,seed]=base.case_motion(p0,c,int(seed),level,condition)[3]
            motion=motions[cid,seed];cache=caches[cid,ch]
            g=g.sort_values('sample_index').reset_index(drop=True);old=g.iloc[:-1];g=g.iloc[1:].reset_index(drop=True)
            k=g.sample_index.to_numpy(int);assert np.all(k-old.sample_index.to_numpy(int)==1)
            ds=motion['ds_odom'][k];da=motion['dtheta_gyro'][k];psi=old.psi.to_numpy();distance=ds*np.sinc(da/(2*np.pi))
            # Prior constructed without truth or current saved posterior.
            prior=np.column_stack([old.x.to_numpy()+distance*np.cos(psi+da/2),old.y.to_numpy()+distance*np.sin(psi+da/2),base.wrap(psi+da)])
            pp=base.propagated_cov(base.packP(old),psi,ds,da,motion['dt_s'][k])
            truth=cache['truth'][k]
            storedprior=np.column_stack([truth[:,0]+g.prior_error_x,truth[:,1]+g.prior_error_y,base.wrap(truth[:,2]+np.radians(g.prior_heading_error_deg))])
            priorerr=float(errors(prior,storedprior).max())
            pcerr=float(np.max(abs(np.diagonal(pp,axis1=1,axis2=2)-g[['prior_Pxx','prior_Pyy','prior_Ppsi']].to_numpy())))
            hs,jac=base.native(lut,c,prior);H=jac[:,None,:];R=np.tile(np.array([[[base.RS]]]),(len(g),1,1));z=cache['s'][k,None];pred=hs[:,None]
            if arm=='C':
                xy=prior[:,:2]-np.asarray(c['anchor'][:2]);dist=np.sqrt(np.sum(xy**2,axis=1)+(c['robot_z_m']-c['anchor'][2])**2)
                H=np.stack([jac,np.column_stack([xy/dist[:,None],np.zeros(len(g))])],axis=1)
                R=np.tile(np.diag([base.RS,base.RR]),(len(g),1,1));z=np.column_stack([z[:,0],cache[rm][k]]);pred=np.column_stack([hs,dist])
            assert np.isfinite(z).all()
            innovation=z-pred;S=H@pp@H.transpose(0,2,1)+R
            nis=np.einsum('ni,ni->n',innovation,np.linalg.solve(S,innovation[...,None])[...,0])
            applied=g.status.to_numpy()=='applied';gate=6.6348966010212145 if arm=='A' else 9.21034037197618
            gatefails=int(np.count_nonzero(applied!=(nis<=gate)))
            w=np.ones(len(g)) if name=='M0' else g.huber_weight.fillna(1).to_numpy();assert np.all(np.isfinite(w)&(w>0))
            eff=R/w[:,None,None];gain=np.linalg.solve(H@pp@H.transpose(0,2,1)+eff,H@pp).transpose(0,2,1)
            expected,raw=posterior(prior,gain,innovation,applied)
            stored=g[['x','y','psi']].to_numpy();err=errors(expected,stored);assert np.isfinite(err).all()
            ident=np.eye(3)-gain@H;post=ident@pp@ident.transpose(0,2,1)+gain@eff@gain.transpose(0,2,1);post[~applied]=pp[~applied]
            meta=dict(stage=stage,case=cid,channel=ch,range_model=rm,seed=int(seed),arm=arm,model=name)
            entry=dict(**meta,n=len(g),accepted=int(applied.sum()),rejected=int((~applied).sum()),wrap_crossings=int(np.count_nonzero(np.abs(raw[:,2]-expected[:,2])>np.pi)),posterior_x_max_m=float(err[:,0].max()),posterior_y_max_m=float(err[:,1].max()),posterior_psi_max_rad=float(err[:,2].max()),posterior_fail_rows=int(np.count_nonzero(np.any(err>TOL,axis=1))),prior_state_max=priorerr,prior_cov_max=pcerr,NIS_max=float(np.max(abs(nis-g.NIS.to_numpy()))),gate_fail_rows=gatefails,posterior_cov_max=float(np.max(abs(post-base.packP(g)))))
            groups.append(entry)
            rows=pd.DataFrame({**meta,'sample_index':k,'applied':applied,'x_expected':expected[:,0],'y_expected':expected[:,1],'psi_expected':expected[:,2],'x_stored':stored[:,0],'y_stored':stored[:,1],'psi_stored':stored[:,2],'x_error_m':err[:,0],'y_error_m':err[:,1],'psi_error_rad':err[:,2]})
            rows.to_csv(rawout,index=False,header=(total==0));total+=len(g)
        print(stage,'rows',total,flush=True)
    summary=pd.DataFrame(groups);summary.to_csv(out/'GROUP_PARITY.csv',index=False)
    checkcols=['prior_state_max','prior_cov_max','NIS_max','posterior_cov_max','posterior_x_max_m','posterior_y_max_m','posterior_psi_max_rad']
    passed=bool((summary[checkcols]<=TOL).all().all() and summary.gate_fail_rows.sum()==0)
    if not smoke: assert total==original['H4_rows'] and len(summary)==1512
    for p,h in original['source_sha256'].items():assert base.sha(p)==h,p
    receipt=dict(status='PASS' if passed else 'FAIL',rows=total,groups=len(summary),tolerance=TOL,angle_units='radians',fail_rows=int(summary.posterior_fail_rows.sum()),gate_fail_rows=int(summary.gate_fail_rows.sum()),max_errors=summary[checkcols].max().to_dict(),accepted=int(summary.accepted.sum()),rejected=int(summary.rejected.sum()),wrap_crossings=int(summary.wrap_crossings.sum()),test=test,elapsed_s=time.time()-started,source_sha256={str(Path(__file__).resolve()):base.sha(Path(__file__)),**original['source_sha256']},trace_sha256=tracehash,input_manifest_sha256=base.sha(base.INPUT/'MANIFEST.json'),outputs={p.name:base.sha(p) for p in out.iterdir()},scientific_PASS=False,scope='One-step replay from preceding saved posterior; first saved row per group excluded; final robust weights reused, not re-optimized')
    base.dump(out/'RECEIPT.json',receipt);print(json.dumps(receipt['max_errors']),receipt['status'],flush=True)
    return 0 if passed else 1

if __name__=='__main__':sys.exit(run('--smoke' in sys.argv))
