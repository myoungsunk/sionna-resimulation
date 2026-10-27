from pathlib import Path
import os,sys,json,importlib.util,hashlib,traceback
ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'DS_MASK_CAUSAL_X0A_X1_20261026_01a1775b'
X2=ROOT.parent/'DS_MASK_CAUSAL_X2_20261026_01a1775b'
sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('frozen_x1',OLD/'run_stage.py');S=importlib.util.module_from_spec(spec);spec.loader.exec_module(S)
S.ROOT=ROOT;os.environ['PJ_OUT']=str(ROOT/'runtime')
import numpy as np
import pandas as pd
V=None
def close(name,a,b):S.check(name,a,b,1e-10,1e-10)
def sequential(x,P,v,H,R,block):
    hr,hs=H[:,0],H[:,1];kr=np.einsum('nij,nj->ni',P,hr)/(np.einsum('ni,nij,nj->n',hr,P,hr)+R[:,0,0])[:,None]
    kr[block,2:]=0
    dx=kr*v[:,0,None];A=np.eye(4)[None]-kr[:,:,None]*hr[:,None,:]
    p1=A@P@A.swapaxes(-1,-2)+R[:,0,0,None,None]*(kr[:,:,None]*kr[:,None,:])
    ks=np.einsum('nij,nj->ni',p1,hs)/(np.einsum('ni,nij,nj->n',hs,p1,hs)+R[:,1,1])[:,None]
    delta=dx+ks*(v[:,1]-np.einsum('ni,ni->n',hs,dx))[:,None]
    A=np.eye(4)[None]-ks[:,:,None]*hs[:,None,:]
    cp=A@p1@A.swapaxes(-1,-2)+R[:,1,1,None,None]*(ks[:,:,None]*ks[:,None,:]);cp=.5*(cp+cp.swapaxes(-1,-2))
    y=x+delta;y[:,2]=V.MC.wrap(y[:,2])
    K=np.stack([kr-ks*np.einsum('ni,ni->n',hs,kr)[:,None],ks],axis=2)
    return y,cp,K
def update(x,P,z,h,H,mu,R,mode):
    v=z-h-mu;hp=H@P;cov=hp@H.swapaxes(-1,-2)+R;cov=.5*(cov+cov.swapaxes(-1,-2))
    K=np.linalg.solve(cov,hp).swapaxes(-1,-2)
    for j in np.flatnonzero((mode==2)|(mode==3)):
        c=0 if mode[j]==2 else 1;K[j]=0;K[j,:,c]=hp[j,c]/cov[j,c,c]
    delta=np.einsum('nij,nj->ni',K,v);y=x+delta;y[:,2]=V.MC.wrap(y[:,2]);A=np.eye(4)[None]-K@H
    cp=A@P@A.swapaxes(-1,-2)+K@R@K.swapaxes(-1,-2);cp=.5*(cp+cp.swapaxes(-1,-2))
    seq=mode>=4
    if seq.any():y[seq],cp[seq],K[seq]=sequential(x[seq],P[seq],v[seq],H[seq],R[seq],mode[seq]==5)
    yes=mode>0
    return np.where(yes[:,None],y,x),np.where(yes[:,None,None],cp,P),K
def unit():
    rng=np.random.default_rng(2701);n=5;x=rng.normal(size=(n,4));L=rng.normal(size=(n,4,4));P=L@L.swapaxes(-1,-2)+np.eye(4);H=rng.normal(size=(n,2,4));h=rng.normal(size=(n,2));mu=np.zeros((n,2));z=np.ones((n,2));R=np.tile(np.diag([.1,.3]),(n,1,1))
    a=update(x,P,z,h,H,mu,R,np.ones(n,int));b=update(x,P,z,h,H,mu,R,np.full(n,4))
    for k in [0,1]:close('unit_seq_joint_'+str(k),a[k],b[k])
    c=sequential(x,P,z-h,H,R,np.ones(n,bool));assert np.linalg.eigvalsh(c[1]).min()>0
    for ch,mode in [(0,2),(1,3)]:
        got=update(x,P,z,h,H,mu,R,np.full(n,mode));hh=H[:,ch];kk=np.einsum('nij,nj->ni',P,hh)/(np.einsum('ni,nij,nj->n',hh,P,hh)+R[:,ch,ch])[:,None]
        expected=x+kk*(z[:,ch]-h[:,ch])[:,None];expected[:,2]=V.MC.wrap(expected[:,2]);close('unit_scalar_'+str(ch),got[0],expected)
    S.event('UNIT_PASS')
def replay(case,inp,model,specs,mask,ms=0.):
    n=len(inp['t']);J=len(specs);x=np.tile(np.r_[inp['x0'],0.],(J,1));P=np.tile(np.diag(np.r_[V.INITIAL_POSE_STD**2,V.BIAS_PRIOR_STD**2]),(J,1,1))
    shapes={'x':(4,),'P':(4,4),'prior':(4,),'Pprior':(4,4),'h':(2,),'H':(2,4),'K':(4,2),'mu':(2,),'R':(2,2),'nu':(2,)}
    out={k:np.empty((n,J)+sh) for k,sh in shapes.items()};out['mode']=np.zeros((n,J),np.int8);out['acc']=np.zeros((n,J),bool)
    for k in range(n):
        if k%128==0:S.stopcheck()
        if k:
            c=inp['controls']
            for j in range(J):x[j],P[j]=V.predict_one(x[j],P[j],float(c['ds_odom'][k]),float(c['dtheta_gyro'][k]),float(c['dt_s'][k]))
        h,H=model.batch(x,case);mu=np.tile(inp['mu'][k],(J,1));R=np.tile(inp['R'][k],(J,1,1));z=np.tile(inp['z'][k],(J,1));mode=np.zeros(J,int)
        ab,am=mask[k];new=am and not ab
        for j,s in enumerate(specs):
            mu[j,0]+=s.get('alpha',0)*(inp['pred'][k]-mu[j,0]);z[j,1]-=ms*s.get('oracle',0)
            policy=s.get('policy','base');accept=ab
            if policy=='mur':accept=am
            elif policy=='union':accept=ab or am
            elif policy=='intersection':accept=ab and am
            mode[j]=s.get('joint',1) if accept else 0
            if new and s.get('new_ch'):mode[j]=s['new_ch']
        out['prior'][k]=x;out['Pprior'][k]=P;out['h'][k]=h;out['H'][k]=H;out['mu'][k]=mu;out['R'][k]=R;out['nu'][k]=z-h-mu
        x,P,K=update(x,P,z,h,H,mu,R,mode);out['x'][k]=x;out['P'][k]=P;out['K'][k]=K;out['mode'][k]=mode;out['acc'][k]=mode>0
    assert np.isfinite(out['x']).all() and np.isfinite(P).all()
    assert np.max(abs(out['P']-out['P'].swapaxes(-1,-2)))<1e-12
    assert np.linalg.eigvalsh(out['P']).min()>=-1e-12
    rej=~out['acc']
    if rej.any():S.check('reject_x',out['x'][rej],out['prior'][rej],0);S.check('reject_P',out['P'][rej],out['Pprior'][rej],0)
    # Independently verify the full predetermined acceptance/channel schedules.
    ab,am=mask.T;new=am&~ab
    for j,s in enumerate(specs):
        acc={'base':ab,'mur':am,'union':ab|am,'intersection':ab&am}[s.get('policy','base')].copy()
        expected=np.where(acc,s.get('joint',1),0)
        if s.get('new_ch'):expected[new]=s['new_ch']
        S.check('mode_'+s['name'],out['mode'][:,j],expected,0)
    return out
def compare(label,out,j,ref,arm):
    jr=list(ref['names']).index(arm)
    for key in ['x','P','prior','Pprior','h','H','mu','R','acc']:
        a=out[key][:,j];b=ref[key][:,jr]
        if key in ['x','prior']:
            diff=a-b;diff[:,2]=V.MC.wrap(diff[:,2]);close(label+'_'+key,diff,np.zeros_like(diff))
        else:close(label+'_'+key,a,b)
def score(stage,case,bias,inp,out,specs,ms):
    m=inp['t']>=30;truth=np.column_stack([inp['truth'],np.full(len(m),np.radians(V.BIAS_LEVELS[bias]))]);e=out['x']-truth[:,None];e[:,:,2]=V.MC.wrap(e[:,:,2]);he=np.degrees(e[m,:,2]);P=out['P'][m]
    nees=np.einsum('nji,nji->nj',e[m],np.linalg.solve(P,e[m,...,None])[...,0]);hn=e[m,:,2]**2/P[:,:,2,2]
    anc=np.array(case['anchor']);dz=anc[2]-case['robot_z_m'];tr=np.sqrt(np.sum((truth[:,:2]-anc[:2])**2,axis=1)+dz**2);rr=(np.sqrt(np.sum((out['x'][:,:,:2]-anc[:2])**2,axis=2)+dz**2)-tr[:,None])*100
    rows=[]
    for j,s in enumerate(specs):
        rmse=float(np.sqrt(np.mean(he[:,j]**2)));biasv=float(he[:,j].mean());std=float(he[:,j].std())
        close('rmse_bias_std',rmse**2,biasv**2+std**2)
        rows.append(dict(stage=stage,case=case['id'],route=case['route'],bias=bias,arm=s['name'],alpha=s.get('alpha',0),oracle_ms=ms*s.get('oracle',0),heading_rmse_deg=rmse,heading_bias_deg=biasv,heading_std_deg=std,heading95_deg=float(np.quantile(abs(he[:,j]),.95)),heading_nees=float(hn[:,j].mean()),state4_nees=float(nees[:,j].mean()),range_rmse_cm=float(np.sqrt(np.mean(rr[m,j]**2))),xy_rmse_m=float(np.sqrt(np.mean(np.sum(e[m,j,:2]**2,axis=1)))),accepted_all=int(out['acc'][:,j].sum()),scoring_n=int(m.sum())))
    dest=ROOT/stage;dest.mkdir(exist_ok=True);np.savez_compressed(dest/f'{case["id"]}_{bias}.npz',t_s=inp['t'],pose_id=inp['ids'],truth_scoring_only=truth,names=np.array([s['name'] for s in specs]),specs_json=json.dumps(specs),oracle_ms=ms,**out)
    return rows
def main():
    global V
    locked=json.loads((OLD/'INPUT_LOCK.json').read_text())['files'].copy()
    for folder,paths in [(OLD,list((OLD/'x1').glob('*.npz'))+[OLD/'run_stage.py',OLD/'EXECUTION_RESULT.json']),(X2,list((X2/'linear').glob('*_BB.npz')))]:
        manifest={r['path']:r['sha256'] for r in json.loads((folder/'OUTPUT_SHA256.json').read_text())['files']}
        for p in paths:
            h=S.sha(p);assert h==manifest[p.relative_to(folder).as_posix()];locked.append(dict(path=str(p),sha256=h))
    for r in locked:assert S.sha(r['path'])==r['sha256']
    S.write('INPUT_LOCK.json',dict(files=locked,script_sha256=S.sha(__file__),protocol_sha256=S.sha(ROOT/'PROTOCOL.md'),python=sys.version,command=sys.argv));S.event('INPUT_FREEZE_PASS',files=len(locked))
    sys.path.insert(0,str(S.PKG));import v_replay as V
    S.V=V;S.test_update();unit();model=V.SourceFFD()
    feat=pd.read_csv(S.one('OBSERVATION_FEATURES_LABELS.csv.gz'));par=pd.read_csv(S.one('OOF_PARAMETERS.csv.gz'));mr=pd.read_csv(S.PKG/'results_murec/MR_SERIES.csv.gz');hg=pd.read_csv(S.PKG/'results_hgate/HG_SERIES.csv.gz')
    cache=[]
    for case in V.MANIFEST['cases']:
        for bias in ['B0','L2']:
            inp=S.load_case(case,bias,feat,par,mr,hg)
            with np.load(OLD/'x1'/f'{case["id"]}_{bias}.npz') as f:ref={k:f[k] for k in f.files}
            mask=ref['acc'][:,[0,3]];assert np.all(inp['R'][:,0,1]==0) and np.all(inp['R'][:,1,0]==0)
            with np.load(X2/'linear'/f'{case["id"]}_{bias}_BB.npz') as f:
                S.check('oracle_pose_ids',f['pose_id'],inp['ids'],0);S.check('oracle_base_mask',f['base_accept'],mask[:,0],0);ms=float(f['u'][mask[:,0],1].mean())
            cache.append((case,bias,inp,ref,mask,ms))
    scores=[]
    stages=['E1','E2','E3_CONTROL','E3','E4a','E4b']
    for stage in stages:
        S.event('STAGE_START',stage_name=stage)
        count=0
        for case,bias,inp,ref,mask,ms in cache:
            cid=case['id'];label=stage+'_'+cid+'_'+bias
            if stage=='E4a' and cid!='R5_aA_m0':continue
            if stage=='E4b' and cid!='R2_aB_m0':continue
            if stage=='E1':specs=[dict(name='A'+str(a),alpha=a) for a in [0,.25,.5,.75,1]];controls=[(0,'BB'),(4,'MB')]
            elif stage=='E2':specs=[dict(name='BB'),dict(name='MB',alpha=1),dict(name='O_BB',oracle=1),dict(name='O_MB',alpha=1,oracle=1)];controls=[(0,'BB'),(1,'MB')]
            elif stage=='E3_CONTROL':specs=[dict(name='SEQ_BB',joint=4),dict(name='SEQ_MB',joint=4,alpha=1)];controls=[(0,'BB'),(1,'MB')]
            elif stage=='E3':specs=[dict(name='BLOCK_BB',joint=5),dict(name='BLOCK_MB',joint=5,alpha=1)];controls=[]
            elif stage=='E4a':specs=[dict(name='BB'),dict(name='BM',policy='mur'),dict(name='BB_NEW_POL',new_ch=3)];controls=[(0,'BB'),(1,'BM')]
            else:specs=[dict(name='MB',alpha=1),dict(name='DROP4',alpha=1,policy='intersection'),dict(name='RESTORE4',alpha=1,policy='union',new_ch=2),dict(name='MM_NEW_RANGE_ONLY',alpha=1,policy='mur',new_ch=2)];controls=[(0,'MB'),(3,'MM_NEW_RANGE_ONLY')]
            S.event('CASE_START',condition=label);out=replay(case,inp,model,specs,mask,ms)
            for j,a in controls:compare(label+'_'+a,out,j,ref,a)
            scores.extend(score(stage,case,bias,inp,out,specs,ms));pd.DataFrame(scores).to_csv(ROOT/'SCORES.csv',index=False);count+=1
            S.write('CHECKS.json',S.checks);S.event('CASE_PASS',condition=label)
        S.write(stage+'_GATE.json',dict(status='PASS',conditions=count,meaning='Controls and numerical guards passed; not a scientific hypothesis PASS'));S.event('STAGE_PASS',stage_name=stage,conditions=count)
    for r in locked:assert S.sha(r['path'])==r['sha256']
    S.write('EXECUTION_RESULT.json',dict(status='TECHNICAL_PASS',stages=stages,score_rows=len(scores),inputs_preserved=True,checks=len(S.checks),scientific_claim='Nonlinear intervention diagnostics; interpretation in report'))
    S.event('COMPLETE')
if __name__=='__main__':
    try:main()
    except BaseException as e:S.write('FAILURE.json',dict(error=str(e),traceback=traceback.format_exc()));S.event('STOP',error=str(e));raise
