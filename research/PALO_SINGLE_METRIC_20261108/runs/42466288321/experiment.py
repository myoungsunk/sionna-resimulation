#!/usr/bin/env python3
"""One additional scalar gate at a time. Frozen nonlinear PALO replay.
No truth is passed to decide() or measured_s_slope(). Binary accept/reject only.
Existing NIS99 gate is shared. R2 is already explored: not independent validation.
"""
from __future__ import annotations
import argparse, base64, hashlib, importlib, importlib.util, io, json, math, os, sys, time, urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd

REPO='myoungsunk/sionna-resimulation'
BASE='00ba47dda323817b2d0c122494c14ba368807830'
CDREF='8894353b10f790746f32d8d82159213aad9c82a7'
CDPATH='research/PALO_MECHANISM_CD_EXEC_20261108/runs/42453921978/executed_source/common.py'
CDBLOB='d53c640f4b0f7038f15d2612d54a31b209adb582'
HREF='047cce2acb244ec2d7badc563345ccdd1f48613f'
HPATH='results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C'
LEGACYREF='b7bacb08bfaca9a1765cddd5fff819c45e3ab0d4'
LEGACYPATH='research/PALO_MOTION_CIR_RISK_20261108/runs/42462035988/matched_motion_cir_frames.csv.gz'
RS=.0081; GATE=6.6348966010212145; DEG=180/np.pi
LEVELS=('B0','L0','L1','L2')
FOLDER='research/PALO_SINGLE_METRIC_20261108'

def dump(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8')
def sha(b):return hashlib.sha256(b).hexdigest()
def blob(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def get(ref,p,expected=None):
    err=None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(f'https://raw.githubusercontent.com/{REPO}/{ref}/{p}',headers={'User-Agent':'PALO-minimal-gates'}),timeout=120) as r:b=r.read()
            assert not b.startswith(b'version https://git-lfs.github.com/spec'),f'LFS:{p}'
            if expected:assert sha(b)==expected,(p,'SHA',sha(b))
            return b
        except AssertionError:raise
        except Exception as e:err=e;time.sleep(attempt+1)
    raise RuntimeError(f'FETCH:{p}:{err}')
def common():
    p=Path('vendor/common.py');p.parent.mkdir(exist_ok=True)
    b=p.read_bytes() if p.exists() else get(CDREF,CDPATH)
    assert blob(b)==CDBLOB,'COMMON_SOURCE_CHANGED'
    p.write_bytes(b);sys.path.insert(0,str(p.parent.resolve()))
    return importlib.import_module('common')
def wrap(a):return (np.asarray(a)+np.pi)%(2*np.pi)-np.pi

def policies():
    out=[dict(id='DR',family='DR',feature='none',op='none',threshold=0.),dict(id='S4',family='S4',feature='none',op='all',threshold=0.)]
    for f in ('h_prior','h_fd1','h_candidate','h_sroot'):
        for op in ('le','ge'):
            for q in (.05,.1,.2,.3,.5,.75,1.,1.5,2.,3.):
                out.append(dict(id=f'{f}_{op}_{q:g}',family=f,feature=f,op=op,threshold=q))
    out.append(dict(id='root_exists',family='root_exists',feature='h_sroot',op='exists',threshold=0.))
    grids={'correction_deg':(.05,.1,.2,.5,1.,2.,5.),
           'nis':(.1,.25,.5,1.,2.,3.841458820694124,GATE),
           'innovation':(.01,.02,.05,.1,.15,.2,.4),
           'fp13':(1.8,2.,2.1,2.2,2.3,2.5,3.),
           'fp25':(2.5,3.,3.5,4.,5.,6.),
           'ds_tap2':(.01,.02,.05,.1,.2,.5,1.),
           'ds_time':(.01,.02,.05,.1,.2,.5)}
    for f,grid in grids.items():
        for q in grid:out.append(dict(id=f'{f}_le_{q:g}',family=f,feature=f,op='le',threshold=q))
    assert len({p['id'] for p in out})==len(out)
    return out

def raw_features(H):
    h=H[:,:,:,0];n=257;pad=np.zeros((len(h),1028,2),complex)
    win=.5-.5*np.cos(2*np.pi*np.arange(n)/(n-1))
    pad[:,:n]=h*win[None,:,None]
    pw=abs(np.fft.ifft(pad,axis=1)*n)**2
    rx=pw.max(axis=1).argmax(axis=1)
    strongest=pw[np.arange(len(pw))[:,None],np.arange(1028)[None,:],rx[:,None]]
    fp=(strongest>=.09*strongest.max(axis=1)[:,None]).argmax(axis=1)
    p=pw[np.arange(len(pw)),fp]
    s=(p[:,0]-p[:,1])/p.sum(axis=1)
    result={'s':s,'fp':fp}
    for bef,aft,name in [(4,8,'fp13'),(8,16,'fp25')]:
        o=np.arange(-bef,aft+1);ix=fp[:,None]+o
        assert ((ix>=0)&(ix<1028)).all(),'CIR_WINDOW_TRUNCATED'
        v=pw[np.arange(len(pw))[:,None],ix,:]
        w=v/v.sum(axis=1)[:,None,:]
        mu=(w*o[None,:,None]).sum(axis=1)
        result[name]=np.sqrt((w*(o[None,:,None]-mu[:,None,:])**2).sum(axis=1)).mean(axis=1)
    ds=[]
    for o in (-2,2):
        p=pw[np.arange(len(pw)),fp+o]
        ds.append(abs((p[:,0]-p[:,1])/p.sum(axis=1)-s))
    result['ds_tap2']=np.maximum(*ds)
    result['ds_time']=abs(np.r_[0,np.diff(s)])
    return result

def measured_s_slope(e,x,z):
    """Exact inversion of fixed-position, piecewise-linear angular LUT.
    Select nearest circular root to prior yaw; no GT. Missing root => unavailable.
    Used ONLY to gate an ordinary s-domain update, never to replace the measurement.
    """
    ax,ay,az=e.case['anchor'];u=x[0]-ax;v=x[1]-ay
    height=az-e.case['robot_z_m'];theta=np.arctan2(np.hypot(u,v),height)*DEG
    tx=np.arctan2(-v,u)*DEG
    t=np.clip(theta/e.dt,0,e.nt-1-1e-9);i=int(np.floor(t));ft=t-i
    a=(tx+180)/e.dp;jf=np.floor(a);j=int(jf)%e.np;fa=a-jf;j1=(j+1)%e.np
    S=e.lut
    values=((1-fa)*S[i,j,:]+fa*S[i,j1,:])*(1-ft)+((1-fa)*S[i+1,j,:]+fa*S[i+1,j1,:])*ft
    dn=np.roll(values,-1)-values
    frac=np.divide(z-values,dn,out=np.full_like(values,np.nan),where=abs(dn)>1e-14)
    ix=np.flatnonzero((frac>=-1e-12)&(frac<=1+1e-12))
    if not len(ix):return np.nan,np.nan,0,np.nan
    frac=np.clip(frac[ix],0,1)
    rx=-180+e.dp*(ix+frac)
    yaw=wrap(np.arctan2(-v,-u)-np.deg2rad(e.case['mount_deg']+rx))
    dist=abs(wrap(yaw-x[2]));a=int(np.argmin(dist));j=int(ix[a])
    slope=abs(dn[j]/np.deg2rad(e.dp))
    return float(slope),float(yaw[a]),int(len(ix)),float(dist[a]*DEG)

def observation(e,x):
    h,H=e.scalar_lut.model(x,e.case)
    return h[1:],H[1:]
def advance(e,r2,x,P,c,k):
    if not k:return x.copy(),P.copy()
    return r2.predict_one(x,P,float(c['ds_odom'][k]),float(c['dtheta_gyro'][k]),float(c['dt_s'][k]))
def candidate(e,x,P,z):
    return e.core.gaussian_update(x,P,np.array([float(z)]),lambda q:observation(e,q),np.array([[RS]]),gate_threshold=None)
def decide(policy,value,nis):
    if policy['op']=='none':return False
    if not np.isfinite(nis) or nis>GATE:return False
    if policy['op']=='all':return True
    if not np.isfinite(value):return False
    if policy['op']=='exists':return True
    if policy['op']=='le':return bool(value<=policy['threshold'])
    if policy['op']=='ge':return bool(value>=policy['threshold'])
    raise ValueError(policy)

def prepare():
    c=common();out=Path('shared');out.mkdir(exist_ok=True)
    c.download_inputs(Path('cache'),out)
    e=c.Engine(Path('cache'));r2=importlib.import_module('r2_bias_replay')
    pp=policies();dump(out/'POLICIES.json',pp)
    dump(out/'CONTRACT.json',dict(question='Single additional indicator; exact own-state nonlinear closed loop',
      policies=len(pp),channels=['los','full'],bias_levels=list(LEVELS),frames=979,
      full_eval='t>=40',development='40<=t<120',test='t>=140',gap='120<=t<140',
      selection='One common threshold/direction per family minimizing worst joint H/XY ratio vs DR across four Full levels on development only. Threshold sweep is exploratory; test never used for selection.',
      gate='all methods share original scalar NIS99 except DR; no truth in gate; no new ML; no alpha scaling',
      measured_s='nearest exact inverse root at own predicted position, circular prior branch; no root means reject; root_exists is control',
      labels='truth only for post-hoc metrics, LoS only for diagnostic pairing, never policy input',
      data_limit='same previously explored R2 route/seed; simulated noise-free RF, not hardware CIR',
      original_refs=dict(CD=CDREF,input=c.INPUT_SHA),old_cir_join_error='k-200 into 979-frame RF table; corrected to k/pose_id'))
    parity=[]
    for ch in ('los','full'):
      for lv in LEVELS:
        control=e.controls[ch,lv];original=e.original[ch,lv]
        for mode,j in [('S4',3),('DR',1)]:
          x,P=e.initial(ch,lv);errs=[0.,0.,0.];status_diff=0
          for k,z in enumerate(e.trace[ch]['z_s']):
            xm,Pm=advance(e,r2,x,P,control,k)
            if mode=='S4':
                xu,Pu,d=candidate(e,xm,Pm,z);a=d['NIS']<=GATE
                x,P=(xu,Pu) if a else (xm,Pm)
                errs[2]=max(errs[2],abs(float(d['NIS'])-float(original['nis'][k,j])))
                status_diff+=int(a!=(original['status'][k,j]=='APPLIED'))
            else:x,P=xm,Pm
            errs[0]=max(errs[0],float(abs(x-original['estimate'][k,j]).max()))
            errs[1]=max(errs[1],float(abs(P-original['covariance'][k,j]).max()))
          record=dict(channel=ch,level=lv,policy=mode,state=errs[0],cov=errs[1],nis=errs[2],mask=status_diff)
          parity.append(record);dump(out/'BASELINE_PARITY.json',parity)
          assert errs[0]<1e-7 and errs[1]<1e-8 and errs[2]<1e-7 and status_diff==0,record
          print('BASELINE_PARITY',record,flush=True)
    source=[('full',f'{HPATH}/FULL_RF/H_R2_aB_m0.npy','b3b4c61e23286b86c78b6e87f5b9b5358121cbde7717bae73e5650cc900b546c'),
            ('los',f'{HPATH}/H_LoS_R2_aB_m0.npy','811bdfb1b152839f85c6378faafc0f94619601416084a0995f2d79caa997c467')]
    pos=e.trace['full']['pose_id'].astype(int)
    samples=json.loads(get(HREF,f'{HPATH}/R2_aB_m0/SAMPLES.json','35af279692a15dc429263f88cfbb4db949c1260cb7cf9d9e0c292172a7505b0e'))
    coords=np.array([[samples[j]['x'],samples[j]['y'],np.deg2rad(samples[j]['yaw_body_deg'])] for j in pos])
    assert abs(coords[:,:2]-e.truth[:,:2]).max()<1e-6
    assert abs(wrap(coords[:,2]-e.truth[:,2])).max()*DEG<1e-6
    rf={};rf_receipt=[]
    for ch,path,hs in source:
        b=get(HREF,path,hs);H=np.load(io.BytesIO(b),allow_pickle=False)
        assert H.shape==(1303,257,2,2)
        rf[ch]=raw_features(H[pos]);err=float(abs(rf[ch]['s']-e.trace[ch]['z_s']).max())
        assert err<1e-12,('CIR_S_PARITY',ch,err)
        np.savez_compressed(out/f'rf_{ch}.npz',**rf[ch],k=np.arange(979),pose_id=pos,t=e.t)
        rf_receipt.append(dict(ch=ch,sha256=hs,bytes=len(b),s_parity=err))
    dump(out/'RF_PROVENANCE.json',rf_receipt)
    oldb=get(LEGACYREF,LEGACYPATH,'35264bf410a464e73a5a2b740cade6aa618c44853987b13f8e7ce12645906ac5')
    old=pd.read_csv(io.BytesIO(oldb),compression='gzip');k=old.k.to_numpy(int)
    assert np.array_equal(old.pose_id.to_numpy(int),pos[k])
    audit=[]
    correct={'fp_spread_primary':rf['full']['fp13'],'fp_spread_wide':rf['full']['fp25'],
       'delta_s_tap_absmax2':rf['full']['ds_tap2'],
       'oracle_delta_s_full_minus_los':rf['full']['s']-rf['los']['s']}
    for name,arr in correct.items():
        legacy_err=float(abs(old[name].to_numpy()-arr[k-200]).max())
        current_err=float(abs(old[name].to_numpy()-arr[k]).max())
        assert legacy_err<1e-10,(name,legacy_err)
        audit.append(dict(column=name,legacy_matches_k_minus_200_max_error=legacy_err,current_misalignment_max=current_err))
        old[name]=arr[k]
    old['abs_oracle_delta_s']=abs(old.oracle_delta_s_full_minus_los)
    old.to_csv(out/'corrected_selected_rf_fields.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    b=old.query('level=="B0" and donor=="s4"')
    bad=b[b.ref_head_harm_gt05]
    dump(out/'ALIGNMENT_ERRATUM.json',dict(status='CONFIRMED_200_FRAME_40_SECOND_JOIN_BUG',
        affected_columns=audit,original_rows=len(old),original_report_cir_auc_withdrawn=True,
        unaffected='motion-only statistics and original LUT Hpsi features; RF-derived fields/classifiers and cross-target claims invalidated',
        correct_RF_gt01=int((b.abs_oracle_delta_s>.1).sum()),
        candidate_harm_gt05=len(bad),actual_accepted_harm_gt05=int(bad.gate_eligible.sum()),
        corrected_harm_events=bad[['k','t','gate_eligible','abs_oracle_delta_s','fp_spread_primary','fp_spread_wide']].to_dict('records')))
    root_checks=[]
    for lv in LEVELS:
        for k in range(0,979,49):
            x=e.saved[lv,'s4']['prior_X'][k];z=float(observation(e,x)[0][0])
            g,psi,n,dist=measured_s_slope(e,x,z)
            assert np.isfinite(g) and dist<1e-6,(lv,k,dist)
            y=x.copy();y[2]=psi;res=abs(float(observation(e,y)[0][0])-z)
            assert res<1e-10,res
            root_checks.append(res)
    dump(out/'ROOT_MATH_QA.json',dict(exact_forward_inverse_checks=len(root_checks),max_residual=max(root_checks),
       fallback='no inverse root => reject, counted; no synthetic replacement root'))
    dump(out/'PREPARE_PASS.json',dict(baseline_cases=16,rf_frames=979,policies=len(pp)))

def run_case(ch,lv):
    c=common();e=c.Engine(Path('cache'));r2=importlib.import_module('r2_bias_replay')
    out=Path('cases');out.mkdir(exist_ok=True);assert Path('shared/PREPARE_PASS.json').exists()
    pp=json.loads(Path('shared/POLICIES.json').read_text());N=len(e.t);M=len(pp)
    rf=dict(np.load(f'shared/rf_{ch}.npz',allow_pickle=False))
    assert np.array_equal(rf['k'],np.arange(N)) and np.array_equal(rf['pose_id'],e.trace[ch]['pose_id'])
    X=np.zeros((N,M,4));P=np.zeros((N,M,4,4));accepted=np.zeros((N,M),bool)
    nis=np.zeros((N,M));scores=np.full((N,M),np.nan);steps=np.zeros((N,M,4))
    prior_x=np.zeros((N,M,4));root_distance=np.full((N,M),np.nan);root_count=np.full((N,M),-1,np.int16)
    harm_h=np.zeros((N,M),bool);harm_xy=np.zeros((N,M),bool)
    controls=e.controls[ch,lv];zs=e.trace[ch]['z_s'];root_err=0.;positive_min=1e99;scalar_rechecks=0
    for m,policy in enumerate(pp):
        x,p=e.initial(ch,lv)
        for k in range(N):
            xm,pm=advance(e,r2,x,p,controls,k)
            xu,pu,d=candidate(e,xm,pm,zs[k]);n=float(d['NIS']);feature=policy['feature']
            dx=xu-xm;dx[2]=wrap(dx[2])
            if feature=='h_prior':v=abs(float(d['H'][0,2]))
            elif feature=='h_fd1':
                a=xm.copy();b=xm.copy();a[2]+=np.deg2rad(1.);b[2]-=np.deg2rad(1.)
                v=abs(float(observation(e,a)[0][0]-observation(e,b)[0][0]))/np.deg2rad(2.)
            elif feature=='h_candidate':v=abs(float(observation(e,xu)[1][0,2]))
            elif feature=='h_sroot':
                v,root,nr,dist=measured_s_slope(e,xm,float(zs[k]));root_count[k,m]=nr;root_distance[k,m]=dist
                if nr and k%53==0:
                    y=xm.copy();y[2]=root;er=abs(float(observation(e,y)[0][0])-zs[k]);root_err=max(root_err,er)
                    assert er<1e-9,('root',ch,lv,k,policy['id'],er)
            elif feature=='correction_deg':v=abs(float(dx[2]))*DEG
            elif feature=='nis':v=n
            elif feature=='innovation':v=abs(float(d['innovation'][0]))
            elif feature in rf:v=float(rf[feature][k])
            elif feature=='none':v=0.
            else:raise RuntimeError(feature)
            use=decide(policy,v,n);x,p=(xu,pu) if use else (xm,pm)
            assert np.isfinite(x).all() and np.isfinite(p).all()
            eig=float(np.linalg.eigvalsh(p).min());positive_min=min(positive_min,eig)
            assert eig>0 and abs(p-p.T).max()<1e-10
            if (k*13+m)%211==0:
                if k:rx,rp=advance(e,r2,X[k-1,m],P[k-1,m],controls,k)
                else:rx,rp=e.initial(ch,lv)
                ux,up,ud=candidate(e,rx,rp,zs[k]);ex,ep=(ux,up) if use else (rx,rp)
                assert abs(x-ex).max()<1e-11 and abs(p-ep).max()<1e-11
                scalar_rechecks+=1
            X[k,m]=x;P[k,m]=p;accepted[k,m]=use;nis[k,m]=n;scores[k,m]=v;steps[k,m]=dx;prior_x[k,m]=xm
            # Offline labels below cannot affect any future policy decision.
            gt=e.truth[k];err0=abs(float(wrap(xm[2]-gt[2])))*DEG;err1=abs(float(wrap(xu[2]-gt[2])))*DEG
            harm_h[k,m]=err1-err0>.5
            harm_xy[k,m]=np.linalg.norm(xu[:2]-gt[:2])-np.linalg.norm(xm[:2]-gt[:2])>.01
        print('POLICY',ch,lv,m+1,M,policy['id'],'accept',int(accepted[:,m].sum()),flush=True)
    for name,j in [('S4',3),('DR',1)]:
        m=next(i for i,p in enumerate(pp) if p['id']==name);ref=e.original[ch,lv]
        difx=float(abs(X[:,m]-ref['estimate'][:,j]).max());difp=float(abs(P[:,m]-ref['covariance'][:,j]).max())
        assert difx<1e-7 and difp<1e-8,('BASELINE',ch,lv,name,difx,difp)
        if name=='S4':
            assert abs(nis[:,m]-ref['nis'][:,j]).max()<1e-7
            assert np.array_equal(accepted[:,m],ref['status'][:,j]=='APPLIED')
    err=X[:,:,:3]-e.truth[:,None,:];err[:,:,2]=wrap(err[:,:,2])
    eh=err[:,:,2]*DEG;xy=np.linalg.norm(err[:,:,:2],axis=2)
    hn=err[:,:,2]**2/P[:,:,2,2]
    xn=np.einsum('nmi,nmi->nm',err[:,:,:2],np.linalg.solve(P[:,:,:2,:2],err[:,:,:2,None])[...,0])
    metrics=[]
    masks={'all_eval':e.t>=40,'development':(e.t>=40)&(e.t<120),'late_test':e.t>=140}
    for window,mask in masks.items():
        for m,p in enumerate(pp):
            a=accepted[mask,m]
            metrics.append(dict(channel=ch,level=lv,window=window,**p,n=int(mask.sum()),
                heading_rmse_deg=float(np.sqrt(np.mean(eh[mask,m]**2))),xy_rmse_m=float(np.sqrt(np.mean(xy[mask,m]**2))),
                head95=float(np.mean(hn[mask,m]<=3.841458820694124)),xy95=float(np.mean(xn[mask,m]<=5.991464547107979)),
                head_nees=float(np.mean(hn[mask,m])),xy_nees=float(np.mean(xn[mask,m])),
                head_q95_deg=float(np.quantile(abs(eh[mask,m]),.95)),xy_q95_m=float(np.quantile(xy[mask,m],.95)),
                accepted=int(a.sum()),accepted_all=int(accepted[:,m].sum()),
                candidate_head_losses=int(harm_h[mask,m].sum()),accepted_head_losses=int((harm_h[mask,m]&a).sum()),
                accepted_xy_losses=int((harm_xy[mask,m]&a).sum()),
                missing_score=int(np.count_nonzero(~np.isfinite(scores[mask,m])))))
    pd.DataFrame(metrics).to_csv(out/f'{ch}_{lv}_metrics.csv',index=False)
    np.savez_compressed(out/f'{ch}_{lv}_trajectories.npz',X=X,P=P,prior_X=prior_x,step=steps,nis=nis,
        accepted=accepted,score=scores,root_count=root_count,root_distance_deg=root_distance,t=e.t,truth=e.truth,
        pose_id=e.trace[ch]['pose_id'],policies=np.array([p['id'] for p in pp]),harm_h=harm_h,harm_xy=harm_xy)
    dump(out/f'{ch}_{lv}_QA.json',dict(status='EXACT_SCALAR_CLOSED_LOOP_PASS',policies=M,steps=N*M,
        min_P_eigenvalue=positive_min,root_forward_max_error=root_err,scalar_transition_rechecks=scalar_rechecks,
        selector_truth_dependency=False))

def aggregate():
    out=Path('release');out.mkdir(exist_ok=True)
    for p in Path('shared').glob('*'):
        if p.is_file():(out/p.name).write_bytes(p.read_bytes())
    frames=[];qas=[]
    for ch in ('los','full'):
      for lv in LEVELS:
        stem=f'{ch}_{lv}';p=Path('cases')/f'{stem}_metrics.csv';df=pd.read_csv(p);frames.append(df)
        qa=json.loads((Path('cases')/f'{stem}_QA.json').read_text());qas.append(dict(channel=ch,level=lv,**qa))
        with np.load(Path('cases')/f'{stem}_trajectories.npz',allow_pickle=False) as a:
            err=wrap(a['X'][:,:,2]-a['truth'][:,None,2])*DEG;xy=np.linalg.norm(a['X'][:,:,:2]-a['truth'][:,None,:2],axis=2)
            mask=a['t']>=40
            for j,name in enumerate(a['policies']):
                rec=df[(df.id==name)&(df.window=='all_eval')].iloc[0]
                assert abs(float(np.sqrt(np.mean(err[mask,j]**2)))-rec.heading_rmse_deg)<1e-9
                assert abs(float(np.sqrt(np.mean(xy[mask,j]**2)))-rec.xy_rmse_m)<1e-9
                assert int(a['accepted'][mask,j].sum())==rec.accepted
                # Direct circular error increment must match stored accepted loss count.
                pre=abs(wrap(a['prior_X'][:,:,2]-a['truth'][:,None,2]))*DEG
                real_harm=(abs(err)-pre>.5)&a['accepted']
                assert int(real_harm[mask,j].sum())==rec.accepted_head_losses
        for file in Path('cases').glob(stem+'_*'):
            if file.is_file():(out/file.name).write_bytes(file.read_bytes())
    full=pd.concat(frames,ignore_index=True)
    for reference in ('DR','S4'):
        base=full[full.id==reference].set_index(['channel','level','window'])
        key=pd.MultiIndex.from_frame(full[['channel','level','window']])
        full[f'h_ratio_{reference}']=full.heading_rmse_deg.to_numpy()/base.loc[key,'heading_rmse_deg'].to_numpy()
        full[f'xy_ratio_{reference}']=full.xy_rmse_m.to_numpy()/base.loc[key,'xy_rmse_m'].to_numpy()
        full[f'both_better_{reference}']=(full[f'h_ratio_{reference}']<1-1e-9)&(full[f'xy_ratio_{reference}']<1-1e-9)
    full.to_csv(out/'ALL_METRICS.csv',index=False)
    dev=full[(full.channel=='full')&(full.window=='development')]
    devscore=dev.groupby(['family','id'],sort=False).agg(worst_h=('h_ratio_DR','max'),worst_xy=('xy_ratio_DR','max'),total_accept=('accepted','sum')).reset_index()
    devscore['worst_joint']=devscore[['worst_h','worst_xy']].max(axis=1)
    chosen=devscore.sort_values(['worst_joint','total_accept','id'],ascending=[True,True,True]).groupby('family',sort=False).head(1)
    chosen.to_csv(out/'DEV_FROZEN_SELECTION.csv',index=False)
    selected=full[full.id.isin(chosen.id)].copy();selected.to_csv(out/'SELECTED_ALL_WINDOWS.csv',index=False)
    paired=[]
    for policy,group in full[(full.channel=='full')&(full.window=='all_eval')].groupby('id'):
        paired.append(dict(id=policy,family=group.family.iloc[0],h_worst_vs_dr=group.h_ratio_DR.max(),xy_worst_vs_dr=group.xy_ratio_DR.max(),
          levels_both_better_dr=int(group.both_better_DR.sum()),levels_both_better_s4=int(group.both_better_S4.sum()),
          b0_heading=float(group[group.level=='B0'].heading_rmse_deg.iloc[0]),b0_xy=float(group[group.level=='B0'].xy_rmse_m.iloc[0]),
          l2_heading=float(group[group.level=='L2'].heading_rmse_deg.iloc[0]),l2_xy=float(group[group.level=='L2'].xy_rmse_m.iloc[0])))
    pd.DataFrame(paired).to_csv(out/'EXPLORATORY_SWEEP_COMPARISON.csv',index=False)
    dump(out/'VERIFICATION.json',dict(status='ALL_CASES_AND_SAVED_ARRAY_METRICS_PASS',cases=qas,
        result_rows=len(full),policy_count=int(full.id.nunique()),all_trajectories=8*int(full.id.nunique()),
        original_cir_join_bug_corrected=True,independent_science_audit=False,new_policy_closed_loop=True,
        calibration_claim=False,held_out_environment=False))
    lines=['# PALO single-metric closed-loop experiment','',
        'One scalar gate per policy, original NIS gate shared. Exact own-state X/P nonlinear replay.',
        'R2 and seed0 only. Same-route development/test, all thresholds reported, not production validation.','',
        '## Important correction',
        'Previous RF/CIR pairing used k-200 on a 979-frame RF array. Current analysis joins by absolute k and checks pose_id; previous CIR AUC and small-RF/large-harm claims are withdrawn. Motion-only and original Hpsi arrays were not shifted.','',
        '## Development-selected policy per family (thresholds NOT chosen on late test)',
        chosen.to_string(index=False),'',
        '## Full late test results for those fixed policies',
        selected[(selected.channel=='full')&(selected.window=='late_test')][['level','id','heading_rmse_deg','xy_rmse_m','accepted','head95','xy95','both_better_DR']].to_string(index=False),
        '', 'See ALL_METRICS.csv and all trajectories for the full exploratory sweep.']
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n')
    (out/'experiment.py').write_bytes(Path(__file__).read_bytes())
    manifest={p.name:dict(bytes=p.stat().st_size,sha256=sha(p.read_bytes())) for p in out.iterdir() if p.is_file()}
    dump(out/'OUTPUT_SHA256.json',manifest)
    print('SUMMARY',json.dumps(dict(policies=int(full.id.nunique()),trajectories=8*int(full.id.nunique()),
      dev_selected=chosen[['family','id','worst_joint']].to_dict('records'))),flush=True)

def publish():
    token=os.environ['GITHUB_TOKEN'];branch=os.environ['TARGET_BRANCH'];apiroot=f'https://api.github.com/repos/{REPO}'
    def api(path,method='GET',payload=None):
        data=None if payload is None else json.dumps(payload).encode()
        hdr={'Authorization':f'Bearer {token}','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'PALO-single-metric'}
        if data is not None:hdr['Content-Type']='application/json'
        err=None
        for attempt in range(4):
            try:
                with urllib.request.urlopen(urllib.request.Request(apiroot+path,data=data,headers=hdr,method=method),timeout=180) as r:return json.load(r)
            except Exception as e:err=e;time.sleep(1+attempt)
        raise RuntimeError(f'API:{path}:{err}')
    ref='/git/ref/heads/'+branch.replace('/','%2F')
    parent=api(ref)['object']['sha'];assert parent==os.environ['GITHUB_SHA'],'CONCURRENT_BRANCH_CHANGE'
    base=api('/git/commits/'+parent)['tree']['sha'];entries=[]
    prefix=f'{FOLDER}/runs/{os.environ["GITHUB_RUN_ID"]}'
    for p in sorted(Path('release').iterdir()):
        if p.is_file():
            b=p.read_bytes();obj=api('/git/blobs','POST',dict(content=base64.b64encode(b).decode(),encoding='base64'))
            assert obj['sha']==blob(b)
            entries.append(dict(path=f'{prefix}/{p.name}',mode='100644',type='blob',sha=obj['sha']))
    tree=base
    for i in range(0,len(entries),12):tree=api('/git/trees','POST',dict(base_tree=tree,tree=entries[i:i+12]))['sha']
    commit=api('/git/commits','POST',dict(message='Publish parity-verified single-indicator nonlinear closed-loop sweep and corrected CIR pairing',tree=tree,parents=[parent]))['sha']
    assert api(ref)['object']['sha']==parent,'CONCURRENT_WRITE_BEFORE_PUSH'
    api('/git/refs/heads/'+branch.replace('/','%2F'),'PATCH',dict(sha=commit,force=False))
    assert api(ref)['object']['sha']==commit
    print('PUBLISHED',commit,'FILES',len(entries),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['prepare','case','aggregate']);ap.add_argument('--channel',choices=['los','full']);ap.add_argument('--level',choices=LEVELS);ap.add_argument('--publish',action='store_true');a=ap.parse_args()
    if a.mode=='prepare':prepare()
    elif a.mode=='case':run_case(a.channel,a.level)
    else:
        aggregate()
        if a.publish:publish()
