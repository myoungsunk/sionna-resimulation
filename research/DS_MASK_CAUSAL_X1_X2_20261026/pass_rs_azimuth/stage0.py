from pathlib import Path
import hashlib,json,datetime
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'pol_azimuth_alloc'
PRIMARY=['R2_aA_m45','R4_aA_m0','R4_aB_m0']
EDGES=[0,.5,1,1.5,2,3,4,6,8,np.inf]
LABELS=['0-.5','.5-1','1-1.5','1.5-2','2-3','3-4','4-6','6-8','8-inf']
GATE=9.21034037197618
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(name,obj): (ROOT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def save(name,rows):pd.DataFrame(rows).to_csv(ROOT/name,index=False,na_rep='NA')

def main():
    assert not (ROOT/'STAGE0_LOCK.json').exists(),'Do not overwrite an executed stage'
    files=[OLD/'C1B_PACKETS.csv.gz',OLD/'C3_PACKETS.csv.gz',ROOT/'PROTOCOL.md',ROOT/'PROTOCOL_ADDENDUM.md',Path(__file__)]
    files+=sorted((ROOT.parent/'e1_e4/E1').glob('*.npz'))
    core=Path(r'D:/SLAM_bot/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/execution_33e9849/p2/research/PJ_CONSISTENCY_M123_20261021/m_core.py')
    files.append(core)
    lock=[dict(path=str(p.resolve()),sha256=sha(p),bytes=p.stat().st_size) for p in files]
    dump('STAGE0_LOCK.json',dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),files=lock))
    a=pd.read_csv(OLD/'C1B_PACKETS.csv.gz'); c=pd.read_csv(OLD/'C3_PACKETS.csv.gz')
    checks=[]
    def check(name,ok):
        checks.append(dict(name=name,pass_check=bool(ok)))
        if not ok:
            dump('STAGE0_CHECKS.json',dict(status='FAIL',checks=checks));raise AssertionError(name)
    check('unique_keys',not a.duplicated(['case','bias','arm','pose_id']).any())
    # Same RF is repeated by filters; check before removing duplicates.
    check('residual_same_bias_arm',a.groupby(['case','pose_id']).r_base.agg(lambda x:x.max()-x.min()).max()<1e-12)
    train=a[(a.bias=='B0')&(a.arm=='BB')].copy()
    train['train_bin']=pd.cut(train.d_est_m,EDGES,labels=LABELS,right=False)
    routes=sorted(train.route.unique());check('route_inventory',routes==['R2','R4','R5'])
    p1=[]
    for hold in routes:
        tr=train[train.route!=hold]
        for label in LABELS:
            g=tr[tr.train_bin==label];v=g.r_base.var(ddof=1)
            p1.append(dict(bin=label,route_holdout=hold,mean=g.r_base.mean(),var=v,n=len(g),
                           valid=bool(len(g)>=30 and np.isfinite(v) and v>0),training_routes=','.join(sorted(g.route.unique()))))
    tab=pd.DataFrame(p1);cvrows=[]
    for label in LABELS:
        g=tab[tab.bin==label];v=g['var'];cv=v.std(ddof=1)/v.mean() if v.notna().all() and v.mean()>0 else np.nan
        tab.loc[tab.bin==label,'route_cv']=cv
        cvrows.append(dict(bin=label,cv=cv,min_n=int(g.n.min()),all_cells_valid=bool(g.valid.all()),go=bool(g.valid.all() and cv<=.5)))
    save('P1_RS_TABLE.csv',tab);save('P1_CV.csv',cvrows)
    p1go=all(r['go'] for r in cvrows[:3])
    episodes=[];formation=[];previews=[];gaprows=[];maskdiff=[]
    for (case,bias),g0 in c.groupby(['case','bias']):
        bb=g0[g0.arm=='BB'].sort_values('k').reset_index(drop=True)
        mb=g0[g0.arm=='MB'].sort_values('k').reset_index(drop=True)
        check(case+bias+'_paired',np.array_equal(bb.pose_id,mb.pose_id) and np.array_equal(bb.d_gt_m,mb.d_gt_m))
        t=np.round(bb.t_s.to_numpy(),8);near=bb.d_gt_m.to_numpy()<1.5
        starts=np.flatnonzero(near & ~np.r_[False,near[:-1]]);ends=np.flatnonzero(near & ~np.r_[near[1:],False])
        check(case+bias+'_episode_count',len(starts)==len(ends))
        gaps={x:mb[x].to_numpy()-bb[x].to_numpy() for x in ['e_t_cm','e_r_cm','psi_err_deg','beta_err_deg']}
        gaprows.extend(dict(case=case,bias=bias,k=int(bb.k.iloc[k]),t_s=t[k],d_gt_m=float(bb.d_gt_m.iloc[k]),**{x:float(v[k]) for x,v in gaps.items()}) for k in range(len(t)))
        trace=np.load(ROOT.parent/'e1_e4/E1'/f'{case}_{bias}.npz'); names=list(trace['names'])
        i0=names.index('A0');i1=names.index('A1')
        check(case+bias+'_AB_mask',np.array_equal(trace['acc'][:,i0],trace['acc'][:,i1]))
        for pid,(i,j) in enumerate(zip(starts,ends),1):
            start,end=t[i],t[j];nxt=t[starts[pid]] if pid<len(starts) else np.inf
            prelo=max(0.,start-30);posthi=min(end+30,nxt,t[-1]);prelen=start-prelo;postlen=posthi-end
            pre=(t>=prelo)&(t<start);post=(t>end)&(t<=posthi)&(t<nxt)
            frominit=prelen<5 and abs(gaps['e_t_cm'][0])<.1
            validpre=(prelen>=5 and pre.any()) or frominit;validpost=postlen>=10 and post.any()
            ep=dict(case=case,bias=bias,pass_id=pid,primary=case in PRIMARY and pid==1,role='first' if pid==1 else 'reexposure',start_s=start,end_s=end,
                    min_d_gt_m=float(bb.d_gt_m.iloc[i:j+1].min()),min_d_time_s=float(t[i+np.argmin(bb.d_gt_m.iloc[i:j+1].to_numpy())]),window_start_s=max(0.,start-10),window_end_s=min(t[-1],end+10),
                    pre_start_s=prelo,pre_end_s=start,pre_length_s=prelen,pre_n=int(pre.sum()),post_start_s=end,post_end_s=posthi,post_length_s=postlen,post_n=int(post.sum()),
                    pre_first_sample_s=float(t[pre][0]) if pre.any() else np.nan,pre_last_sample_s=float(t[pre][-1]) if pre.any() else np.nan,
                    post_first_sample_s=float(t[post][0]) if post.any() else np.nan,post_last_sample_s=float(t[post][-1]) if post.any() else np.nan,
                    pre_from_init=frominit,init_overlap=bool(prelo<10 and start>0),valid_pre=bool(validpre),valid_post=bool(validpost))
            episodes.append(ep);fr=ep.copy()
            for col,vals in gaps.items():
                before=0. if frominit else float(vals[pre].mean()) if validpre else np.nan
                after=float(vals[post].mean()) if validpost else np.nan
                fr.update({col+'_pre':before,col+'_post':after,col+'_formation':after-before})
            den=abs(fr['e_t_cm_post']);ratio=abs(fr['e_t_cm_formation'])/den if den>1e-12 else np.nan
            fr.update(formation_ratio=ratio,result='NA' if not np.isfinite(ratio) else 'GO' if ratio>=.5 else 'NO_GO')
            formation.append(fr)
            window=(t>=ep['window_start_s'])&(t<=ep['window_end_s'])
            for arm,idx in [('BB',i0),('MB',i1)]:
                d=(bb if arm=='BB' else mb).d_est_m.to_numpy();R=trace['R'][:,idx].copy();H=trace['H'][:,idx];P=trace['Pprior'][:,idx];nu=trace['nu'][:,idx]
                newr=R[:,1,1].copy();invalid=np.zeros(len(t),bool)
                table=tab[tab.route_holdout==case.split('_')[0]].set_index('bin')
                for k in np.flatnonzero(d<2):
                    label=LABELS[min(np.searchsorted(EDGES,d[k],side='right')-1,2)]
                    rr=table.loc[label]
                    if not rr.valid:invalid[k]=True;continue
                    weight=1. if d[k]<1.5 else (2-d[k])/.5
                    newr[k]=np.exp(weight*np.log(rr['var'])+(1-weight)*np.log(newr[k]))
                S=H@P@np.swapaxes(H,-1,-2)+R;S=.5*(S+np.swapaxes(S,-1,-2))
                oldnis=np.einsum('ni,ni->n',nu,np.linalg.solve(S,nu[...,None])[...,0])
                S[:,1,1]+=newr-R[:,1,1];newnis=np.einsum('ni,ni->n',nu,np.linalg.solve(S,nu[...,None])[...,0])
                acc=trace['acc'][:,idx];maskdiff.append(dict(case=case,bias=bias,arm=arm,natural_original_vs_AB=int(((oldnis<=GATE)!=acc).sum())))
                denom=int((window&acc).sum());bad=int((window&invalid).sum());nr=int((window&acc&(newnis>GATE)).sum()) if not bad else None
                frac=nr/denom if nr is not None and denom else np.nan
                previews.append(dict(case=case,bias=bias,arm=arm,pass_id=pid,primary=ep['primary'],window_n=int(window.sum()),accepted_n=denom,invalid_R_n=bad,new_reject_n=nr,
                                     new_reject_fraction_accepted=frac,new_reject_fraction_all=nr/window.sum() if nr is not None else np.nan,
                                     result='NA' if not np.isfinite(frac) else 'GO' if frac<=.2 else 'GATE_DOMINATED'))
    save('P2_PASSES_GT.csv',episodes);save('P3_FORMATION.csv',formation);save('P4_GATE_PREVIEW.csv',previews);save('P3_GAP_SERIES.csv',gaprows);save('P4_BASELINE_GATE_DIFFERENCES.csv',maskdiff)
    p2go=all(any(e['case']==case and e['bias']==bias for e in episodes) for case in PRIMARY for bias in ['B0','L2'])
    p3go=all(r['result']=='GO' for r in formation if r['primary']) and sum(r['primary'] for r in formation)==6
    p4go=all(r['result']=='GO' for r in previews if r['primary']) and sum(r['primary'] for r in previews)==12
    for f in lock:check('input_unchanged_'+Path(f['path']).name,sha(Path(f['path']))==f['sha256'])
    dump('STAGE0_CHECKS.json',dict(status='PASS',checks=checks,no_replay=True))
    result=dict(P1='GO' if p1go else 'NO_GO',P2='GO' if p2go else 'NO_GO',P3='GO' if p3go else 'NO_GO',P4='GO' if p4go else 'NO_GO_OR_NA',overall='GO' if all([p1go,p2go,p3go,p4go]) else 'NO_GO',no_replay=True)
    dump('STAGE0_DECISION.json',result);print(json.dumps(result))
    print(pd.DataFrame(cvrows[:3]).to_string(index=False))
    print(pd.DataFrame(formation).query('primary')[['case','bias','pre_length_s','post_length_s','e_t_cm_pre','e_t_cm_post','formation_ratio','result']].to_string(index=False))

if __name__=='__main__':main()
