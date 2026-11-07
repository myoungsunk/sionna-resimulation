"""PALO-ORACLE-001: parity-gated greedy hindsight diagnostic, not an upper bound."""
import sys, json, hashlib, shutil, platform
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/'source'))
import palo_oracle_closedloop as m
ROOT=BASE/'inputs'
OUT=BASE/'results_v2'
POLICIES=['dr','s4','oracle_heading','oracle_xy','oracle_both','oracle_heading_gate','oracle_both_gate']
def save(name,obj):
    (OUT/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
def replay(ch,lv,policy,core,lut,case):
    f=m.get_input(ROOT,ch); c=m.get_controls(ROOT,ch,lv)
    t=f['t_s']; truth=f['truth_for_offline_scoring_only']; n=len(t)
    assert n==979 and np.all(np.diff(t)>0) and len(np.unique(f['pose_id']))==n
    x,P=m.make_initial(c)
    X=[]; C=[]; PX=[]; PC=[]; UX=[]; UC=[]; N=[]; A=[]; rows=[]
    for k in range(n):
        import r2_bias_replay
        xm,Pm=(x.copy(),P.copy()) if k==0 else r2_bias_replay.predict_one(x,P,float(c['ds_odom'][k]),float(c['dtheta_gyro'][k]),float(c['dt_s'][k]))
        xu,Pu,d=m.candidate(core,lut,case,xm,Pm,f['z_s'][k])
        b=m.scored(xm,Pm,truth[k]); a=m.scored(xu,Pu,truth[k])
        accept=m.select(policy,b,a,d['NIS'],ch,0.)
        x,P=(xu,Pu) if accept else (xm,Pm)
        assert np.isfinite(x).all() and np.isfinite(P).all() and np.isfinite(d['NIS'])
        assert np.linalg.eigvalsh(P).min()>0 and np.max(np.abs(P-P.T))<1e-12
        X.append(x.copy()); C.append(P.copy()); PX.append(xm.copy()); PC.append(Pm.copy())
        UX.append(xu.copy()); UC.append(Pu.copy()); N.append(d['NIS']); A.append(accept)
        rows.append(dict(m.scored(x,P,truth[k]),applied=int(accept)))
    arr=dict(X=np.array(X),P=np.array(C),prior_X=np.array(PX),prior_P=np.array(PC),candidate_X=np.array(UX),candidate_P=np.array(UC),nis=np.array(N),accepted=np.array(A),t=t,pose_id=f['pose_id'],truth=truth,R=np.array([[m.RS]]))
    mask=t>=40
    metric=m.statistics([r for r,yes in zip(rows,mask) if yes]); metric['applied_all']=int(sum(A))
    e=arr['X'][mask,:2]-truth[mask,:2]; cp=arr['P'][mask,:2,:2]
    nees=np.einsum('ni,ni->n',e,np.linalg.solve(cp,e[...,None])[...,0])
    metric.update(xy_nees=float(nees.mean()),xy_95_coverage=float(np.mean(nees<=5.991464547107979)),min_cov_eigenvalue=float(np.linalg.eigvalsh(arr['P']).min()))
    np.savez_compressed(OUT/f'{ch}_{lv}_{policy}.npz',**arr)
    return arr,metric
def main():
    OUT.mkdir(exist_ok=False)
    contract=dict(question='PALO-ORACLE-001',role='IMPLEMENTER',claim='선택적 편파 사용의 가능성을 탐색하는 진단 대조',base_commit='4c43020f04fbbf7d0510f792c4ab99a1d9f5ddb5',policies=POLICIES,oracle='instantaneous greedy error reduction; chosen x AND P carried recursively; exact frozen LUT recomputed at own prior',truth='oracle choice and offline scores only',scope='R2 anchor B seed0; 8 channel/level cases; 979 steps; report t>=40',gate=m.GATE,R=m.RS,parity_limits=dict(state=1e-7,cov=1e-8,nis=1e-7,status=0),exclusions='no RF quality oracle, no global-optimal or generalization claim',environment=dict(python=sys.version,numpy=np.__version__,platform=platform.platform()),started=datetime.now(timezone.utc).isoformat())
    save('CONTRACT.json',contract)
    core,lut,case=m.load_deps(ROOT)
    parity=[]; metrics=[]
    # All original S4 cases must pass before any hindsight branch is evaluated.
    for ch in m.CH:
      for lv in m.LV:
        arr,met=replay(ch,lv,'s4',core,lut,case); original=m.get_original(ROOT,ch,lv)
        vals=dict(channel=ch,level=lv,state=float(np.max(np.abs(arr['X']-original['estimate'][:,3]))),cov=float(np.max(np.abs(arr['P']-original['covariance'][:,3]))),nis=float(np.max(np.abs(arr['nis']-original['nis'][:,3]))),status=int(np.sum(arr['accepted']!=(original['status'][:,3]=='APPLIED'))))
        parity.append(vals); save('PARITY.json',parity); print('PARITY',vals,flush=True)
        assert all(np.isfinite(vals[k]) and vals[k]<=v for k,v in contract['parity_limits'].items()),'PARITY_FAIL'
        metrics.append(dict(channel=ch,level=lv,policy='s4',**met))
    save('PARITY_GATE_PASS.json',dict(cases=8,passed=True))
    for ch in m.CH:
      for lv in m.LV:
       for p in POLICIES:
        if p=='s4':continue
        _,met=replay(ch,lv,p,core,lut,case); metrics.append(dict(channel=ch,level=lv,policy=p,**met))
        print('DONE',ch,lv,p,met['heading_rmse_deg'],flush=True)
    assert len(metrics)==56 and all(r['n']==779 for r in metrics)
    save('SUMMARY.json',dict(status='EXECUTION_COMPLETE_SELF_CHECK_PENDING',metrics=metrics,finished=datetime.now(timezone.utc).isoformat()))
if __name__=='__main__':main()
