"""Freeze provenance, run synthetic/numerical gates, then one actual paired smoke."""
import csv,json,math,sys,time,traceback,subprocess
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
import h3_offline as h
from h3_offline import c,C,ROOT,REPO

CACHE=Path('D:/SLAM_bot/artifacts/EKF3_ROBUST_FUSION_20261013/M0')
REFERENCE=REPO/'research/EKF3_INDEPENDENT_20261013/diagnostics/robust_fusion/results/LOSS_FAMILY_20261013'
def write(name,rows):
    with (OUT/name).open('w',newline='',encoding='utf-8') as f:
        fields=list(dict.fromkeys(k for r in rows for k in r));w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def synth():
    results=[]
    # Sequential conditioning must agree with joint update at ONE fixed linearization.
    for cross in (-.4,0.,.4):
        P=np.array([[.3,.01,.03],[.01,.2,.02],[.03,.02,.1]])
        H=np.array([[.4,.2,-.8],[.7,-.1,0.]])
        R=np.array([[.1,cross*.2],[cross*.2,.4]])
        y=np.array([.15,-.12]);K=np.linalg.solve(H@P@H.T+R,H@P).T
        joint=K@y;JP=P-K@H@P
        hr=H[1];kr=P@hr/(hr@P@hr+R[1,1]);x=kr*y[1]
        RP=P-np.outer(kr,hr@P);alpha=R[0,1]/R[1,1]
        hs=H[0]-alpha*hr;vs=R[0,0]-R[0,1]**2/R[1,1]
        residual=y[0]-alpha*y[1]-hs@x;ks=RP@hs/(hs@RP@hs+vs)
        seq=x+ks*residual;SP=RP-np.outer(ks,hs@RP)
        err=max(np.max(abs(seq-joint)),np.max(abs(SP-JP)))
        if err>1e-10:raise RuntimeError('Conditional sequential/joint synthetic mismatch')
        results.append(dict(test='linear_joint_sequential',cross=cross,max_difference=float(err)))
    # Circular seam and explicitly separated two-mode HPD region.
    one=lambda q:h.wrapped_logprior(q,np.pi-.01,.1**2)
    po=h.posterior(one)
    if abs(h.wrap(po['MAP']-(np.pi-.01)))>1e-6 or abs(po['prob'].sum()-1)>1e-12:
        raise RuntimeError('Circular normalization/MAP gate')
    two=lambda q:np.logaddexp(h.wrapped_logprior(q,.6,.08**2),h.wrapped_logprior(q,-2.,.1**2))
    p=h.posterior(two)
    if p['mode_count']!=2 or len(p['hpd_intervals'])!=2:raise RuntimeError('Multimodal HPD gate')
    results.extend([dict(test='circular_seam',grid=po['angle_grid_n'],TV=po['TV']),dict(test='multimodal_HPD',modes=p['mode_count'],regions=len(p['hpd_intervals']))])
    return results

def main():
    start=time.time();checks=[];smoke=[];jacrows=[]
    hashes={str(p):c.file_sha(p) for p in ROOT.glob('*.py')};hashes[str(ROOT/'CONTRACT.json')]=c.file_sha(ROOT/'CONTRACT.json')
    c.atomic_json(OUT/'INPUT_MANIFEST.json',dict(command=sys.argv,started_utc=datetime.now(timezone.utc).isoformat(),
        contract=C,source_sha256=hashes,repository_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()))
    try:
        im=json.loads((CACHE/'MANIFEST.json').read_text())
        for name,sha in im['sha256'].items():
            if c.file_sha(CACHE/name)!=sha:raise RuntimeError('Cache input drift '+name)
        p0=c.check_inputs();lut=c.original_lut(p0)
        c.atomic_json(OUT/'VERIFIED_INPUTS.json',dict(input_sha256=im['sha256'],frozen_blobs=c.check_frozen_baseline_files(),p0=p0))
        checks.append(dict(test='frozen_inputs',status='PASS'))
        checks.extend(synth())
        for case in p0['cases']:
            with np.load(CACHE/(case['id']+'_los.npz')) as cache:
                truth=cache['truth'];t=cache['t']
                for k in np.linspace(0,len(t)-1,12,dtype=int):
                    x=truth[k].copy()+np.array([.013,-.017,.0023])
                    terms,jac,error,boundary,clipping=h.chain(lut,x,case)
                    diff=h.baseline_parity(lut,x,np.diag([.01,.01,(5/h.RAD)**2]),float(cache['s'][k]),case)
                    jacrows.append(dict(case=case['id'],sample=int(k),jacobian_numeric_error=error,chain_error=float(np.max(abs(terms.sum(0)-jac[:2]))),boundary=boundary,clipping=clipping,inverse_parity=diff))
        checks.append(dict(test='geometry_chain_and_original_inverse',status='PASS',samples=len(jacrows),max_numeric_error=max(r['jacobian_numeric_error'] for r in jacrows),max_inverse_difference=max(r['inverse_parity'] for r in jacrows)))
        write('NUMERICAL_GATE_SAMPLES.csv',jacrows);write('SYNTHETIC_GATES.csv',checks)
        # Actual first paired smoke condition. No RF posterior feeds next prior.
        case=next(x for x in p0['cases'] if x['id']=='R2_aA_m0')
        t,truth,pids,motion,_=c.case_motion(p0,case,0,1,'noise_pair')
        f=c.DiagnosticFilter(c.initial_state(truth[0],0))
        with np.load(CACHE/(case['id']+'_los.npz')) as cache:
            for k in range(len(t)):
                if k:f.predict(float(motion['ds_odom'][k]),float(motion['dtheta_gyro'][k]),float(motion['dt_s'][k]))
                if t[k]<30:continue
                x=f.pose.copy();P=f.Ppose.copy();zs=float(cache['s'][k]);zr=float(cache['B_OLD'][k]);mu=np.zeros(2);R=np.diag([c.RS,c.RR])
                inv=h.legacy(lut,x,P,zs,case,truth[k]);po=h.posterior(h.fixed_logfun(lut,x,P,zs,case))
                score=h.scored(po,truth[k,2])
                row=dict(case=case['id'],sample=k,t_s=float(t[k]),method='G0_FIXED_POSITION_MAP',inverse_status=inv['status'],**score)
                smoke.append(row);write('SMOKE_PARTIAL.csv',smoke)
                print('fixed-position smoke',k,po['angle_grid_n'],flush=True)
                height=case['anchor'][2]-case['robot_z_m']
                if zr<=0 or zr<abs(height):raise RuntimeError('Smoke slant range unrealizable')
                theta=float(np.arctan2(np.sqrt(zr*zr-height*height),height)*h.RAD)
                g1=h.posterior(h.fixed_logfun(lut,x,P,zs,case,override_theta=theta))
                smoke.append(dict(case=case['id'],sample=k,t_s=float(t[k]),method='G1_THETA_ONLY',**h.scored(g1,truth[k,2])))
                # G2 correlated conditional and G3 jointly integrated positions.
                for full_cross in (False,True):
                    xp,pp,status=h.range_update(x,P,zr,case,0.,c.RR,full_cross)
                    if status!='applied':continue
                    post=h.integrated_posterior(lut,xp,pp,zs,zr,case,mu,R,True)
                    smoke.append(dict(case=case['id'],sample=k,t_s=float(t[k]),method='G2_CROSS' if full_cross else 'G2_HEADING_FIXED',**h.scored(post,truth[k,2])))
                post=h.integrated_posterior(lut,x,P,zs,zr,case,mu,R)
                smoke.append(dict(case=case['id'],sample=k,t_s=float(t[k]),method='G3_HEADING_MARGINAL',**h.scored(post,truth[k,2])))
                write('SMOKE_PARTIAL.csv',smoke)
                if len({r['sample'] for r in smoke})==3:break
        write('SMOKE.csv',smoke)
        receipt=dict(status='PASS',exit_code=0,synthetic_numeric_gate='PASS',smoke='PASS',scientific_PASS=False,
            full_experiment='NOT_RUN',elapsed_s=time.time()-start,checks=checks,smoke_rows=len(smoke))
        c.atomic_json(OUT/'VALIDATION_RECEIPT.json',receipt)
    except Exception as exc:
        if jacrows:write('NUMERICAL_GATE_SAMPLES.csv',jacrows)
        if checks:write('SYNTHETIC_GATES.csv',checks)
        if smoke:write('SMOKE_PARTIAL.csv',smoke)
        c.atomic_json(OUT/'VALIDATION_RECEIPT.json',dict(status='FAIL_CLOSED',exit_code=1,error_type=type(exc).__name__,
            failure_reason=str(exc),scientific_PASS=False,elapsed_s=time.time()-start,checks_completed=checks,
            full_experiment='NOT_RUN',recursive_fusion='NOT_RUN',partial_rows=len(smoke)))
        traceback.print_exc();raise

if __name__=='__main__':
    OUT=ROOT/(sys.argv[1] if len(sys.argv)>1 else 'GATES_01');OUT.mkdir(exist_ok=False);main()
