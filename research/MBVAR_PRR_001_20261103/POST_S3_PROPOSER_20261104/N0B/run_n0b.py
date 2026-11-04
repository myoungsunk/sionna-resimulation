"""Run the registered N0B comparisons; evaluator truth is loaded after branching."""
import datetime
import json
import os
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from approval import authorize,bind,digest,here,pkg,plan_commit
from endpoints_n0b import measure
from summary_n0b import aggregate
from rates import tabulate

def put(p,value):
    p.write_text(json.dumps(value,indent=2,allow_nan=False,default=lambda v:v.item()),encoding='utf8')
def truth_for(p,key,ids):
    path=p.cache.parent/'evaluator_truth'/(key+'.npz')
    if digest(path)!=p.lock['evaluator_truth/'+path.name]:raise ValueError('truth hash')
    with np.load(path) as z:
        assert np.array_equal(ids,z['pose_id'])
        return z['truth'],z['bg']
def evaluate(output):
    grant=authorize()
    from branching import iter_event_pairs
    from positive_control import positive_controls
    sys.path.insert(0,str(pkg/'S1'))
    import parity as p
    output.mkdir(parents=True,exist_ok=False)
    manifest=dict(grant=grant,utc_start=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=sys.argv,status='RUNNING')
    put(output/'MANIFEST.json',manifest)
    rows=[];files=[];parity_rows=[]
    try:
        receipt=positive_controls(p.b.core,p.b.model,p.spec,p.online,p.read,p.read)
        put(output/'R4_POSITIVE_CONTROLS.json',receipt)
        labels=pd.read_csv(here.parent/'P0/LABELS.csv').query("phase=='EVAL'").copy()
        assert len(labels)==520 and labels.event.is_unique
        for stage,sg in labels.groupby('stage'):
            source=pkg/stage/'runs/EVAL_001'
            index={r['file']:r for r in json.loads((source/'TRACE_INDEX.json').read_bytes())}
            events=json.loads((source/'EVENTS.json').read_bytes())
            for (route,bias,ch,seed,arm),group in sg.groupby(['route','bias','channel','seed','arm']):
                stop=os.environ.get('MANAGED_PROCESS_STOP_FILE')
                if stop and Path(stop).exists():raise InterruptedError('owner stop')
                short=f'{route}_aB_m0_{bias}';name=short+'_'+ch;pk=p.read(name);ct=p.read(short+'_'+str(seed))
                fname=f'{name}_{seed}_{arm}'+('_main' if stage=='S3' else '')+'.npz'
                if digest(source/fname)!=index[fname]['sha256']:raise ValueError('natural output hash')
                natural_events=[e for e in events if all(e[k]==v for k,v in dict(route=route,bias=bias,channel=ch,seed=seed,arm=arm,kind='P').items())]
                lookup=group.set_index('index',verify_integrity=True)
                assert set(lookup.index)=={e['index'] for e in natural_events}
                config=digest(pkg/'S3/RULES.json')
                with np.load(source/fname) as orig:
                    natural={k:orig[k] for k in orig.files}
                pairs=iter_event_pairs(stage,pk,ct,arm,p.b.core,p.b.model,p.spec,p.online,natural,natural_events,config,target_indices=set(lookup.index))
                for pair in pairs:
                    k=pair.index; source_row=lookup.loc[k];on,off=pair.on,pair.off;ids=on['sample_index']
                    assert np.array_equal(ids,off['sample_index']) and np.array_equal(pk['pose_id'][ids],on['pose_id'])
                    assert np.array_equal(on['pose_id'],off['pose_id']) and np.array_equal(on['mask'],off['mask'])
                    truth,bg=truth_for(p,short,pk['pose_id']);before=pair.pretreatment_prior
                    dh=abs(np.degrees(np.angle(np.exp(1j*(before[2]-truth[k,2])))));dx=np.linalg.norm(before[:2]-truth[k,:2])
                    accurate=bool(dh<=1 and dx<=.1)
                    assert accurate==source_row.accurate and np.allclose([dh,dx],[source_row.head_deg,source_row.xy_m],atol=1e-10,rtol=1e-10)
                    disp=pair.disposition
                    assert disp==source_row.disposition
                    applied=bool(source_row.applied)
                    aa,bb=[measure(pk['t'][ids],tr['x'],tr['P'],truth[ids],np.asarray(bg)[ids] if np.ndim(bg) else bg,accurate) for tr in (on,off)]
                    rec=dict(event=source_row.event,stage=stage,route=route,bias=bias,channel=ch,seed=seed,arm=arm,index=k,pose_id=pair.pose_id,time=float(pk['t'][k]),accurate=accurate,applied=applied,disposition=disp,start_hash=pair.start_hash,start_heading_deg=dh,start_xy_m=dx)
                    for name_,value in aa.items():
                        rec['on_'+name_]=value;rec['off_'+name_]=bb[name_]
                        if name_ not in ('available_s','full_10','full_20') and value is not None and bb[name_] is not None:
                            rec['delta_'+name_]=float(value)-float(bb[name_])
                    if not aa['full_20']:rec['delta_exit_observed']=np.nan
                    a=rec['delta_head_int_20'];b=rec['delta_xy_int_20']
                    rec['effect']=('censored' if not aa['full_20'] else 'tie' if abs(a)<=1e-7 and abs(b)<=1e-8 else 'benefit' if a < -1e-7 and b < -1e-8 else 'harm' if a>1e-7 and b>1e-8 else 'mixed')
                    if not applied and (not np.allclose(on['x'],off['x'],atol=1e-10,rtol=1e-10) or not np.allclose(on['P'],off['P'],atol=1e-10,rtol=1e-10) or rec['effect'] not in ('tie','censored')):raise ValueError('rejected candidate diverged')
                    for endpoint,flag1,flag2,eligible in [
                        ('recovered',np.isfinite(aa['recovery_s']),np.isfinite(bb['recovery_s']),not accurate),
                        ('exited',aa['exit_observed'],bb['exit_observed'],accurate),
                        ('reentered',np.isfinite(aa['reentry_s']),np.isfinite(bb['reentry_s']),accurate and (aa['exit_observed'] or bb['exit_observed']))]:
                        for lbl,test in [('on_only',flag1 and not flag2),('off_only',flag2 and not flag1),('both',flag1 and flag2),('neither',not flag1 and not flag2)]:
                            rec[lbl+'_'+endpoint]=bool(test) if eligible and aa['full_20'] else None
                    f=output/(source_row.event+'.npz');np.savez_compressed(f,t=pk['t'][ids],pose_id=on['pose_id'],prior=before,on_x=on['x'],on_P=on['P'],off_x=off['x'],off_P=off['P'],mask=on['mask'],on_weight=on['weight'],off_weight=off['weight'],on_Pprior=on['Pprior'],off_Pprior=off['Pprior'],on_applied=on['recovery_applied'],off_applied=off['recovery_applied'],on_suppressed=on['recovery_suppressed'],off_suppressed=off['recovery_suppressed'])
                    files.append(dict(event=source_row.event,file=f.name,sha256=digest(f)))
                    parity_rows.append(dict(event=source_row.event,parity=pair.parity,decision=pair.decision))
                    rows.append(rec)
                print(stage,route,bias,ch,seed,arm,len(rows),flush=True)
        df=pd.DataFrame(rows)
        assert len(df)==520 and df.event.is_unique and set(df.event)==set(labels.event)
        df.to_csv(output/'EVENT_RESULTS.csv',index=False);aggregate(df,output);tabulate(df,output)
        put(output/'PARITY.json',parity_rows);put(output/'TRACE_INDEX.json',files)
        manifest.update(status='COMPLETE',utc_end=datetime.datetime.now(datetime.timezone.utc).isoformat(),pairs=len(rows))
    except BaseException as exc:
        manifest.update(status='FAILED',error=repr(exc),completed_pairs=len(rows));raise
    finally:put(output/'MANIFEST.json',manifest)
if __name__=='__main__':evaluate(Path(sys.argv[1]))




