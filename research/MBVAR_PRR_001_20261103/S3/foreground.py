"""Single-packet foreground EKF for checkpoint and cold replay."""
from copy import deepcopy
from dataclasses import dataclass
import math
import sys
from pathlib import Path

import numpy as np

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root/'S2'))
sys.path.insert(0, str(root/'S1'))
from recovery import Geometry, RecoveryMachine, validate_covariance
from online import GATE, joseph, predict, weight
from history import History, validate_candidate, source_registry

@dataclass
class Chain:
    x: object
    P: object
    shadow_x: object
    shadow_P: object
    geometry: object
    machine: object
    last_index: int = -1
    source_pose_ids: tuple = ()
    last_pose_id: object = None

def initial(packet, controls):
    x = np.r_[controls['x0'],0.]
    P = packet['P0'].copy()
    return Chain(x,P,x.copy(),P.copy(),Geometry(),RecoveryMachine(),source_pose_ids=source_registry(packet['pose_id']))

def frame(packet, controls, k):
    row = {key:packet[key][k] for key in ('t','z','muBASE','muMB','R','D','pose_id')}
    row.update({key:controls[key][k] for key in ('ds','gy','dt')})
    return row

def step(chain, row, k, prevention, historical, core, model, spec):
    if chain.last_index + 1 != k:
        raise ValueError('packet discontinuity')
    if k<0 or k>=len(chain.source_pose_ids) or row['pose_id']!=chain.source_pose_ids[k]:
        raise ValueError('source pose ID mismatch')
    if k and chain.last_pose_id!=chain.source_pose_ids[k-1]:
        raise ValueError('previous source pose ID mismatch')
    cov = row['R']
    if cov.dtype != np.float64 or np.any(cov[[0,1],[1,0]] != 0):
        raise ValueError('unexpected observation covariance')
    ct = {key:[row[key]] for key in ('ds','gy','dt')}
    def propagate(x,P):
        if k == 0: return x,P
        Q=np.diag([2e-5*abs(ct['ds'][0]),math.radians(.015)**2*ct['dt'][0],0.])
        return core.predict(x,P,ct['ds'][0],ct['gy'][0],ct['dt'][0],Q)[:2]
    sx,sp=propagate(chain.shadow_x,chain.shadow_P)
    h0,H0=model.batch(sx[None],spec)
    v0=row['z']-h0[0]-row['muBASE']
    gate=bool(v0@np.linalg.solve(H0[0]@sp@H0[0].T+cov,v0)<=GATE)
    chain.shadow_x,chain.shadow_P,_,_=joseph(sx,sp,H0[0],v0,cov,gate,1.)
    old=chain.x
    F=np.eye(4) if k==0 else core.transition(old,row['ds'],row['gy'],row['dt'])[1]
    rho=np.linalg.norm(old[:2]-np.asarray(spec['anchor'])[:2])
    sigma=np.interp(rho,[0,1.5,3,6,10],[.011,.020,.050,.120,.240])
    xp,pp=propagate(old,chain.P)
    h,H=model.batch(xp[None],spec)
    h,H=h[0],H[0]
    d0=row['z'][1]-h[1]
    risk_w=weight('W-d0-DS',d0,row['D'])
    applied=risk_w if prevention else 1.
    if historical: applied=min(applied,.25)
    rv=cov.copy()
    rv[1,1]+=sigma**2
    re=rv.copy()
    re[1,1]/=applied
    v=row['z']-h-row['muMB']
    chain.geometry.add(row['t'],H,re,F,gate)
    ok,conditional,marginal,_=chain.geometry.information()
    estimated=np.linalg.norm(xp[:2]-np.asarray(spec['anchor'])[:2])
    candidate,status=chain.machine.observe(row['t'],gate,risk_w,estimated,ok)
    chain.x,chain.P,K,S=joseph(xp,pp,H,v,re,gate,applied)
    validate_covariance(chain.P)
    chain.last_index=k
    chain.last_pose_id=chain.source_pose_ids[k]
    rec=dict(x=chain.x,P=chain.P,prior=xp,Pprior=pp,h=h,H=H,mu=row['muMB'],Rvar=rv,Reff=re,K=K,
             nu=v,S=S,d0=d0,weight=applied,sigma_b=sigma,rho_before=rho,nis=v@np.linalg.solve(S,v),
             mask=gate,conditional_lambda=conditional,marginal_lambda=marginal,
             candidate=candidate,episode_first=chain.machine.first if chain.machine.first is not None else -1.,
             shadow_x=chain.shadow_x.copy(),shadow_P=chain.shadow_P.copy())
    return rec,candidate

def state_record(chain):
    return dict(x=chain.x.tolist(),P=chain.P.tolist(),shadow_x=chain.shadow_x.tolist(),shadow_P=chain.shadow_P.tolist(),last_index=chain.last_index,last_pose_id=chain.last_pose_id,
                machine={k:list(v) if hasattr(v,'popleft') else (None if isinstance(v,float) and not math.isfinite(v) else v) for k,v in vars(chain.machine).items()},
                geometry=[(t,H.tolist(),R.tolist(),F.tolist(),accepted) for t,H,R,F,accepted in chain.geometry.history])

def replay(packet,controls,arm,core,model,spec,config_hash,*,seconds=60,identity=False,timed=False,
           capture_snapshots=False,start=0,end=None,initial_state=None,common_schedule=None,common_first=None):
    import time
    import psutil
    from cold_reference import cold_replay
    if arm not in ('A','B','C_CP','D_CP'): raise ValueError(arm)
    prevention=arm in ('B','D_CP');recovery=arm in ('C_CP','D_CP')
    if initial_state is None:
        chain=initial(packet,controls);hist=History(seconds,config_hash,packet['pose_id'])
        hist.save(-1,float(packet['t'][0])-1.,chain)
    else:
        chain,hist=deepcopy(initial_state)
        if chain.source_pose_ids!=tuple(packet['pose_id']) or hist.pose_ids!=chain.source_pose_ids:
            raise ValueError('snapshot source registry mismatch')
    emitted=[];events=[];retro=[];snapshots={};last_attempt=-math.inf
    stop=len(packet['t']) if end is None else end
    rows=[frame(packet,controls,k) for k in range(start,stop)]
    epoch=time.perf_counter_ns();peak=psutil.Process().memory_info().rss
    requested={int(np.searchsorted(packet['t'],t)) for t in (30,60,90) if t<=packet['t'][-1]}
    for k,row in zip(range(start,stop),rows):
        scheduled=epoch+int(round((float(row['t'])-float(packet['t'][start]))*1e9))
        if timed:
            remaining=(scheduled-time.perf_counter_ns())/1e9
            if remaining>0:time.sleep(remaining)
        tick=time.perf_counter_ns();queue=max(0,tick-scheduled) if timed else 0
        before=deepcopy((chain,hist)) if capture_snapshots else None
        if k and abs(float(row['t']-packet['t'][k-1])-.2)>1e-7:raise ValueError('timestamp drift')
        if not hist.append(k,row['t'],row):raise ValueError('invalid incoming stream')
        previous_first=chain.machine.first
        rec,candidate=step(chain,row,k,prevention,False,core,model,spec)
        first=chain.machine.first;pretreatment_prior=rec['prior'].copy()
        if capture_snapshots and (k in requested or (first is not None and first!=previous_first)):
            snapshots[k]=before
        if common_schedule is not None:
            candidate=bool(common_schedule[k]);first=float(common_first[k]) if candidate else first
        if candidate and first is not None and first>last_attempt:
            last_attempt=first
            if recovery:
                first_index=next((i for i,t,_ in hist.packets if abs(t-first)<1e-8),None)
                selected=hist.replay_input(first_index,k) if first_index is not None else None
                disposition='HISTORY_INSUFFICIENT';changed=[];path=[];cold_error=None;cp_record=None
                if selected:
                    cp,suffix=selected;proposed=cp.filter_state;cp_record=state_record(proposed)
                    cx,cP,ci,cold_path=cold_replay(proposed,suffix,prevention,first,identity,core,model,spec)
                    rebuilt=deepcopy(hist)
                    while rebuilt.checkpoints and rebuilt.checkpoints[-1].last_index>cp.last_index:rebuilt.checkpoints.pop()
                    rebuilt.next_checkpoint=cp.timestamp+1.-1e-10
                    for i,t,saved in suffix:
                        new,_=step(proposed,saved,i,prevention,not identity and t>=first,core,model,spec)
                        if t>=first and not identity:changed.append(i)
                        path.append((i,new['x'].copy(),new['P'].copy()))
                        if t>=rebuilt.next_checkpoint and i!=k:
                            from history import Checkpoint
                            rebuilt.checkpoints.append(Checkpoint(i,t,config_hash,deepcopy(proposed),proposed.last_pose_id))
                            rebuilt.next_checkpoint=t+1.-1e-10
                    cold_error=max(float(np.max(np.abs(cx-proposed.x))),float(np.max(np.abs(cP-proposed.P))))
                    if ci!=proposed.last_index or not np.allclose(cx,proposed.x,atol=1e-10,rtol=1e-10) or not np.allclose(cP,proposed.P,atol=1e-10,rtol=1e-10):raise ValueError('independent cold mismatch')
                    for a,b in zip(path,cold_path):
                        if a[0]!=b[0] or not np.allclose(a[1],b[1],atol=1e-10,rtol=1e-10) or not np.allclose(a[2],b[2],atol=1e-10,rtol=1e-10):raise ValueError('cold path mismatch')
                    disposition=validate_candidate(chain.x,proposed.x,proposed.P,proposed.last_index,k,end_pose_id=proposed.last_pose_id,current_pose_id=row['pose_id'])
                    if identity and (not np.allclose(chain.x,proposed.x,atol=1e-10,rtol=1e-10) or not np.allclose(chain.P,proposed.P,atol=1e-10,rtol=1e-10)):raise ValueError('identity mismatch')
                    if disposition=='ACCEPT':
                        proposed.machine.first=first;proposed.machine.commit(row['t']);chain,hist,rec=proposed,rebuilt,new
                        retro.append((k,path))
                events.append(dict(index=k,first=first,checkpoint=selected[0].last_index if selected else None,
                                   checkpoint_state=cp_record,historical_indices=changed,disposition=disposition,
                                   cold_max_abs=cold_error,end_index=k,end_pose_id=proposed.last_pose_id if selected else None,current_pose_id=row['pose_id'].item() if isinstance(row['pose_id'],np.generic) else row['pose_id'],
                                   checkpoint_pose_id=selected[0].last_pose_id if selected else None,
                                   historical_pose_ids=[chain.source_pose_ids[i] for i in changed],identity=identity))
            else:chain.machine.commit(row['t'])
        hist.save(k,row['t'],chain)
        finish=time.perf_counter_ns();memory=psutil.Process().memory_info();peak=max(peak,getattr(memory,'peak_wset',memory.rss))
        rec['pre_replay_prior']=pretreatment_prior
        rec['latency_ns']=finish-tick;rec['queue_wait_ns']=queue
        rec['arrival_to_emitted_ns']=finish-scheduled if timed else -1
        rec['sample_index']=k;emitted.append(rec)
    tr={key:np.asarray([r[key] for r in emitted]) for key in emitted[0]}
    timing=dict(real_clock_5Hz=timed,packets=len(rows),dropped_packets=0,peak_resident_bytes=peak,
                timed_p99_ms=float(np.quantile(tr['arrival_to_emitted_ns'],.99)/1e6) if timed else None,
                timed_max_ms=float(tr['arrival_to_emitted_ns'].max()/1e6) if timed else None,
                wall_clock_s=(time.perf_counter_ns()-epoch)/1e9)
    return tr,events,retro,snapshots,timing
