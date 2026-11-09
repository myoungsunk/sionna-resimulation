"""Evaluator-only SourceFFD wrong-reference and clean-return diagnostics.

All constructed ideal RF is h_SourceFFD(truth)+muMB. It is NOT clean/LoS CIR,
an observed sensor measurement, or a new physical channel simulation. Oracle
truth is local to this evaluator and never added to the runtime Monitor API.
Each comparison is from a fixed main prior; no modified posterior is recycled.
"""
from __future__ import annotations
import argparse,csv,json,time,hashlib
from pathlib import Path
from dataclasses import asdict,replace
import numpy as np
from experiment import context,packet_for,config_for,read_npz,ROOT
from mcg import profile_history,score_current,weights,covariance_update,wrap


def clean_json(x):
    if isinstance(x,np.ndarray):return clean_json(x.tolist())
    if isinstance(x,dict):return {str(k):clean_json(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [clean_json(v) for v in x]
    if isinstance(x,(np.integer,np.bool_)):return x.item()
    if isinstance(x,(float,np.floating)):return float(x) if np.isfinite(x) else None
    return x


def save(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(clean_json(obj),indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def loss(x,truth):
    return np.array([float(np.degrees(wrap(x[2]-truth[2]))**2),float(np.sum((x[:2]-truth[:2])**2))])


def action_comparison(x,P,h,H,z,mu,R,beta,truth,permitted):
    values={};states={}
    for name,b in [('SKIP',(0.,0.)),('B',(1.,1.)),('GUARD',beta)]:
        y,_,_,_,_=covariance_update(x,P,H,z-h-mu,R,b,permitted)
        values[name]=loss(y,truth);states[name]=y
    gain=values['SKIP']-values['B'];lost=np.maximum(values['GUARD']-values['B'],0)
    ratios=[float(lost[j]/gain[j]) if gain[j]>[1e-12,1e-14][j] else None for j in range(2)]
    return {'permitted':bool(permitted),'metric_order':['heading_deg2','xy_m2'],
        'loss':values,'states':states,'baseline_gain_vs_skip':gain,
        'guard_net_gain_vs_B':values['B']-values['GUARD'],
        'lost_beneficial_gain_ratio':ratios}


def main(a):
    out=a.out;out.mkdir(parents=True,exist_ok=True)
    implementation_sha256=hashlib.sha256(Path(__file__).with_name('mcg.py').read_bytes()).hexdigest()
    script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    start=time.perf_counter();r45,core,online,model,hashes=context()
    cfg=config_for(tau=a.tau,span=5.)
    allrows=[];source=[];selected={}
    for route in ['R2','R4','R5']:
        packet,_,_=packet_for(r45,route,'B_FROZEN',a.archives)
        tr=read_npz(a.archives/route/f'{route}_B_FROZEN.npz')
        htpath=a.model_truth/f'{route}_htruth.npz';ht=read_npz(htpath)
        truth=ht['truth'];htruth=ht['htruth'];n=len(truth)
        assert np.array_equal(ht['t'],packet['t']) and np.array_equal(ht['pose_id'],packet['pose_id'])
        source.append({'route':route,'htruth_sha256':hashlib.sha256(htpath.read_bytes()).hexdigest(),
            'htruth_source_hashes':json.loads(str(ht['source_hashes_json'])),
            'baseline_sha256':hashlib.sha256((a.archives/route/f'{route}_B_FROZEN.npz').read_bytes()).hexdigest()})
        ideal=htruth+packet['muMB']
        controls=np.column_stack([packet[v] for v in ('ds','gy','dt')])
        old=read_npz(ROOT/'research/FP_SC_RECOVERY_R0_R5_20261107/R45_RUN_001'/f'{route}_TRACE.npz')
        arm_names=[str(x) for x in old['arms']];bi=arm_names.index('B')
        assert np.array_equal(old['t'],packet['t']) and np.array_equal(old['pose_id'],packet['pose_id'])
        assert np.max(np.abs(old['x'][:,bi]-tr['x']))<1e-10
        eligible=np.flatnonzero(packet['t']-packet['t'][0]>=5.-1e-9)
        starts=np.searchsorted(packet['t'],packet['t'][eligible]-5.-1e-9)
        worst=int(eligible[np.argmax(abs(tr['prior'][starts,3]))])
        events=list(dict.fromkeys([worst]+[max(25,min(n-1,int((n-1)*f))) for f in (.25,.5,.75)]))
        selected[route]={'selection':'max absolute stored anchor gyro_bias at a 5-second window; fixed 25/50/75 percent indices',
            'indices':events,'max_anchor_bias_window_target_index':worst,'profile_protection_index':events[2] if len(events)>2 else events[-1]}
        cache={}

        def gate(k,z):
            if k not in cache:
                sx=old['shadow_x'][k-1,bi].copy() if k else packet['x0'].copy()
                sp=old['shadow_P'][k-1,bi].copy() if k else packet['P0'].copy()
                cc={v:packet[v] for v in ('ds','gy','dt')};cc['x0']=packet['x0'][:3]
                sx,sp=online.predict(core,sx,sp,k,cc)
                hh,HH=model.batch(sx[None],r45.SPEC);HH=HH[0];hh=hh[0]
                S=HH@sp@HH.T+packet['R'][k]
                v=packet['z'][k]-hh-packet['muBASE'][k]
                raw_nis=float(v@np.linalg.solve(S,v))
                assert bool(raw_nis<=online.GATE)==bool(tr['mask'][k])
                cache[k]=(hh,S,sx,sp,raw_nis)
            hh,S,sx,sp,raw_nis=cache[k]
            v=z-hh-packet['muBASE'][k];nis=float(v@np.linalg.solve(S,v))
            return bool(nis<=online.GATE),nis,raw_nis

        def evaluate(name,k,anchor,history,current,cfg_here=cfg,main_x=None,main_P=None,family='RAW_HISTORY_IDEAL_TARGET',current_kind='MAIN_MODEL_CONSISTENT_IDEAL'):
            aa=int(np.searchsorted(packet['t'],packet['t'][k]-cfg_here.span_s-1e-9))
            p=profile_history(core,model,r45.SPEC,anchor,controls[aa:k+1],packet['t'][aa:k+1],
                history,packet['muMB'][aa:k],tr['Reff'][aa:k+1],cfg_here)
            sc=score_current(p,current,packet['muMB'][k]);beta,status=weights(sc,cfg_here)
            mx=tr['prior'][k].copy() if main_x is None else main_x.copy()
            mp=tr['Pprior'][k].copy() if main_P is None else main_P.copy()
            hh,HH=model.batch(mx[None],r45.SPEC);hh=hh[0];HH=HH[0]
            allowed,nis,raw_nis=gate(k,current)
            row={'route':route,'k':k,'t_s':float(packet['t'][k]),'anchor_index':aa,'family':family,'name':name,
                'current_kind':current_kind,'profile_reason':p['reason'],'profile_status':p['status'],'status':status,
                'valid_channels':sc['valid_channels'],'scores':sc['scores'],'beta':beta,
                'theta':p['theta'],'anchor':anchor,'rank':p['rank'],'target_span_sigma':p['target_span_sigma'],
                'profile_cost':p['profile_cost'],'linearity_sigma':p['linearity_sigma'],'config_sha256':cfg_here.digest(),
                'candidate_count':p.get('candidate_count'),'stationarity_per_sample':p.get('stationarity_per_sample'),
                'refinements':p.get('refinements'),'boundary_support':p.get('boundary_support'),
                'boundary_target_shift_sigma':p.get('boundary_target_shift_sigma'),
                'legacy_current_gate':allowed,'legacy_current_gate_nis':nis,'legacy_raw_gate':bool(tr['mask'][k]),
                'legacy_raw_gate_nis_recomputed':raw_nis,
                'gate_context':'Archived raw-B shadow history held fixed; constructed history is monitor-only.',
                'actual':action_comparison(mx,mp,hh,HH,current,packet['muMB'][k],tr['Reff'][k],beta,truth[k],allowed),
                'forced_hypothetical':action_comparison(mx,mp,hh,HH,current,packet['muMB'][k],tr['Reff'][k],beta,truth[k],True)}
            allrows.append(row)
            if len(allrows)%15==0:print('SOURCE_STRESS',len(allrows),'elapsed_s',round(time.perf_counter()-start,1),flush=True)
            return row

        for k in events:
            aa=int(np.searchsorted(packet['t'],packet['t'][k]-5.-1e-9));anchor=tr['prior'][aa].copy()
            at=anchor.copy();at[:3]=truth[aa]
            bg=anchor.copy();bg[3]=0.
            hcheck,_=model.batch(np.r_[truth[k],0.][None],r45.SPEC,gradient=False)
            assert np.max(abs(hcheck[0]-htruth[k]))<1e-12
            evaluate('RAW_HISTORY',k,anchor,packet['z'][aa:k],ideal[k])
            evaluate('ORACLE_ANCHOR_POSE_ONLY',k,at,packet['z'][aa:k],ideal[k])
            evaluate('ORACLE_ANCHOR_BG_ZERO_ONLY',k,bg,packet['z'][aa:k],ideal[k])
            evaluate('ORACLE_HISTORY_IDEAL_ONLY',k,anchor,ideal[aa:k],ideal[k])
            evaluate('PROFILE_BOUNDS_DOUBLED_ONLY',k,anchor,packet['z'][aa:k],ideal[k],replace(cfg,bounds=tuple(np.array(cfg.bounds)*2)))

        k=selected[route]['profile_protection_index'];aa=int(np.searchsorted(packet['t'],packet['t'][k]-5.-1e-9))
        at=np.r_[truth[aa],0.]
        for deg in [-20,-10,-5,5,10,20]:
            perturbed=at.copy();perturbed[2]=wrap(perturbed[2]+np.radians(deg))
            evaluate('ANCHOR_YAW_%+d_DEG'%deg,k,perturbed,ideal[aa:k],ideal[k],family='REFERENCE_ONLY_PERTURBATION')
        for axis in [0,1]:
            for shift in [-.5,.5]:
                perturbed=at.copy();perturbed[axis]+=shift
                evaluate('ANCHOR_%s_%+.1f_M'%(['X','Y'][axis],shift),k,perturbed,ideal[aa:k],ideal[k],family='REFERENCE_ONLY_PERTURBATION')
        for bgdeg in [-.1,.1]:
            perturbed=at.copy();perturbed[3]=np.radians(bgdeg)
            evaluate('ANCHOR_BG_%+.1f_DEG_S'%bgdeg,k,perturbed,ideal[aa:k],ideal[k],family='REFERENCE_ONLY_PERTURBATION')

        # Synthetic coherent history through the ORIGINAL SOURCE observer; no new
        # channel/ray trace. Rigid XY/yaw transform preserves path shape exactly.
        delta=.3;rot=np.array([[np.cos(delta),-np.sin(delta)],[np.sin(delta),np.cos(delta)]])
        transformed=np.column_stack([truth[aa:k+1],np.zeros(k-aa+1)])
        transformed[:,:2]=(truth[aa:k+1,:2]-truth[aa,:2])@rot.T+truth[aa,:2]+np.array([.3,.3])
        transformed[:,2]=wrap(truth[aa:k+1,2]+delta)
        hz,_=model.batch(transformed,r45.SPEC,gradient=False);hz+=packet['muMB'][aa:k+1]
        mx=np.r_[truth[k],0.]+np.array([.1,-.1,.05,0.])
        mp=np.diag([.01,.01,np.radians(5.)**2,np.radians(.1)**2])
        evaluate('COHERENT_WRONG_HISTORY_AND_TARGET',k,at,hz[:-1],hz[-1],main_x=mx,main_P=mp,
            family='CONSTRUCTED_COHERENT_SOURCE_MODEL',current_kind='RIGIDLY_TRANSFORMED_SOURCE_MODEL')
        evaluate('COHERENT_WRONG_HISTORY_IDEAL_RETURN',k,at,hz[:-1],ideal[k],main_x=mx,main_P=mp,
            family='CONSTRUCTED_COHERENT_SOURCE_MODEL')
        evaluate('ORACLE_HISTORY_IDEAL_RETURN',k,at,ideal[aa:k],ideal[k],main_x=mx,main_P=mp,
            family='CONSTRUCTED_COHERENT_SOURCE_MODEL')
        save(out/f'{route}_SOURCE_STRESS.json',{'route':route,'rows':[r for r in allrows if r['route']==route]})

    groups={}
    for family in sorted(set(r['family'] for r in allrows)):
        rows=[r for r in allrows if r['family']==family]
        reasons={reason:sum(r['profile_reason']==reason for r in rows) for reason in sorted(set(r['profile_reason'] for r in rows))}
        groups[family]={'n':len(rows),'any_valid':sum(bool(np.any(r['valid_channels'])) for r in rows),
            'both_valid':sum(bool(np.all(r['valid_channels'])) for r in rows),
            'damped':sum(bool(np.any(r['beta']<1)) for r in rows),
            'legacy_current_rejected':sum(not r['legacy_current_gate'] for r in rows),
            'reason_counts':reasons}
    report={'status':'EVALUATOR_ONLY_SOURCEFFD_STRESS_EXECUTED','n_profiles':len(allrows),'config':asdict(cfg),
        'implementation_sha256':implementation_sha256,'script_sha256':script_sha256,
        'scope':'Selected one-step diagnostic counterfactuals; constructed ideal RF is htruth+muMB, not observed clean CIR.',
        'no_prevalence_or_generalization_claim':True,'no_modified_posterior_propagation':True,
        'legacy_shadow_context':'Original raw B prior; no hypothetical historical changes are propagated to legacy shadow.',
        'selection':selected,'groups':groups,'source_hashes':hashes,'inputs':source,'elapsed_s':time.perf_counter()-start}
    assert hashlib.sha256(Path(__file__).with_name('mcg.py').read_bytes()).hexdigest()==implementation_sha256,'RUNTIME_CHANGED_DURING_STRESS'
    save(out/'SOURCE_STRESS_SUMMARY.json',report)
    fields=['route','k','t_s','family','name','profile_reason','status','valid_r','valid_s','beta_r','beta_s','score_r','score_s','score_joint','legacy_current_gate','legacy_current_gate_nis','forced_heading_B_gain','forced_xy_B_gain','forced_heading_lost_ratio','forced_xy_lost_ratio','actual_heading_lost_ratio','actual_xy_lost_ratio']
    with (out/'SOURCE_STRESS_ROWS.csv').open('w',newline='') as f:
        wr=csv.DictWriter(f,fieldnames=fields);wr.writeheader()
        for r in allrows:
            row={key:r[key] for key in ['route','k','t_s','family','name','profile_reason','status','legacy_current_gate','legacy_current_gate_nis']}
            row.update(valid_r=r['valid_channels'][0],valid_s=r['valid_channels'][1],beta_r=r['beta'][0],beta_s=r['beta'][1],score_r=r['scores'][0],score_s=r['scores'][1],score_joint=r['scores'][2])
            row.update(forced_heading_B_gain=r['forced_hypothetical']['baseline_gain_vs_skip'][0],forced_xy_B_gain=r['forced_hypothetical']['baseline_gain_vs_skip'][1],forced_heading_lost_ratio=r['forced_hypothetical']['lost_beneficial_gain_ratio'][0],forced_xy_lost_ratio=r['forced_hypothetical']['lost_beneficial_gain_ratio'][1],actual_heading_lost_ratio=r['actual']['lost_beneficial_gain_ratio'][0],actual_xy_lost_ratio=r['actual']['lost_beneficial_gain_ratio'][1])
            wr.writerow(clean_json(row))
    print(json.dumps(clean_json(report),ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--archives',type=Path,required=True);p.add_argument('--model-truth',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--tau',type=float,default=3.)
    main(p.parse_args())
