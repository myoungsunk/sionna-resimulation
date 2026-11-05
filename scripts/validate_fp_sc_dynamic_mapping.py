"""Frozen finite-domain mapping validation, not an E1-02/E2 stage runner."""
import os
for _k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[_k]='1'
import argparse,csv,datetime,itertools,json,math,platform,subprocess,sys,time
from pathlib import Path
import psutil
process=psutil.Process();process.cpu_affinity(process.cpu_affinity()[:3])
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from qclean_uwb.fp_sc.followup.contracts import Policy,sha256,verify_files,write_json,STEP_M
from qclean_uwb.fp_sc.followup.selection import native_support
from qclean_uwb.fp_sc.followup.numerics import cir_from_spectrum,raw_detection
from qclean_uwb.fp_sc.followup.data import load_case
from qclean_uwb.fp_sc.e0_baseline import load_original_model,SPEC

def directions():
    d=np.array([x for x in itertools.product((-1,0,1),repeat=3) if np.count_nonzero(x)>=2],float)
    return d/np.linalg.norm(d,axis=1)[:,None]

STRESSES=[('COV_001',0.,0.,0.),('X_PLUS',.5,0.,0.),('X_MINUS',-.5,0.,0.),
          ('Y_PLUS',0.,.5,0.),('Y_MINUS',0.,-.5,0.),('YAW_PLUS',0.,0.,math.pi/12),('YAW_MINUS',0.,0.,-math.pi/12)]

def stencil(x,P):
    ev,U=np.linalg.eigh(P[:3,:3]);A=U*np.sqrt(np.maximum(ev,0.))[None,:]
    points=np.tile(x,(7,1));points[1:4,:3]+=2*A.T;points[4:7,:3]-=2*A.T
    probe=np.tile(x,(20,1));probe[:,:3]+=2*directions()@A.T
    return points,probe

class Native:
    def __init__(self,model):self.model=model;self.states=0;self.calls=0;self.peak_rss=0
    def __call__(self,states):
        output=[]
        for start in range(0,len(states),128):
            x=states[start:start+128]
            _,_,diag=self.model.batch(x,SPEC,gradient=False,return_diagnostics=True)
            ranges=np.asarray(diag['native_range']);taps=np.asarray(diag['tap'])
            assert np.isfinite(ranges).all() and np.max(abs(ranges-taps*STEP_M))<=1e-10
            output.append(ranges);self.calls+=1;self.states+=len(x)
            self.peak_rss=max(self.peak_rss,process.memory_info().rss)
        geometry=np.sqrt(np.sum((states[:,:2]-np.asarray(SPEC['anchor'])[:2])**2,axis=1)+
                         (SPEC['anchor'][2]-SPEC['robot_z_m'])**2)
        return np.concatenate(output),geometry

def validate(root,out,manifest_path,contract_path):
    out.mkdir(parents=True,exist_ok=False);start=time.monotonic()
    manifest=json.loads(manifest_path.read_text())
    verify_files(root,manifest['input_files']);verify_files(root,manifest['baseline_sources'])
    policy=Policy(**manifest['policy'])
    assert policy.native_sigma_scale==2 and policy.mapping_slack_m==.15 and policy.max_prior_width_m==1.5
    code_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    assert not subprocess.check_output(['git','diff','HEAD','--','src','scripts','tests'],cwd=root).strip()
    receipt=dict(status='RUNNING',question_id='FP-SC-DYNAMIC-MAPPING-R1',code_commit=code_commit,
        contract_sha256=sha256(contract_path),input_manifest_sha256=sha256(manifest_path),
        started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        environment=dict(python=platform.python_version(),numpy=np.__version__,platform=platform.platform()),
        cpu_affinity=process.cpu_affinity(),E1_02_started=False,E2_started=False,
        candidate_generation_calls=0,real_select_calls=0,real_detection_calls=0,EKF_replay_calls=0)
    write_json(out/'RUN_RECEIPT.json',receipt)
    try:
        _,_,model,sources=load_original_model(root);native=Native(model)
        cols=['case_id','route','channel','k','pose_id','t','stratum','raw_tap','ref_tap','ref_valid',
            'native_center','geometry','offset','native_min','native_max','low','high','width','hold_width',
            'ref_in_support','usable_ref','probe_min','probe_max','probe_excess_m','endpoint_error_m']
        scols=['case_id','route','channel','k','pose_id','stress','ref_valid','low','high','width','hold_width',
               'ref_in_support','narrow_reference_exclusion']
        count=stress_count=0;max_endpoint=0.;special={}
        with (out/'NOMINAL.csv').open('x',newline='') as f,(out/'STRESS.csv').open('x',newline='') as sf:
            writer=csv.DictWriter(f,fieldnames=cols);writer.writeheader()
            sw=csv.DictWriter(sf,fieldnames=scols);sw.writeheader()
            for cid,spec in manifest['cases'].items():
                case,ev=load_case(root,spec,manifest['input_files'],None,detection_only=True)
                if not special:
                    x=case.prior[0].copy();zero=np.zeros((4,4))
                    z,_=native_support(x,zero,native,policy);center=native(x[None])[0][0]
                    wrap=np.tile(x,(3,1));wrap[:,2]+=[0,2*np.pi,-2*np.pi]
                    wr,_=native(wrap)
                    special=dict(zero_covariance_error=max(abs(z.low-(center-.15)),abs(z.high-(center+.15))),
                        yaw_periodic_error=float(np.ptp(wr)))
                    assert max(special.values())<=1e-10
                for base in range(0,len(case.t),16):
                    chunk=[];point_sets=[]
                    for k in range(base,min(base+16,len(case.t))):
                        pts,probe=stencil(case.prior[k],case.Pprior[k]);sets=[pts,probe]
                        for _,dx,dy,dyaw in STRESSES:
                            x=case.prior[k]+[dx,dy,dyaw,0.]
                            sets.append(stencil(x,case.Pprior[k]*.01)[0])
                        point_sets.append(sets);chunk.extend(sets)
                    states=np.concatenate(chunk);ranges,geometry=native(states);cursor=0
                    for j,sets in enumerate(point_sets):
                        k=base+j;rr=ranges[cursor:cursor+7];gg=geometry[cursor:cursor+7]
                        probes=ranges[cursor+7:cursor+27]
                        def replay_native(actual):
                            assert np.max(abs(actual-sets[0]))<=1e-10
                            return rr,gg
                        support,offset=native_support(case.prior[k],case.Pprior[k],replay_native,policy)
                        error=max(abs(support.low-(rr.min()-.15)),abs(support.high-(rr.max()+.15)))
                        assert error<=1e-10;max_endpoint=max(max_endpoint,float(error))
                        raw,_,_=raw_detection(cir_from_spectrum(case.Hrf[k]))
                        ref,_,_=raw_detection(cir_from_spectrum(ev.clean_H[k]))
                        valid=ref is not None
                        stratum=('invalid_reference' if not valid else 'invalid_raw' if raw is None else
                                 'normal' if raw==ref else 'one_tap' if abs(raw-ref)==1 else 'large_error')
                        low,high=support.low,support.high;width=high-low;hold=width>1.5
                        inside=bool(valid and low-1e-10<=ref*STEP_M<=high+1e-10)
                        excess=max(0.,low-float(probes.min()),float(probes.max())-high)
                        writer.writerow(dict(case_id=cid,route=case.route,channel=case.channel,k=k,
                            pose_id=int(case.pose_id[k]),t=float(case.t[k]),stratum=stratum,raw_tap=raw,ref_tap=ref,
                            ref_valid=int(valid),native_center=rr[0],geometry=gg[0],offset=offset,
                            native_min=rr.min(),native_max=rr.max(),low=low,high=high,width=width,
                            hold_width=int(hold),ref_in_support=int(inside),usable_ref=int(inside and not hold),
                            probe_min=probes.min(),probe_max=probes.max(),probe_excess_m=excess,endpoint_error_m=error))
                        for s,(name,*_) in enumerate(STRESSES):
                            sr=ranges[cursor+27+7*s:cursor+34+7*s];sl=float(sr.min()-.15);sh=float(sr.max()+.15)
                            si=bool(valid and sl-1e-10<=ref*STEP_M<=sh+1e-10);held=sh-sl>1.5
                            sw.writerow(dict(case_id=cid,route=case.route,channel=case.channel,k=k,pose_id=int(case.pose_id[k]),
                                stress=name,ref_valid=int(valid),low=sl,high=sh,width=sh-sl,hold_width=int(held),
                                ref_in_support=int(si),narrow_reference_exclusion=int(valid and not si and not held)))
                            stress_count+=1
                        cursor+=76;count+=1
                    assert cursor==len(states)
                    f.flush();sf.flush()
                print('MAPPING_CASE_COMPLETE',cid,len(case.t),'elapsed_s',round(time.monotonic()-start,1),flush=True)
        assert count==6272 and stress_count==43904
        receipt.update(status='COMPLETE_NUMERICAL_REVIEW_PENDING',rows=count,stress_rows=stress_count,
            source_hashes=sources,special_cases=special,max_endpoint_error_m=max_endpoint,
            model_states=native.states,model_batch_calls=native.calls,peak_rss_bytes=native.peak_rss,
            elapsed_s=time.monotonic()-start,files={n:sha256(out/n) for n in ('NOMINAL.csv','STRESS.csv')})
    except Exception:
        import traceback
        receipt.update(status='FAILED_PRESERVED',error=traceback.format_exc());raise
    finally:
        receipt['ended_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();write_json(out/'RUN_RECEIPT.json',receipt)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True);p.add_argument('--contract',type=Path,required=True)
    a=p.parse_args();validate(a.root.resolve(),a.output.resolve(),a.manifest,a.contract)
