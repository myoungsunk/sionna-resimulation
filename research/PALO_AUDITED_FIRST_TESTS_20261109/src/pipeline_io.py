#!/usr/bin/env python3
"""Inputs audit, independent result aggregation and transactional Git publication."""
from __future__ import annotations
import argparse,base64,hashlib,io,json,os,time,urllib.request,zipfile
from pathlib import Path
import numpy as np
import pandas as pd

REPO='myoungsunk/sionna-resimulation'
PREFIX='research/PALO_AUDITED_FIRST_TESTS_20261109'
CASES=('R2_aB_m0','R4_aA_m0','R5_aA_m0','R5_aB_m0')
COMMON_SHA='fd1e6b6d1b309ee85226cfc3146030ad4eb14e21be5937fdf764912007f7336e'
LOADER_GITSHA='d0ae06abeeba856a3f333d2b6e0b4d94dda5a805'
DEG=180/np.pi

def H(b):return hashlib.sha256(b).hexdigest()
def dump(p,o):Path(p).write_text(json.dumps(o,indent=2,ensure_ascii=False,allow_nan=False)+'\n')

def source_check(root,out):
    root=Path(root);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    receipts=json.loads((root/'shared/SOURCE_MANIFEST.json').read_text())['files'];checked=[]
    for r in receipts:
        p=root/'cache'/r['local'];b=p.read_bytes()
        assert len(b)==r['bytes'] and H(b)==r['sha256'],('INPUT_SOURCE_SHA_FAIL',str(p))
        g=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
        assert g==r['git_blob'],('INPUT_GIT_BLOB_FAIL',str(p))
        checked.append({'path':r['local'],'sha256':H(b),'bytes':len(b)})
    assert H((root/'vendor/common.py').read_bytes())==COMMON_SHA,'REUSED_COMMON_CHANGED'
    p=root/'route_loader.py'
    if p.exists():
        b=p.read_bytes();g=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
        assert g==LOADER_GITSHA,('ROUTE_LOADER_CHANGED',g)
        checked.append(dict(path='route_loader.py',sha256=H(b),git_blob=g))
    dump(out/'INPUT_SOURCE_AUDIT.json',dict(status='PASS',files_checked=len(checked),files=checked,
        note='All source/data/LUT bytes against pinned upstream manifests; pyc is not executed as source'))
    print('SOURCE_HASH_PASS',len(checked))

def all_results(root):
    root=Path(root);pub=root/'release';pub.mkdir(exist_ok=False)
    metrics=[];info=[];withdraw=[];block=[];receipts=[];recounts=[];rawpaths=[]
    for case in CASES:
        folder=root/case
        receipt=json.loads((folder/'CASE_PASS.json').read_text());assert receipt['case']==case
        assert receipt['status']=='NUMERICAL_AUDIT_PASS_NOT_SCIENTIFIC_ADOPTION'
        manifest=json.loads((folder/'SHA256.json').read_text())
        for p,rec in manifest.items():
            f=folder/p;assert H(f.read_bytes())==rec['sha256'] and f.stat().st_size==rec['bytes'],('OUTPUT_MANIFEST_FAIL',str(f))
        df=pd.read_csv(folder/'METRICS.csv');assert len(df)==168
        assert df.groupby(['channel','level','policy']).size().eq(3).all()
        for file in sorted((folder/'trajectories').glob('*.npz')):
            channel,level,policy=file.stem.split('_',2)
            with np.load(file,allow_pickle=False) as a:
                X,P,t,gt=a['X'],a['P'],a['t'],a['truth'];mask=t>=40
                error=X[:,:3]-gt;error[:,2]=np.arctan2(np.sin(error[:,2]),np.cos(error[:,2]))
                h=float(np.linalg.norm(error[mask,2]*DEG)/np.sqrt(mask.sum()))
                xy=float(np.linalg.norm(error[mask,:2])/np.sqrt(mask.sum()))
                bias={'B0':0,'L0':.01,'L1':.05,'L2':.2}[level]
                b=float(np.linalg.norm(X[mask,3]*DEG-bias)/np.sqrt(mask.sum()))
                row=df[(df.channel==channel)&(df.level==level)&(df.policy==policy)&(df.window=='all')].iloc[0]
                diff=max(abs(h-row.heading_rmse_deg),abs(xy-row.xy_rmse_m),abs(b-row.bias_rmse_deg_s))
                assert diff<1e-9,('SAVED_RAW_METRIC_FAIL',case,channel,level,policy,diff)
                assert np.isfinite(X).all() and np.linalg.eigvalsh(P).min()>0
                recounts.append(dict(case=case,channel=channel,level=level,policy=policy,n=int(mask.sum()),max_metric_error=diff))
                if policy in ('TWO','FOUR','COLLAPSE'):
                    assert np.max(abs(a['weights'].sum(axis=1)-1))<1e-12
                    assert np.isfinite(a['heading_NLPD']).all()
        metrics.append(df);info.append(pd.read_csv(folder/'INFORMATION_WINDOWS.csv'))
        withdraw.append(pd.read_csv(folder/'WITHDRAWAL_OUTCOMES.csv'))
        block.append(pd.read_csv(folder/'BLOCKS.csv'));receipts.append(receipt)
        # Commit inspectable tables and audit receipts separately from raw arrays.
        dest=pub/case;dest.mkdir()
        for p in folder.iterdir():
            if p.is_file():(dest/p.name).write_bytes(p.read_bytes())
        # Store raw arrays in deterministic ZIP chunks under the normal Git tree, not LFS.
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_STORED) as archive:
            for p in sorted(folder.rglob('*.npz')):
                zi=zipfile.ZipInfo(str(p.relative_to(folder)),date_time=(2026,11,9,0,0,0))
                archive.writestr(zi,p.read_bytes())
        raw=buffer.getvalue();partsize=6*1024**2
        parts=[]
        for i,offset in enumerate(range(0,len(raw),partsize)):
            name=f'{case}.raw.zip.part{i:03d}';chunk=raw[offset:offset+partsize]
            (pub/name).write_bytes(chunk);parts.append(dict(name=name,bytes=len(chunk),sha256=H(chunk)))
        rawpaths.append(dict(case=case,joined_filename=f'{case}.raw.zip',bytes=len(raw),sha256=H(raw),parts=parts))
    M=pd.concat(metrics,ignore_index=True);I=pd.concat(info,ignore_index=True)
    W=pd.concat(withdraw,ignore_index=True);B=pd.concat(block,ignore_index=True)
    M.to_csv(pub/'ALL_METRICS.csv',index=False);B.to_csv(pub/'ALL_BLOCKS.csv',index=False)
    W.to_csv(pub/'WITHDRAWAL_OUTCOMES.csv',index=False)
    I.to_csv(pub/'ALL_INFORMATION_WINDOWS.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    cols=['case','channel','level','donor','window_s','rho']
    IS=I.groupby(cols,as_index=False).agg(n=('start','size'),median_initial_heading_ratio=('heading_prior_ratio','median'),
        median_endpoint_heading_ratio=('endpoint_heading_ratio','median'),median_bias_ratio=('bias_prior_ratio','median'),
        median_heading_schur_raw=('heading_schur_raw','median'),median_heading_schur_projected=('heading_schur_projected','median'),
        n_endpoint_retention_below_10pct=('endpoint_heading_ratio',lambda x:int((x<.1).sum())),
        rf_discrepancy_std_median=('discrepancy_std','median'),clipped_windows=('clip',lambda x:int((x>0).sum())))
    IS.to_csv(pub/'INFORMATION_SUMMARY.csv',index=False)
    WS=W.groupby(['case','channel','level','lag_s','horizon_s','arm'],as_index=False).agg(
        n=('start','size'),mean_heading_gain_deg2=('heading_gain_deg2','mean'),
        mean_xy_gain_m2=('xy_gain_m2','mean'),mean_heading_ISE_gain=('heading_ISE_gain_deg2_s','mean'),
        positive_heading_events=('heading_gain_deg2',lambda x:int((x>1e-9).sum())),
        harmful_heading_events=('heading_gain_deg2',lambda x:int((x< -1e-9).sum())),
        selected_drop_events=('selected_drop','sum'))
    WS.to_csv(pub/'WITHDRAWAL_SUMMARY.csv',index=False)
    perf=[]
    for (case,ch,lv),g in M[M.window=='all'].groupby(['case','channel','level']):
        g=g.set_index('policy');b=g.loc['S4'];c=g.loc['COLLAPSE']
        for pol in ('TWO','FOUR'):
            r=g.loc[pol]
            perf.append(dict(case=case,channel=ch,level=lv,policy=pol,
                heading_ratio_to_S4=float(r.heading_rmse_deg/b.heading_rmse_deg),
                xy_ratio_to_S4=float(r.xy_rmse_m/b.xy_rmse_m),
                heading_ratio_to_collapse=float(r.heading_rmse_deg/c.heading_rmse_deg),
                xy_ratio_to_collapse=float(r.xy_rmse_m/c.xy_rmse_m),
                better_both_S4=bool(r.heading_rmse_deg<b.heading_rmse_deg and r.xy_rmse_m<b.xy_rmse_m),
                better_both_collapse=bool(r.heading_rmse_deg<c.heading_rmse_deg and r.xy_rmse_m<c.xy_rmse_m)))
    pd.DataFrame(perf).to_csv(pub/'MIXTURE_COMPARISONS.csv',index=False)
    dump(pub/'RAW_ARRAY_PARTS.json',rawpaths)
    dump(pub/'RESULT_RECOUNT_AUDIT.json',dict(status='PASS',trajectories=len(recounts),rows=recounts,
        max_metric_difference=max(x['max_metric_error'] for x in recounts),
        provenance='Recomputed all 224 saved trajectory metrics by norm; not a second simulation'))
    dump(pub/'SUMMARY.json',dict(status='NUMERICAL_AUDIT_PASS_EFFICACY_REQUIRES_SEPARATE_REVIEW',
         n_cases=len(CASES),cases=receipts,metric_rows=len(M),projection_windows=len(I),
         withdrawal_rows=len(W),block_rows=len(B),raw_array_packages=rawpaths,
         external_independent_audit=False,
         limitations=['same corridor, seed0, seen development routes',
          'stage1 is linearized information check, no new filter trajectory',
          'stage2 probabilities, pruning and Gaussian likelihood approximations are uncalibrated',
          'stage3 is event-conditioned checkpoint replay + ERTS, not full nonlinear factor graph',
          'future validation score uses no truth but is not a certified risk probability']))
    # Visible, executed sources accompany results and also get a copy at repository root.
    src=Path(__file__).parent
    (pub/'executed_source').mkdir()
    for f in src.glob('*.py'):(pub/'executed_source'/f.name).write_bytes(f.read_bytes())
    unit=root/'unit'
    if unit.exists():
        (pub/'unit').mkdir()
        for p in unit.iterdir():
            if p.is_file():(pub/'unit'/p.name).write_bytes(p.read_bytes())
    digest={str(p.relative_to(pub)):dict(bytes=p.stat().st_size,sha256=H(p.read_bytes())) for p in pub.rglob('*') if p.is_file()}
    dump(pub/'OUTPUT_SHA256.json',digest)
    print('FINAL_ARRAY_AUDIT_PASS',len(M),'metrics',len(I),'projection windows',len(W),'withdrawal rows')
    return pub

def publish(pub):
    token=os.environ['GITHUB_TOKEN'];branch=os.environ['TARGET_BRANCH'];source=os.environ['GITHUB_SHA']
    root=f'https://api.github.com/repos/{REPO}'
    def api(path,method='GET',payload=None):
        b=None if payload is None else json.dumps(payload).encode();heads={'Authorization':f'Bearer {token}',
         'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'PALO-audited-pretests'}
        if b is not None:heads['Content-Type']='application/json'
        for i in range(5):
            try:
                with urllib.request.urlopen(urllib.request.Request(root+path,data=b,headers=heads,method=method),timeout=150) as r:return json.load(r)
            except Exception:
                if i==4:raise
                time.sleep(2**i)
    ref='/git/ref/heads/'+branch.replace('/','%2F');parent=api(ref)['object']['sha']
    assert parent==source,('CONCURRENT_BRANCH_CHANGE',parent,source)
    base=api('/git/commits/'+parent)['tree']['sha'];tree=[];prefix=f'{PREFIX}/runs/{os.environ["GITHUB_RUN_ID"]}'
    for p in sorted(Path(pub).rglob('*')):
        if p.is_file():
            blob=api('/git/blobs','POST',dict(content=base64.b64encode(p.read_bytes()).decode(),encoding='base64'))['sha']
            tree.append(dict(path=prefix+'/'+str(p.relative_to(pub)),mode='100644',type='blob',sha=blob))
            if p.parent.name=='executed_source':tree.append(dict(path=PREFIX+'/src/'+p.name,mode='100644',type='blob',sha=blob))
    for i in range(0,len(tree),12):base=api('/git/trees','POST',dict(base_tree=base,tree=tree[i:i+12]))['sha']
    commit=api('/git/commits','POST',dict(tree=base,parents=[parent],message='Publish ordered PALO pretests with reused-source, separate-math, raw-array and withdrawal audits'))['sha']
    assert api(ref)['object']['sha']==parent,'CONCURRENT_PUBLISH_ABORT'
    api('/git/refs/heads/'+branch.replace('/','%2F'),'PATCH',dict(sha=commit,force=False))
    assert api(ref)['object']['sha']==commit
    print('PUBLISHED',commit,'files',len(tree),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['source','aggregate']);ap.add_argument('--root',default='.')
    ap.add_argument('--out',default='unit');ap.add_argument('--publish',action='store_true');a=ap.parse_args()
    if a.mode=='source':source_check(a.root,a.out)
    else:
        p=all_results(a.root)
        if a.publish:publish(p)
