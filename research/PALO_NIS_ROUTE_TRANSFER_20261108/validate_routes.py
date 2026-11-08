#!/usr/bin/env python3
"""Frozen scalar PALO NIS threshold transfer: R2 / R4 / R5.
No new Sionna simulation, no parameter tuning, no truth in the estimator.
Checks R2 original S4 and DR parity; same frozen LoS LUT and motion model in
all cases. All route cases are 5 Hz and are already-public development scenes.
Only fixed policies: DR, S4 chi2_1(0.99), NIS<=0.5, NIS<=2.
"""
from __future__ import annotations
import argparse, csv, hashlib, importlib, io, json, math, os, sys, time, base64
import urllib.request
from pathlib import Path
import numpy as np
import pandas as pd

REPO='myoungsunk/sionna-resimulation'
RF_REF='047cce2acb244ec2d7badc563345ccdd1f48613f'
RF_DIR='results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C'
CASE_IDS=('R2_aA_m0','R2_aA_m45','R2_aB_m0',
          'R4_aA_m0','R4_aB_m0','R5_aA_m0','R5_aB_m0')
LEVELS={'B0':0.0,'L0':.01,'L1':.05,'L2':.2}
POLICIES={'DR':None,'S4':6.6348966010212145,'NIS_0p5':.5,'NIS_2':2.}
DEG=180./np.pi
C1=3.841458820694124
C2=5.991464547107979
OUT=Path('case-results')
OUT.mkdir(parents=True,exist_ok=True)
INPUTS=[]

def wrap(a):return (np.asarray(a)+np.pi)%(2*np.pi)-np.pi
def sha(b):return hashlib.sha256(b).hexdigest()
def rget(path,expected=None):
    last=None
    for i in range(4):
        try:
            u=f'https://raw.githubusercontent.com/{REPO}/{RF_REF}/{path}'
            req=urllib.request.Request(u,headers={'User-Agent':'PALO-route-transfer'})
            with urllib.request.urlopen(req,timeout=120) as r:b=r.read()
            if b.startswith(b'version https://git-lfs.github.com/spec'):raise AssertionError('LFS_POINTER_'+path)
            if expected and sha(b)!=expected:raise AssertionError('SHA_MISMATCH_'+path)
            INPUTS.append(dict(ref=RF_REF,path=path,bytes=len(b),sha256=sha(b)))
            return b
        except AssertionError:raise
        except Exception as e:
            last=e;time.sleep(i+1)
    raise RuntimeError('REMOTE_FETCH_FAILED '+path+' '+repr(last))
def exact_source():
    cache=Path('cache')
    assert (cache/'pol/experiments/POL_FGO_CORR_20261106_v1/frozen/repo').exists(),'ORIGINAL_PALO_FROZEN_FILES_MISSING'
    assert Path('vendor/common.py').exists(),'VERIFIED_FROZEN_COMMON_MISSING'
    sys.path.insert(0,str(Path('vendor').resolve()))
    import common
    assert common.INPUT_SHA=='4c43020f04fbbf7d0510f792c4ab99a1d9f5ddb5'
    eng=common.Engine(cache)
    frozen=cache/'pol/experiments/POL_FGO_CORR_20261106_v1/frozen/repo'
    sys.path.insert(0,str((frozen/'research/EKF4_RANGE_S_STAGED_20261014').resolve()))
    import r2_bias_replay as r2
    return eng,r2

def extract_observations(raw):
    assert raw.ndim==4 and raw.shape[1:]==(257,2,2)
    sig=raw[:,:,:,0];n=257
    window=.5-.5*np.cos(2*np.pi*np.arange(n)/(n-1))
    pad=np.zeros((len(sig),4*n,2),complex)
    pad[:,:n]=sig*window[None,:,None]
    cir=np.fft.ifft(pad,axis=1)*n
    amp=np.abs(cir)
    branch=amp.max(axis=1).argmax(axis=1)
    strongest=amp[np.arange(len(amp))[:,None],np.arange(4*n)[None,:],branch[:,None]]
    fp=(strongest>=.3*strongest.max(axis=1)[:,None]).argmax(axis=1)
    p=np.abs(cir[np.arange(len(cir)),fp,:])**2
    s=(p[:,0]-p[:,1])/p.sum(axis=1)
    assert np.isfinite(s).all() and np.isfinite(cir).all()
    return s,fp

def load_case(caseid):
    # Each case's H and trajectory are archived in a single, immutable original revision.
    frozen=Path('cache/pol/experiments/POL_FGO_CORR_20261106_v1/frozen/repo')
    manifest=json.loads((frozen/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())
    case=next(x for x in manifest['cases'] if x['id']==caseid)
    route=case['route']
    timeline=pd.read_csv(io.BytesIO(rget(f'{RF_DIR}/INPUTS/timeline_{route}_Tnone.csv')))
    assert np.array_equal(timeline['idx'].to_numpy(),np.arange(len(timeline)))
    assert np.array_equal(timeline['pose_id'].to_numpy(),np.arange(len(timeline)))
    t=timeline['t_s'].to_numpy(float)
    assert len(t)>400 and np.max(np.abs(t-np.arange(len(t))*.2))<1e-10
    truth=np.column_stack([timeline['x'],timeline['y'],np.deg2rad(timeline['yaw_body_deg'])]).astype(float)
    cases=json.loads(rget(f'{RF_DIR}/CASES.json'))
    meta=next(x for x in cases if x['case']==caseid)
    pose_bytes=rget(case['samples_path'],expected=meta['samples_sha256'])
    samples=json.loads(pose_bytes)
    assert len(samples)==meta['poses'],(caseid,len(samples),meta['poses'])
    poseid=timeline['pose_id'].to_numpy(int)
    ordered=np.asarray([[samples[i]['x'],samples[i]['y'],np.deg2rad(samples[i]['yaw_body_deg'])] for i in poseid],float)
    maxxy=float(np.abs(ordered[:,:2]-truth[:,:2]).max())
    maxyaw=float(np.abs(wrap(ordered[:,2]-truth[:,2])).max()*DEG)
    assert maxxy<=1e-6 and maxyaw<=1e-5,(caseid,'TIMELINE_POSE_MISMATCH',maxxy,maxyaw)
    s_by_channel={};fp_by_channel={}
    for ch,p,expected in [('full',case['full_path'],meta['input_H_sha256']),
                          ('los',case['los_path'],meta['H_sha256'])]:
        b=rget(p,expected=expected)
        H=np.load(io.BytesIO(b),allow_pickle=False)
        assert H.shape==tuple(meta['shape']),('H_DIMENSION',caseid,ch,H.shape,meta['shape'])
        z,fp=extract_observations(H[poseid])
        s_by_channel[ch]=z;fp_by_channel[ch]=fp
    return case,t,truth,poseid,s_by_channel,fp_by_channel,dict(case=caseid,route=route,n=len(t),
        raw_poses=meta['poses'],anchor=case['anchor'],mount=case['mount_deg'],
        max_pose_xy_m=maxxy,max_pose_heading_deg=maxyaw,
        source_full_SHA=meta['input_H_sha256'],source_los_SHA=meta['H_sha256'])

def run_one(engine,r2,case,t,truth,s,level,channel,caseid):
    eng=engine
    c,x0=r2.build_positive_bias_controls(t,truth,level,seed=0)
    old=None
    if caseid=='R2_aB_m0':
        saved_c=eng.controls[channel,level]
        assert max(float(np.max(np.abs(c[k]-saved_c[k]))) for k in ('ds_odom','dtheta_gyro','dt_s'))<1e-13
        assert np.max(np.abs(x0-saved_c['initial_pose']))<1e-13
        # Apply stored controls to remove 1e-17 byte-level motion generator differences.
        c={k:saved_c[k] for k in ('ds_odom','dtheta_gyro','dt_s')}
        x0=saved_c['initial_pose']
        old=eng.original[channel,level]
        assert np.array_equal(s,eng.trace[channel]['z_s'])
        assert np.max(np.abs(truth-eng.truth))<1e-10
        assert np.array_equal(t,eng.t)
    N=len(t);W=len(POLICIES)
    X=np.full((N,W,4),np.nan)
    P=np.full((N,W,4,4),np.nan)
    NIS=np.full((N,W),np.nan)
    ACCEPT=np.zeros((N,W),bool)
    CLIPPED=np.zeros((N,W),bool)
    prior=np.full((N,W,4),np.nan)
    parity={}
    for j,(policy,gamma) in enumerate(POLICIES.items()):
        x=np.r_[x0,0.].astype(float)
        cov=np.diag(np.array([.1,.1,math.radians(5.),math.radians(.1)])**2)
        err=[0.,0.,0.];bad=0
        for k in range(N):
            if k:
                x,cov=r2.predict_one(x,cov,float(c['ds_odom'][k]),float(c['dtheta_gyro'][k]),float(c['dt_s'][k]))
            prior[k,j]=x
            if gamma is None:
                yes=False;n=np.nan;cl=False
            else:
                nx,nP,d=eng.candidate(x,cov,float(s[k]))
                n=float(d['nis'])
                yes=n<=gamma
                cl=bool(d['clip'])
                if yes:x,cov=nx,nP
            X[k,j]=x;P[k,j]=cov;NIS[k,j]=n;ACCEPT[k,j]=yes;CLIPPED[k,j]=cl
            if old is not None:
                original_index=1 if policy=='DR' else 3
                if policy in ('S4','DR'):
                    err[0]=max(err[0],float(np.abs(x-old['estimate'][k,original_index]).max()))
                    err[1]=max(err[1],float(np.abs(cov-old['covariance'][k,original_index]).max()))
                    if policy=='S4':
                        err[2]=max(err[2],abs(n-float(old['nis'][k,original_index])))
                        bad+=int(yes!=(str(old['status'][k,original_index])=='APPLIED'))
        assert np.isfinite(X[:,j]).all() and np.isfinite(P[:,j]).all()
        assert float(np.linalg.eigvalsh(P[:,j]).min())>0
        assert np.max(np.abs(P[:,j]-P[:,j].transpose(0,2,1)))<1e-12
        if old is not None and policy in ('S4','DR'):
            assert err[0]<1e-7 and err[1]<1e-8 and err[2]<1e-7 and bad==0,(caseid,channel,level,policy,err,bad)
            parity[policy]=dict(max_state=err[0],max_cov=err[1],max_nis=err[2],mask_mismatch=bad)
    return X,P,NIS,ACCEPT,CLIPPED,prior,parity

def errors(X,P,t,truth,level,case,acc,clipped,nis):
    names=list(POLICIES)
    v=X[:,:,:3]-truth[:,None,:];v[:,:,2]=wrap(v[:,:,2])
    he=v[:,:,2]*DEG
    xy=np.linalg.norm(v[:,:,:2],axis=2)
    be=X[:,:,3]*DEG-LEVELS[level]
    hsig=np.sqrt(P[:,:,2,2])*DEG
    bsig=np.sqrt(P[:,:,3,3])*DEG
    hnees=v[:,:,2]**2/P[:,:,2,2]
    bnees=v[:,:,3]**2/P[:,:,3,3] # REPLACED in next line: true bias is nonzero
    bnees=be**2/(bsig**2)
    m=range(len(t))
    xynees=np.zeros((len(t),len(names)))
    for j in range(len(names)):
        xynees[:,j]=np.einsum('ni,ni->n',v[:,j,:2],
                             np.linalg.solve(P[:,j,:2,:2],v[:,j,:2,None])[:,:,0])
    windows={"all_after_40":t>=40, "after_30":t>=30,
             "early_40_80":(t>=40)&(t<80),
             "middle_80_120":(t>=80)&(t<120),
             "late_after_120":t>=120,
             "late_quarter":t>=t[-1]-.25*(t[-1]-40)}
    def nstreak(y):
        longest=0;now=0
        for v in y:
            if not v:now+=1;longest=max(longest,now)
            else:now=0
        return longest
    def val(arr):return float(np.sqrt(np.mean(np.asarray(arr)**2)))
    records=[]
    for window,mask in windows.items():
        if mask.sum()<10:continue
        for j,pol in enumerate(names):
            h=he[mask,j];p=xy[mask,j];b=be[mask,j];ah=acc[mask,j]
            records.append(dict(case=case['id'],route=case['route'],channel=case['channel'],level=level,
                policy=pol,window=window,n=int(mask.sum()),heading_rmse_deg=val(h),
                heading_mae_deg=float(np.mean(abs(h))),heading_q95_abs_deg=float(np.quantile(abs(h),.95)),
                heading_q99_abs_deg=float(np.quantile(abs(h),.99)),heading_max_abs_deg=float(abs(h).max()),
                xy_rmse_m=val(p),xy_q95_m=float(np.quantile(p,.95)),xy_q99_m=float(np.quantile(p,.99)),
                bias_rmse_deg_s=val(b),bias_mae_deg_s=float(np.mean(abs(b))),
                head_nees=float(hnees[mask,j].mean()),xy_nees=float(xynees[mask,j].mean()),
                bias_nees=float(bnees[mask,j].mean()),
                head95=float((hnees[mask,j]<=3.841458820694124).mean()),
                xy95=float((xynees[mask,j]<=5.991464547107979).mean()),
                bias95=float((bnees[mask,j]<=3.841458820694124).mean()),
                head_sigma_rms_deg=val(hsig[mask,j]),
                bias_sigma_rms_deg_s=val(bsig[mask,j]),
                accepted=int(ah.sum()),accept_rate=float(ah.mean()),
                longest_reject_streak=int(nstreak(ah)),
                lut_clip_count=int(clipped[mask,j].sum()),
                nis_mean=float(np.nanmean(nis[mask,j])) if pol!='DR' else None,
                divergence10_frac=float((abs(h)>=10).mean())))
    blocks=[]
    for lower in np.arange(40,np.floor(float(t[-1])/10)*10+1,10):
        mask=(t>=lower)&(t<lower+10)
        if mask.sum()<10:continue
        for j,pol in enumerate(names):
            blocks.append(dict(case=case['id'],route=case['route'],channel=case['channel'],level=level,
               policy=pol,block_start_s=float(lower),block_end_s=float(lower+10),n=int(mask.sum()),
               heading_rmse_deg=val(he[mask,j]),xy_rmse_m=val(xy[mask,j]),
               heading_max_abs_deg=float(abs(he[mask,j]).max()),
               bias_rmse_deg_s=val(be[mask,j]),accept=int(acc[mask,j].sum()),
               head95=float((hnees[mask,j]<=C1).mean()),xy95=float((xynees[mask,j]<=C2).mean())))
    return records,blocks

def one_case(caseid):
    assert caseid in CASE_IDS
    eng,r2=exact_source()
    case,t,truth,pos,observations,fps,meta=load_case(caseid)
    eng.case=case
    # No truth enters the model; held only in scoring and original-control simulation.
    es=[];bs=[];qa=dict(meta=meta,checks={},baseline_parity={},scope='Frozen s-only S4+DR, no gate retraining',
                       scalar_NIS_cutoffs=[.5,2.,6.6348966010212145],
                       status='RUNNING',source_ref=RF_REF)
    for ch in ("full","los"):
        assert len(observations[ch])==len(t)
        for lv in LEVELS:
            X,P,N,A,C,prior,parity=run_one(eng,r2,case,t,truth,observations[ch],lv,ch,caseid)
            rr,bb=errors(X,P,t,truth,lv,dict(case,channel=ch),A,C,N)
            es.extend(rr);bs.extend(bb)
            qa['baseline_parity'][f'{ch}/{lv}']=parity
            if lv=='B0':
                qa['checks'][ch]=dict(samples=int(len(t)),s_min=float(observations[ch].min()),
                    s_max=float(observations[ch].max()),fp_min=int(fps[ch].min()),
                    fp_max=int(fps[ch].max()),clip_total=int(C.sum()))
    pd.DataFrame(es).to_csv(OUT/f'{caseid}_METRICS.csv',index=False)
    pd.DataFrame(bs).to_csv(OUT/f'{caseid}_BLOCKS.csv',index=False)
    qa.update(status='PASS_STORED_R2_PARITY_AND_FROZEN_ROUTES',
              policies=len(POLICIES),eval_rows=len(es),block_rows=len(bs),input_files=INPUTS)
    (OUT/f'{caseid}_QA.json').write_text(json.dumps(qa,indent=2,allow_nan=False))
    print("CASE_PASS "+json.dumps({"case":caseid,"n":len(t),"rows":len(es),
       "r2_parity":qa['baseline_parity'].get('full/B0')},default=str),flush=True)

def aggregate():
    frames=[];blocks=[];receipt=[]
    for caseid in CASE_IDS:
        qa=json.loads((OUT/f'{caseid}_QA.json').read_text())
        assert qa['status']=='PASS_STORED_R2_PARITY_AND_FROZEN_ROUTES'
        if caseid=='R2_aB_m0':
            for lv in LEVELS:
                for ch in ('full','los'):
                    for p in ('DR','S4'):
                        assert p in qa['baseline_parity'][f'{ch}/{lv}']
        df=pd.read_csv(OUT/f'{caseid}_METRICS.csv')
        bl=pd.read_csv(OUT/f'{caseid}_BLOCKS.csv')
        assert len(df)==len(POLICIES)*len(LEVELS)*2*6,(caseid,len(df))
        frames.append(df);blocks.append(bl)
        receipt.append(dict(case=caseid,metric_rows=len(df),block_rows=len(bl),r2_parity=bool(qa['baseline_parity'].get('full/B0'))))
    full=pd.concat(frames,ignore_index=True);B=pd.concat(blocks,ignore_index=True)
    assert len(full)==7*4*4*2*6
    keys=['case','channel','level','window']
    pivot=full.set_index(keys+['policy'])
    for baseline in ('DR','S4'):
        for field in ('heading_rmse_deg','xy_rmse_m','bias_rmse_deg_s'):
            ref=pivot.loc[pd.MultiIndex.from_frame(full[keys+[]].assign(policy=baseline)),field].to_numpy()
            full[f'{field}_ratio_vs_{baseline}']=full[field].to_numpy()/ref
    base=B.set_index(['case','channel','level','block_start_s','policy'])
    for policy in ('NIS_0p5','NIS_2'):
        part=B[B.policy==policy].copy()
        idx=pd.MultiIndex.from_frame(part[['case','channel','level','block_start_s']].assign(policy='S4'))
        part['heading_delta_rmse_vs_S4']=part.heading_rmse_deg.to_numpy()-base.loc[idx,'heading_rmse_deg'].to_numpy()
        part['xy_delta_rmse_vs_S4']=part.xy_rmse_m.to_numpy()-base.loc[idx,'xy_rmse_m'].to_numpy()
        part['gate']=policy
        if policy=='NIS_0p5':deltas=[part]
        else:deltas.append(part)
    improvements=pd.concat(deltas,ignore_index=True)
    full.to_csv(OUT/'ALL_METRICS.csv',index=False)
    B.to_csv(OUT/'TEN_SECOND_BLOCKS.csv',index=False)
    improvements.to_csv(OUT/'TEN_SECOND_COMPARISONS.csv',index=False)
    overall=full[(full.window=='all_after_40')&(full.channel=='full')].copy()
    route=overall.groupby(['route','level','policy'],as_index=False).agg(
        heading_rmse_median=('heading_rmse_deg','median'),xy_rmse_median=('xy_rmse_m','median'),
        bias_rmse_median=('bias_rmse_deg_s','median'),head95_median=('head95','median'),
        xy95_median=('xy95','median'),n_cases=('case','nunique'))
    route.to_csv(OUT/'ROUTE_MEDIANS_FULL.csv',index=False)
    score=[]
    for caseid in CASE_IDS:
        for lv in LEVELS:
            g=overall[(overall.case==caseid)&(overall.level==lv)].set_index('policy')
            a=g.loc['NIS_0p5'];b=g.loc['NIS_2'];s=g.loc['S4']
            score.append(dict(case=caseid,route=caseid.split('_')[0],level=lv,
               h_ratio_0p5_vs_s4=float(a.heading_rmse_deg/s.heading_rmse_deg),
               h_ratio_2_vs_s4=float(b.heading_rmse_deg/s.heading_rmse_deg),
               xy_ratio_0p5_vs_s4=float(a.xy_rmse_m/s.xy_rmse_m),
               xy_ratio_2_vs_s4=float(b.xy_rmse_m/s.xy_rmse_m),
               gate_0p5_better_both_s4=bool(a.heading_rmse_deg<s.heading_rmse_deg and a.xy_rmse_m<s.xy_rmse_m),
               gate_2_better_both_s4=bool(b.heading_rmse_deg<s.heading_rmse_deg and b.xy_rmse_m<s.xy_rmse_m)))
    summary=dict(experiment='PALO NIS fixed .5/2 route transfer',status='VERIFIED_UNBLINDED_SAME_CORRIDOR',
        n_cases=len(CASE_IDS),n_routes=3,n_bias=4,n_channels=2,policies=list(POLICIES),
        metric_rows=int(len(full)),ten_s_blocks=int(len(B)),
        n_better_both_s4_0p5=int(sum(x['gate_0p5_better_both_s4'] for x in score)),
        n_better_both_s4_2=int(sum(x['gate_2_better_both_s4'] for x in score)),
        conditions=score,qa=receipt,
        limitations=['R2,R4,R5 are same modeled corridor, not independent environments',
                     'Same motion-noise stream seed0 and RF source; no blind confirmation',
                     'R2 prior tuned threshold .5/2; other routes not used for tuning',
                     'Scientific comparisons use s-only FrozenLut and R_s=.0081, not P2 POWER joint range-s filter',
                     'No claim of production uncertainty calibration or guaranteed safety'])
    (OUT/'SUMMARY.json').write_text(json.dumps(summary,indent=2,allow_nan=False))
    digest={p.name:{"bytes":p.stat().st_size,"sha256":sha(p.read_bytes())}
            for p in OUT.iterdir() if p.is_file()}
    (OUT/'OUTPUT_SHA256.json').write_text(json.dumps(digest,indent=2))
    print("AGGREGATE_PASS "+json.dumps({k:v for k,v in summary.items() if k in ('metric_rows','ten_s_blocks','n_better_both_s4_0p5','n_better_both_s4_2')},default=str))

def publish():
    token=os.environ['GITHUB_TOKEN'];branch=os.environ['TARGET_BRANCH']
    root=f'https://api.github.com/repos/{REPO}'
    def api(path,method='GET',obj=None):
        b=None if obj is None else json.dumps(obj).encode()
        hd={'Authorization':f'Bearer {token}','Accept':'application/vnd.github+json',
            'X-GitHub-Api-Version':'2022-11-28','User-Agent':'PALO-route-transfer'}
        if b is not None:hd['Content-Type']='application/json'
        err=None
        for i in range(4):
            try:
                req=urllib.request.Request(root+path,data=b,headers=hd,method=method)
                with urllib.request.urlopen(req,timeout=150) as r:return json.load(r)
            except Exception as e:err=e;time.sleep(i+1)
        raise RuntimeError('GITHUB_PUBLISH_FAILED '+path+' '+repr(err))
    ref='/git/ref/heads/'+branch.replace('/','%2F')
    parent=api(ref)['object']['sha']
    assert parent==os.environ['GITHUB_SHA'],('CONCURRENT_UPDATE',parent,os.environ['GITHUB_SHA'])
    base=api('/git/commits/'+parent)['tree']['sha']
    elems=[];prefix=f'research/PALO_NIS_ROUTE_TRANSFER_20261108/runs/{os.environ["GITHUB_RUN_ID"]}'
    for f in sorted(OUT.iterdir()):
        if not f.is_file():continue
        b=f.read_bytes()
        blob=api('/git/blobs','POST',dict(content=base64.b64encode(b).decode(),encoding='base64'))['sha']
        elems.append(dict(path=f'{prefix}/{f.name}',mode='100644',type='blob',sha=blob))
    tree=base
    for i in range(0,len(elems),12):
        tree=api('/git/trees','POST',dict(base_tree=tree,tree=elems[i:i+12]))['sha']
    commit=api('/git/commits','POST',dict(tree=tree,parents=[parent],message='Publish parity-gated frozen NIS route transfer: R2/R4/R5 Full+LoS and bias statistics'))['sha']
    assert api(ref)['object']['sha']==parent
    api('/git/refs/heads/'+branch.replace('/','%2F'),'PATCH',dict(sha=commit,force=False))
    assert api(ref)['object']['sha']==commit
    print('REMOTE_PUBLISHED',commit,'FILES',len(elems),flush=True)

if __name__=='__main__':
    a=argparse.ArgumentParser()
    a.add_argument('mode',choices=('case','aggregate'))
    a.add_argument('--case',choices=CASE_IDS)
    a.add_argument('--publish',action='store_true')
    args=a.parse_args()
    if args.mode=='case':one_case(args.case)
    else:
        aggregate()
        if args.publish:publish()
