import json, hashlib, itertools, sys
from pathlib import Path
from math import radians
import numpy as np

base = Path(__file__).resolve().parents[1]
frozen = base/'inputs/experiments/POL_FGO_CORR_20261106_v1/frozen/repo'
sys.path.insert(0,str(frozen/'research/EKF4_RANGE_S_STAGED_20261014'))
from p3_rf_adapter4 import FrozenLut

sha=lambda b:hashlib.sha256(b).hexdigest()
manifest=json.loads((base/'INPUT_MANIFEST.json').read_bytes())
for rec in manifest['files']:
    content=(base/'inputs'/rec['path'].split('research/POL_HEADING_RESEARCH_20261107/',1)[1]).read_bytes()
    assert len(content)==rec['bytes'] and sha(content)==rec['sha256']
    assert hashlib.sha1(b'blob '+str(len(content)).encode()+b'\0'+content).hexdigest()==rec['git_blob']
hashes=json.loads((base/'OUTPUT_SHA256.json').read_bytes())
for path,digest in hashes.items():
    assert sha((base/path).read_bytes())==digest, path
print('provenance',manifest['commit'],len(manifest['files']),len(hashes),flush=True)
for p in [base/'INPUT_MANIFEST.json',base/'OUTPUT_SHA256.json',base/'run_exact.py',base/'source/palo_oracle_closedloop.py',base/'results_v2/SUMMARY.json',base/'inputs/governance/COMMON_CONTRACT.md',base/'audit/ROLE_AUDITOR.md']:
    print(p.name,sha(p.read_bytes()),flush=True)
out=base/'results_v2'
reports=json.loads((out/'SUMMARY.json').read_bytes())['metrics']
summary={(r['channel'],r['level'],r['policy']):r for r in reports}
policies=('dr','s4','oracle_heading','oracle_xy','oracle_both','oracle_heading_gate','oracle_both_gate')
keys=set(itertools.product(('los','full'),('B0','L0','L1','L2'),policies))
assert len(summary)==len(reports)==56 and keys==set(summary)
assert set(out.glob('*.npz'))=={out/f'{a}_{b}_{c}.npz' for a,b,c in keys}
lut=FrozenLut(frozen)
case=next(r for r in json.loads((frozen/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_bytes())['cases'] if r['id']=='R2_aB_m0')

def wrap(y):
    return (y+np.pi)%(2*np.pi)-np.pi

def motion(previous, cov, ds, gyro, dt):
    a=gyro-previous[:,3]*dt
    w=np.sinc(a/(2*np.pi))
    deriv=np.empty_like(a)
    small=np.abs(a)<1e-3
    aa=a[small]
    deriv[small]=-aa/12+aa**3/480-aa**5/53760
    aa=a[~small]/2
    deriv[~small]=(aa*np.cos(aa)-np.sin(aa))/(2*aa**2)
    t=previous[:,2]+a/2
    unit=np.stack([np.cos(t),np.sin(t)],axis=1)
    perp=lambda x: np.stack([-x[:,1],x[:,0]],axis=1)
    dx=ds[:,None]*w[:,None]*unit
    dturn=ds[:,None]*(deriv[:,None]*unit+w[:,None]*perp(unit)/2)
    predicted=previous.copy()
    predicted[:,:2]+=dx
    predicted[:,2]=wrap(previous[:,2]+a)
    F=np.repeat(np.eye(4)[None,:,:],len(a),axis=0)
    F[:,:2,2]=perp(dx)
    F[:,:2,3]=-dt[:,None]*dturn
    F[:,2,3]=-dt
    G=np.zeros((len(a),4,2))
    G[:,:2,0]=w[:,None]*unit
    G[:,:2,1]=dturn
    G[:,2,1]=1.
    q=np.stack([2e-5*np.abs(ds),radians(.015)**2*dt],axis=1)
    return predicted, F@cov@F.transpose(0,2,1)+(G*q[:,None,:])@G.transpose(0,2,1)

tols=dict(prior_X=1e-12,prior_P=1e-12,candidate_X=1e-12,candidate_P=1e-12,nis=1e-11,metric=1e-11,s4_X=1e-7,s4_P=1e-8,s4_nis=1e-7,dr_X=1e-7,dr_P=1e-8)
maxima={}
def compare(k,a,b):
    assert np.shape(a)==np.shape(b), (k,np.shape(a),np.shape(b))
    d=float(np.max(np.abs(a-b)))
    assert np.isfinite(d) and d<=tols[k],(k,d)
    maxima[k]=max(maxima.get(k,0),d)

first=None
min_eig=float('inf')
n=0
min_gain={}
gate_diff={}
max_geotheta=-np.inf
for ch,lv,p in sorted(keys):
    frame_dir=base/'inputs/inputs/original_run'
    with np.load(frame_dir/'verified_inputs'/f'R2_aB_m0_{ch}_seed0_ONE_STEP.npz',allow_pickle=False) as data:
        t,pose,truth,z,detected=(data[k] for k in ('t_s','pose_id','truth_for_offline_scoring_only','z_s','detected'))
    if first is None:
        first=(t,pose,truth)
    assert all(np.array_equal(i,j) for i,j in zip(first,(t,pose,truth)))
    assert len(t)==len(np.unique(pose))==979 and np.all(np.diff(t)>0)
    assert detected.all() and np.isfinite(z).all()
    with np.load(base/'inputs/experiments/POL_FGO_CORR_20261106_v1/outputs'/f'controls_{ch}_{lv}.npz',allow_pickle=False) as controls, np.load(out/f'{ch}_{lv}_{p}.npz',allow_pickle=False) as a:
        prior,pc,cand,cc,x,c,nis,yes=(a[k] for k in ('prior_X','prior_P','candidate_X','candidate_P','X','P','nis','accepted'))
        assert all(np.array_equal(a[k],q) for k,q in (('t',t),('pose_id',pose),('truth',truth),('R',[[.0081]])))
        assert np.array_equal(t,controls['t_s'])
        assert np.allclose(np.diff(t),controls['dt_s'][1:],rtol=0,atol=1e-12)
        assert prior.shape==cand.shape==x.shape==(979,4)
        assert pc.shape==cc.shape==c.shape==(979,4,4)
        assert nis.shape==yes.shape==(979,) and yes.dtype==np.bool_
        assert np.array_equal(prior[0],np.r_[controls['initial_pose'],0.])
        assert np.array_equal(pc[0],np.diag([.1**2,.1**2,radians(5)**2,radians(.1)**2]))
        pred, pp = motion(x[:-1],c[:-1],*(controls[k][1:] for k in ('ds_odom','dtheta_gyro','dt_s')))
        compare('prior_X',pred,prior[1:])
        compare('prior_P',pp,pc[1:])
        for v in (pc,cc,c):
            assert np.allclose(v,v.transpose(0,2,1),atol=1e-14,rtol=0)
            e0=float(np.linalg.eigvalsh(v).min())
            assert e0>0
            min_eig=min(min_eig,e0)
        measurements=[lut.model(q,case) for q in prior]
        max_geotheta=max(max_geotheta,float(np.degrees(np.arctan2(np.linalg.norm(prior[:,:2]-case['anchor'][:2],axis=1),case['anchor'][2]-case['robot_z_m'])).max()))
        h=np.array([q[0][1] for q in measurements])
        H=np.array([q[1][1] for q in measurements])
        innovation=z-h
        ph=np.einsum('nij,nj->ni',pc,H)
        innovation_var=np.einsum('ni,ni->n',ph,H)+.0081
        gain=ph/innovation_var[:,None]
        updated=prior+gain*innovation[:,None]
        updated[:,2]=wrap(updated[:,2])
        updated_cov=pc-gain[:,:,None]*ph[:,None,:]
        calculated_nis=innovation**2/innovation_var
        compare('candidate_X',updated,cand)
        compare('candidate_P',updated_cov,cc)
        compare('nis',calculated_nis,nis)
        def errors(v):
            residual=v[:,:3]-truth
            residual[:,2]=wrap(residual[:,2])
            return residual, np.sqrt(np.sum(residual[:,:2]**2,axis=1))
        pre,rpre=errors(prior)
        post,rpost=errors(cand)
        head_good=np.abs(pre[:,2])-np.abs(post[:,2])>1e-12
        xy_good=rpre-rpost>1e-12
        g=calculated_nis<=6.6348966010212145
        expected={'dr':np.zeros(979,dtype=bool),'s4':g,'oracle_heading':head_good,'oracle_xy':xy_good,
                  'oracle_both':head_good&xy_good,'oracle_heading_gate':head_good&g,'oracle_both_gate':head_good&xy_good&g}[p]
        assert np.array_equal(yes,expected),(ch,lv,p)
        assert np.array_equal(x[yes],cand[yes]) and np.array_equal(x[~yes],prior[~yes])
        assert np.array_equal(c[yes],cc[yes]) and np.array_equal(c[~yes],pc[~yes])
        if p in ('s4','dr'):
            with np.load(frame_dir/'results/replay'/f'R2_aB_m0_{ch}_{lv}_seed0_recursive.npz',allow_pickle=False) as old:
                j=list(old['names']).index({'s4':'S4','dr':'DR4'}[p])
                assert np.array_equal(t,old['t_s']) and np.array_equal(pose,old['pose_id'])
                compare(p+'_X',x,old['estimate'][:,j])
                compare(p+'_P',c,old['covariance'][:,j])
                if p=='s4':
                    compare('s4_nis',nis,old['nis'][:,j])
                    assert np.array_equal(old['status'][:,j],np.where(yes,'APPLIED','REJECT'))
                else:
                    assert np.all(old['status'][:,j]=='DR_ONLY')
        take=t>=40
        e,r=errors(x)
        e,r=e[take],r[take]
        u=c[take]
        nees_h=e[:,2]**2/u[:,2,2]
        A,B,D=u[:,0,0],u[:,0,1],u[:,1,1]
        nees_xy=(D*e[:,0]**2-2*B*e[:,0]*e[:,1]+A*e[:,1]**2)/(A*D-B**2)
        metrics=dict(n=len(e),heading_rmse_deg=np.degrees(np.sqrt(np.mean(e[:,2]**2))),xy_rmse_m=np.sqrt(np.mean(r**2)),heading_nees=nees_h.mean(),xy_nees=nees_xy.mean(),heading_95_coverage=(nees_h<=3.841458820694124).mean(),xy_95_coverage=(nees_xy<=5.991464547107979).mean(),heading_sigma_rms_deg=np.degrees(np.sqrt(u[:,2,2].mean())),xy_sigma_rms_m=np.sqrt((A+D).mean()),applied=yes[take].sum(),applied_all=yes.sum(),heading_p95_deg=np.percentile(np.abs(np.degrees(e[:,2])),95),xy_p95_m=np.percentile(r,95),min_cov_eigenvalue=np.linalg.eigvalsh(c).min())
        assert metrics['n']==779
        for field,value in metrics.items(): compare('metric',value,summary[ch,lv,p][field])
        n+=len(t)
        if p in ('oracle_heading','oracle_both'):
            with np.load(out/f'{ch}_{lv}_{p}_gate.npz',allow_pickle=False) as gated:
                gate_diff[ch,lv,p]=np.count_nonzero(gated['accepted']!=yes)
print('counts',len(keys),n,56*779)
print('max_abs_differences',maxima)
print('min_eig_prior_candidate_posterior',min_eig)
print('max_theta',max_geotheta,'lut_max',lut.theta.max())
print('gate_mask_difference',gate_diff)
for lv in ('B0','L0','L1','L2'):
 for p in ('s4','dr','oracle_heading','oracle_xy','oracle_both'):
  m=summary['full',lv,p]
  print(lv,p,*(round(m[k],6) for k in ('heading_rmse_deg','xy_rmse_m','heading_nees','xy_nees','heading_95_coverage','xy_95_coverage','heading_sigma_rms_deg','applied')))
