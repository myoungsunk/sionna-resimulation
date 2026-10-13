"""Execute unchanged D5 runner, with observational motion/FilterStep sidecars."""
from pathlib import Path
import dataclasses, datetime, hashlib, json, os, sys
import numpy as np

BASE=Path(__file__).resolve().parent
REPO=BASE.parent/'checkout'
DIAG=REPO/'research/EKF3_INDEPENDENT_20261013/diagnostics'
sys.path[:0]=[str(DIAG),str(DIAG.parent)]
import run_d5_regimes as d5

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    case_id,phase=sys.argv[1:3]
    conditions=['noise_pair','all'] if phase=='smoke' else ['gyro_bias','gyro_sf','wheel_asymmetry','slip']
    base=BASE/'D5_PARTS'/phase/case_id;base.mkdir(parents=True,exist_ok=False)
    evidence=base/'evidence';evidence.mkdir()
    original_run=d5.run_one;original_gen=d5.generate
    original_init=d5.EKF3.__init__;original_record=d5.EKF3._record
    context={};input_hashes={};run_records=[]
    def capture_generate(t,ds,dy,cfg,seed,*args,**kwargs):
        values,eval_only=original_gen(t,ds,dy,cfg,seed,*args,**kwargs)
        key=f"{context['route']}_{cfg.condition}_L{cfg.level}_seed{seed}"
        initial=d5.sensor_rng(seed,'initial').standard_normal(3)*np.array([.1,.1,np.radians(5)])
        arrays={**values,'initial_noise':initial,'pose_id':context['pose_ids']}
        h=hashlib.sha256()
        for name in sorted(arrays):
            ar=np.asarray(arrays[name]);h.update(name.encode());h.update(str(ar.dtype).encode());h.update(str(ar.shape).encode());h.update(ar.tobytes())
        signature=h.hexdigest()
        if key in input_hashes:assert input_hashes[key]['array_signature']==signature,'Paired sensor stream changed'
        else:
            target=evidence/(key+'_MOTION.npz');np.savez_compressed(target,**arrays)
            input_hashes[key]={'array_signature':signature,'sha256':digest(target),'file':target.name,'config':cfg.manifest() if hasattr(cfg,'manifest') else dataclasses.asdict(cfg)}
        context['motion_key']=key
        return values,eval_only
    def capture_init(self,*args,**kwargs):
        original_init(self,*args,**kwargs)
        if context:
            ordinal=len(context['instances']);assert ordinal<4
            context['instances'][id(self)]=ordinal
    def capture_record(self,*args,**kwargs):
        rec=original_record(self,*args,**kwargs)
        if context:
            arm=context['instances'][id(self)]
            if rec.name=='predict':context['k'][arm]+=1
            k=context['k'][arm];event=0 if rec.name=='predict' else 1
            data=context['trace'];data['valid'][k,arm,event]=True
            data['status'][k,arm,event]=rec.status
            for name in ['prior_x','prior_P','post_x','post_P','innovation','predicted_measurement','H','R','S','K','F','G','Q_input','Q_model']:
                value=getattr(rec,name)
                if value is not None:
                    array=np.asarray(value);index=(k,arm,event)+tuple(slice(0,s) for s in array.shape)
                    data[name][index]=array
            if rec.NIS is not None:data['NIS'][k,arm,event]=rec.NIS
        return rec
    def capture_run(case,channel,level,condition,seed,time,truth,pose_ids,obs,range_model,range_physical,lut):
        key=f"{case['id']}_{channel}_{range_model}_{condition}_L{level}_seed{seed}"
        n=len(time);context.clear();context.update(route=case['route'],pose_ids=pose_ids,instances={},k=[0]*4)
        shapes={'prior_x':(3,),'prior_P':(3,3),'post_x':(3,),'post_P':(3,3),'innovation':(2,),'predicted_measurement':(2,),'H':(2,3),'R':(2,2),'S':(2,2),'K':(3,2),'F':(3,3),'G':(3,2),'Q_input':(2,2),'Q_model':(3,3),'NIS':()}
        trace={name:np.full((n,4,2)+shape,np.nan) for name,shape in shapes.items()}
        trace.update(valid=np.zeros((n,4,2),bool),status=np.full((n,4,2),'not_called',dtype='<U16'))
        context['trace']=trace
        output,groups=original_run(case,channel,level,condition,seed,time,truth,pose_ids,obs,range_model,range_physical,lut)
        assert np.sum(trace['valid'][:,:,0])==4*(n-1)
        assert np.sum(trace['valid'][:,:,1])==3*n
        assert np.isfinite(trace['NIS'][:,1:,1]).all()
        target=evidence/(key+'_FILTER.npz')
        np.savez_compressed(target,**trace,t_s=time,pose_id=pose_ids,raw_s=obs['s'],range_physical=range_physical,
            arms=np.array(['D0','A','B','C']),events=np.array(['predict','update']))
        record={'key':key,'motion_key':context['motion_key'],'trace_file':target.name,'sha256':digest(target),'n_steps':n,'pre_gate_NIS_count':3*n}
        run_records.append(record)
        with (base/'completed_runs.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(record)+'\n')
        context.clear()
        return output,groups
    d5.generate=capture_generate;d5.run_one=capture_run
    d5.EKF3.__init__=capture_init;d5.EKF3._record=capture_record
    cli=['run_d5_regimes.py','--out',str(base/'OUTPUT'),'--cases',case_id,'--seeds','0','1','2','--levels','0','1','2','--conditions',*conditions,'--channels','los','full','--range-models','B_OLD','E1_FULL_LORO']
    started=datetime.datetime.now(datetime.timezone.utc).isoformat();sys.argv=cli
    exit_code=d5.main()
    (base/'EVIDENCE_MANIFEST.json').write_text(json.dumps({'started_utc':started,'finished_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'command':cli,'code_revision':'701b8d2c29a4b3b879c4e27096168d6be463559b','harness_sha256':digest(__file__),'exit_code':exit_code,'inputs':input_hashes,'runs':run_records,'recording_only':True,'scientific_PASS':False},indent=2),encoding='utf-8')
    return exit_code

if __name__=='__main__':raise SystemExit(main())
