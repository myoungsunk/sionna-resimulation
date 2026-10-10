"""Bounded, frozen-input CPU validation. No RF generation and no legacy writes.

Run stages 2..6 in order; execution plan must exist before the first run.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from scipy.stats import chi2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from qclean_uwb.drivesim import filters as F, observation as O, sensors as S
from qclean_uwb.drivesim.experiment import read_timeline
from qclean_uwb.drivesim.hs_lut import HsLut, s_model
from qclean_uwb.drivesim.uncertainty import ResidualTable, antenna_phase_deg

OUT = ROOT / "results/DRIVE_SIM_20261007/VALIDATION_REPAIR_20261008"
RAW = Path("D:/SLAM_bot/artifacts/DRIVE_SIM_INDEPENDENT_AUDIT_20261008_01a11947/selected_raw")
REV = "991da089e0723644b244fb663b37c519b6e941e2"
ANCHOR = (4., 0., 2.65)
RZ = .45


def sha(p):
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda: f.read(2**20), b""):
            h.update(b)
    return h.hexdigest()


def write(name, data):
    (OUT / name).write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def clean(v):
    if isinstance(v, dict): return {k: clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, np.ndarray)): return [clean(x) for x in v]
    if isinstance(v, np.generic): return clean(v.item())
    if isinstance(v, float) and not np.isfinite(v): return None
    return v


def stats(r, ids=None):
    r = np.asarray(r, float)
    if not len(r) or not np.isfinite(r).all(): raise ValueError("INVALID_RESIDUALS")
    mean = float(r.mean())
    centered = r - mean
    adjacent = np.ones(len(r)-1, bool) if ids is None else np.diff(ids) == 1
    a, b = centered[:-1][adjacent], centered[1:][adjacent]
    rho = float(np.corrcoef(a, b)[0, 1]) if len(a)>2 and a.std()>0 and b.std()>0 else None
    return dict(n=len(r), mean=mean, variance_centered=float(centered @ centered / len(r)), rms=float(np.sqrt(r @ r / len(r))), rho1=rho,
                contiguous_blocks=1 + int(np.sum(np.diff(ids)!=1)) if ids is not None else 1)


def load():
    meta = json.loads((RAW / "hs_lut_meta.json").read_text())
    lut = HsLut(dict(theta_deg=meta["meta"]["theta_deg"], phi_deg=np.arange(-180., 180., meta["meta"]["phi_deg"][2]), s=np.load(RAW/"hs_lut_2deg.npy")))
    timeline = ROOT/"results/DRIVE_SIM_20261007/S1/routes/timeline_R2_Tnone.csv"
    posesfile = ROOT/"results/DRIVE_SIM_20261007/S1/routes/rf_poses_R2.json"
    rows, ids = read_timeline(timeline)
    store = np.load(RAW/"H_R2_aA_m0.npy", mmap_mode="r")
    freq = np.load(RAW/"freqs_hz.npy")
    poses = json.loads(posesfile.read_text())
    if store.shape != (len(poses), len(freq), 2, 2): raise ValueError("H_POSE_SHAPE_MISMATCH")
    if np.any(ids<0) or np.any(ids>=len(store)): raise ValueError("TIMELINE_POSE_ID_OUT_OF_RANGE")
    maxdiff = max(max(abs(row[k]-poses[i][k]) for k in ("x", "y", "yaw_body_deg")) for row,i in zip(rows,ids))
    if maxdiff>1e-6: raise ValueError("TIMELINE_POSE_GEOMETRY_MISMATCH")
    H = store[ids]
    if not np.isfinite(H).all() or not np.isfinite(lut.s).all() or not np.allclose(np.diff(freq),np.diff(freq)[0],atol=1e-6):
        raise ValueError("NONFINITE_OR_NONUNIFORM_INPUT")
    truth = np.column_stack([[r["x"] for r in rows],[r["y"] for r in rows],np.radians([r["yaw_body_deg"] for r in rows])])
    obs = O.observe(H, freq, None, None)
    sm = s_model(lut,ANCHOR,RZ,truth[:,0],truth[:,1],truth[:,2])
    distance = np.linalg.norm(np.column_stack([truth[:,:2],np.full(len(rows),RZ)])-ANCHOR,axis=1)
    return dict(rows=rows,ids=ids,truth=truth,lut=lut,meta=meta,h=H,freq=freq,obs=obs,sm=sm,d=distance,
                phase=antenna_phase_deg(truth[:,2]),t=np.array([r["t_s"] for r in rows]),max_geometry_diff=maxdiff)


def cfg0(sigma=.16095229605409875, odom=True):
    return F.FilterConfig(anchor_xyz=ANCHOR,robot_z=RZ,s_mismatch_sigma=sigma,range_offset=-.5315983906250129,
                          pos_process_std=.01,use_odom_heading=odom)


def Q(cfg,x,ds):
    G=np.zeros((6,2)); G[:2,0]=[math.cos(x[2]),math.sin(x[2])]; G[2,1]=1/(1+x[4])
    q=G@np.diag([cfg.k_s*abs(ds),cfg.arw_var])@G.T
    q[3,3]+=cfg.bias_rw_std**2*cfg.dt; q[4,4]+=1e-12; q[5,5]+=1e-12
    q[0,0]+=cfg.pos_process_std**2; q[1,1]+=cfg.pos_process_std**2
    return q


def transition(x,ds,dg,cfg):
    x=x.copy(); old=x[2]
    x[:2]+=ds*np.array([math.cos(old),math.sin(old)])
    x[2]=F.wrap(old+(dg-x[3]*cfg.dt)/(1+x[4])); return x


def metric(est,cov,truth,keep,nis_r,nis_s,st):
    e=est[keep,:3]-truth[keep]; e[:,2]=F.wrap(e[:,2]); p=cov[keep]
    nees=np.array([x@np.linalg.solve(c,x) for x,c in zip(e,p)])
    lo,hi=chi2.ppf([.025,.975],3)
    return dict(n_eval=int(keep.sum()),pos_rmse_m=float(np.sqrt((e[:,:2]**2).sum(1).mean())),heading_rmse_deg=float(np.degrees(np.sqrt((e[:,2]**2).mean()))),
                pos_max_m=float(np.linalg.norm(e[:,:2],axis=1).max()),heading_max_deg=float(np.abs(np.degrees(e[:,2])).max()),nees_mean=float(nees.mean()),
                nees_lower_tail=float((nees<lo).mean()),nees_upper_tail=float((nees>hi).mean()),pose_cov95=float((nees<=chi2.ppf(.95,3)).mean()),
                heading_cov95=float((np.abs(e[:,2])<=1.95996398454*np.sqrt(p[:,2,2])).mean()),cov_trace_mean=float(np.trace(p,axis1=1,axis2=2).mean()),
                min_cov_eig=float(np.linalg.eigvalsh(p).min()),nis_r_mean=float(np.mean(nis_r)) if nis_r else None,nis_s_mean=float(np.mean(nis_s)) if nis_s else None,
                r_rejected=st["r_rejected"],s_rejected=st["s_rejected"],r_updates=st["r_updates"],s_updates=st["s_updates"])


def replay(data,cfg,inputs,obs,x0,keep):
    f=F.DriveFilter(cfg,data["lut"],x0); est=[]; cov=[]; nr=[]; ns=[]; ni=[]
    for k in range(len(data["truth"])):
        if k:
            f.predict(inputs["ds_odom"][k],inputs["dtheta_gyro"][k])
            if cfg.use_odom_heading: f.update_odom_heading(inputs["dtheta_odom"][k],inputs["dtheta_gyro"][k],inputs["ds_odom"][k])
            if obs["detected"][k]:
                x,p=f.mean_cov(); d=float(np.linalg.norm(np.r_[x[:2],RZ]-ANCHOR))
                hr=np.zeros(6); hr[:2]=(x[:2]-ANCHOR[:2])/d
                yr=obs["range_m"][k]-d-cfg.range_offset
                rr=cfg.range_sigma**2+cfg.range_quant_var+cfg.range_extra_sigma**2
                if keep[k]: nr.append(float(yr**2/(hr@p@hr+rr)))
                f.update_range(obs["range_m"][k])
                x,p=f.mean_cov(); h,j=s_model(data["lut"],ANCHOR,RZ,*x[:3],with_jac=True)
                hs=np.r_[j,np.zeros(3)]; rs=f._s_R(*obs["power"][k],xy=x[:2],psi=x[2]); ys=obs["s"][k]-h
                if keep[k]:
                    ns.append(float(ys**2/(hs@p@hs+rs))); ni.append(float(ys))
                f.update_s(obs["s"][k],*obs["power"][k])
        x,p=f.mean_cov(); est.append(x);cov.append(p[:3,:3])
    met=metric(np.array(est),np.array(cov),data["truth"],keep,nr,ns,f.stats)
    met["innovation_s"]=stats(ni,np.flatnonzero(keep)[1:] if len(ni)==keep.sum()-1 else None) if ni else None
    return met


def stage2(data):
    rng=np.random.default_rng(20261008); jacerrs=[]
    for _ in range(40):
        x=np.array([rng.uniform(1,18),rng.uniform(-.5,.5),rng.uniform(-3,3),.001,.003,.002]);cfg=cfg0(odom=False)
        h,j=s_model(data["lut"],ANCHOR,RZ,*x[:3],with_jac=True)
        fd=[]
        for i in range(3):
            dx=np.zeros(6);dx[i]=1e-6
            fd.append((s_model(data["lut"],ANCHOR,RZ,*(x+dx)[:3])-s_model(data["lut"],ANCHOR,RZ,*(x-dx)[:3]))/2e-6)
        jacerrs.append(float(np.max(np.abs(j-fd))))
    cfg=cfg0(.04,False);cfg.range_offset=0.;cfg.range_quant_var=0.;cfg.range_extra_sigma=0.;cfg.range_sigma=.03;cfg.pos_process_std=.001
    cfg.p0_std=(.015,.015,math.radians(.3),math.radians(.002),.0002,.0002)
    # Gates disabled only in matched control: tests the Gaussian filter equations,
    # not the truncation induced by the production innovation rejection.
    cfg.gate=float("inf")
    metrics=[];max_predict_diff=0.;min_psd=1.
    for seed in range(3000,3200):
        rng=np.random.default_rng(seed); x0=np.array([8.,.1,.23,0.,0.,0.]);true=x0+rng.normal(size=6)*cfg.p0_std
        f=F.DriveFilter(cfg,data["lut"],x0);es=[];ps=[];ts=[]
        for k in range(120):
            ds=.02;dg=.002*math.sin(k/20)
            prev=true.copy(); true=transition(true,ds,dg,cfg)+rng.multivariate_normal(np.zeros(6),Q(cfg,prev,ds));true[2]=F.wrap(true[2])
            px,pp=f.mean_cov();f.predict(ds,dg)
            if seed==3000 and k==0:
                ff=np.column_stack([(transition(px+np.eye(6)[i]*1e-6,ds,dg,cfg)-transition(px-np.eye(6)[i]*1e-6,ds,dg,cfg))/2e-6 for i in range(6)])
                _,actual=f.mean_cov();max_predict_diff=float(np.max(np.abs(actual-(ff@pp@ff.T+Q(cfg,px,ds)))))
            d=np.linalg.norm(np.r_[true[:2],RZ]-ANCHOR)
            f.update_range(d+cfg.range_sigma*rng.normal())
            h=s_model(data["lut"],ANCHOR,RZ,*true[:3]);f.update_s(h+cfg.s_mismatch_sigma*rng.normal(),1.,1.)
            e,p=f.mean_cov(); es.append(e);ps.append(p[:3,:3]);ts.append(true[:3]);min_psd=min(min_psd,np.linalg.eigvalsh(p).min())
        metrics.append(dict(seed=seed,**metric(np.array(es),np.array(ps),np.array(ts),np.ones(120,bool),[],[],f.stats)))
    # Exact linear-Gaussian scalar update using the production Joseph update.
    oracle=[]
    for seed in range(6000,6200):
        rng=np.random.default_rng(seed);truth=rng.normal();f=F.DriveFilter(cfg,None,np.zeros(6),np.eye(6));H=np.eye(6)[0]
        for k in range(60):
            z=truth+.2*rng.normal();c=f.comps[0];y=z-c.x[0];var=float(H@c.P@H+.04);f._apply(c,H,y,var,.04)
        oracle.append((f.comps[0].x[0]-truth)**2/f.comps[0].P[0,0])
    # Shared gyro: after predict e_theta=-n_g/(1+SF), z_odom noise=-n_g.
    noise=np.random.default_rng(77).normal(0,math.sqrt(cfg.arw_var),size=100000)
    shared=float(np.mean((-noise)*(-noise)))
    out=dict(model="nonlinear matched local control; independent process/UWB; odom pseudo-measurement disabled",seed_results=metrics,
             s_jacobian_max_abs_error=max(jacerrs),predict_covariance_fd_max_abs_error=max_predict_diff,min_full_cov_eig=min_psd,
             exact_scalar_mean_nees=float(np.mean(oracle)),exact_scalar_expected=1.,
             shared_gyro=dict(predicted_error_measurement_noise_cov=shared,analytic_cov=cfg.arw_var,legacy_update_cross_cov=0.,
                              interpretation="nonzero shared gyro covariance omitted by legacy odom update; matched control does not validate that update"),
             angle_wrap_checked=bool(abs(F.wrap(math.pi+.01)-(-math.pi+.01))<1e-12))
    assert max(jacerrs)<1e-4 and max_predict_diff<1e-8 and min_psd>-1e-12 and out["angle_wrap_checked"]
    write("STEP2_MATCHED_CONTROL.json",clean(out))


def stage3(data):
    keep=data["t"]>=30.;r=data["obs"]["s"]-data["sm"];rr=data["obs"]["range_m"]-data["d"]-data["meta"]["range_bias"]["mean_m"]
    index=data["obs"]["index"];change=np.r_[False,np.diff(index)!=0];file=OUT/"STEP3_RESIDUALS.csv"
    import csv
    with file.open("w",newline="",encoding="utf-8") as f:
        w=csv.writer(f);w.writerow(["sample","pose_id","t_s","distance_m","antenna_phase_deg","s_residual","range_residual_m","fp_index","fp_changed"])
        w.writerows(zip(range(len(r)),data["ids"],data["t"],data["d"],data["phase"],r,rr,index,change))
    l2path=ROOT/"results/DRIVE_SIM_20261007/SNOWBALL_ROUTE_RUNS/01a11669/final_20261007T140446Z/results/S4/LUT_LOS_CHECK.json"
    l2=json.loads(l2path.read_text())
    out=dict(L1=dict(status="LEGACY_FAIL_NOT_INDEPENDENTLY_VERIFIED",stored=data["meta"]["gate_L1_interpolation"]),
             L2=dict(status="LEGACY_FAIL_NOT_INDEPENDENTLY_VERIFIED",stored=l2,source=str(l2path),sha256=sha(l2path)),
             missing=["FFD bank NPZ actual bytes (local files are Git LFS pointers)","same-pose Sionna LoS-only H", "raw Jones traces for path separation"],
             full_rf_s=stats(r[keep],np.flatnonzero(keep)),range_residual=stats(rr[keep],np.flatnonzero(keep)),
             cross_corr_range_s=float(np.corrcoef(rr[keep],r[keep])[0,1]),fp_changed=stats(r[keep&change],np.flatnonzero(keep&change)),
             fp_unchanged=stats(r[keep&~change],np.flatnonzero(keep&~change)),fp_change_count=int((change&keep).sum()),
             interpretation="tap-change association only; no causal LoS/multipath decomposition without same-pose LoS H/FFD")
    write("STEP3_OBSERVATION_LAYERS.json",clean(out))


def physical(seed,data):
    ds,dg=S.true_increments(data["rows"]);rng=np.random.default_rng([seed,101]);drift=S.draw_drift(S.DRIFT_LEVELS[0],rng)
    inputs=S.generate_inputs(ds,dg,drift,S.SensorNoise(),.2,rng)
    x0=np.r_[data["truth"][0],0.,0.,0.]+np.random.default_rng([seed,102]).normal(size=6)*np.array(cfg0().p0_std)
    return inputs,x0


def makeobs(data,seed,actual_range=True,actual_s=True,cfg=None):
    cfg=cfg or cfg0();rng=np.random.default_rng([seed,103]);obs=copy.deepcopy(data["obs"])
    rv=cfg.range_sigma**2+cfg.range_quant_var+cfg.range_extra_sigma**2
    rnoise=rng.normal(size=len(data["t"]));snoise=rng.normal(size=len(data["t"]))
    obs["range_m"]=(data["obs"]["range_m"]+cfg.range_sigma*rnoise) if actual_range else (data["d"]+cfg.range_offset+math.sqrt(rv)*rnoise)
    obs["s"]=data["obs"]["s"].copy() if actual_s else data["sm"]+cfg.s_mismatch_sigma*snoise
    return obs


def stage4(data):
    result=[];keep=data["t"]>=30.
    for seed in range(4000,4024):
        inputs,x0=physical(seed,data)
        for ar,ass in ((False,False),(True,False),(False,True),(True,True)):
            cfg=cfg0();obs=makeobs(data,seed,ar,ass,cfg)
            result.append(dict(seed=seed,actual_range=ar,actual_s=ass,**replay(data,cfg,inputs,obs,x0,keep)))
    write("STEP4_FACTORIAL.json",clean(dict(runs=result,noise="clean RF first-path plus .05m Gaussian range; no thermal H noise; synthetic s sigma=.16095229605409875; synthetic range exact filter R")))


def tables(data):
    n=len(data["t"]);cal=(np.arange(n)<int(.4*n))&(data["t"]>=30.)
    ev=(np.arange(n)>=int(.6*n))&(data["t"]>=30.)&~np.isin(data["ids"],data["ids"][cal])
    if cal.sum()<100 or ev.sum()<100: raise ValueError("INSUFFICIENT_SPLIT")
    d=data["d"];p=data["phase"];r=data["obs"]["s"]-data["sm"]
    de=(5.,10.);pe=(15.,30.);di=np.searchsorted(de,d);pi=np.searchsorted(pe,p)
    scalar=stats(r[cal],np.flatnonzero(cal))["rms"];one=np.full(3,np.nan);joint=np.full((3,3),np.nan);cells=[]
    # 20-sample blocks are a count requirement, NOT asserted independent.
    for i in range(3):
        c=cal&(di==i);ids=np.flatnonzero(c)
        if len(ids)>=50 and len(set(ids//20))>=3:one[i]=stats(r[c],ids)["rms"]
        for j in range(3):
            c=cal&(di==i)&(pi==j);ids=np.flatnonzero(c)
            if len(ids)>=50 and len(set(ids//20))>=3:joint[i,j]=stats(r[c],ids)["rms"]
            e=ev&(di==i)&(pi==j)
            cells.append(dict(distance_bin=i,phase_bin=j,calibration=stats(r[c],ids) if c.any() else None,evaluation=stats(r[e],np.flatnonzero(e)) if e.any() else None,
                              eligible=bool(np.isfinite(joint[i,j])),n_20_sample_blocks=len(set(ids//20))))
    models={m:ResidualTable(de,pe,scalar,one,joint,(float(d[cal].min()),float(d[cal].max())),m) for m in ("constant","distance","joint")}
    return cal,ev,models,cells


def stage5(data):
    cal,ev,models,cells=tables(data);r=data["obs"]["s"]-data["sm"]
    train_ids=np.flatnonzero(cal);eval_ids=np.flatnonzero(ev)
    support={};offline={}
    for name,table in models.items():
        sigma=np.array([table.sigma(x[:2],x[2],ANCHOR,RZ,0.) for x in data["truth"][ev]])
        offline[name]=dict(oracle_features=True,mean_normalized_sq=float(np.mean((r[ev]/sigma)**2)),gaussian95_coverage=float((np.abs(r[ev])<=1.96*sigma).mean()),
                           gaussian_nll_mean=float(np.mean(np.log(sigma)+.5*(r[ev]/sigma)**2)))
        support[name]=dict(scalar_rms=table.scalar_rms,distance_rms=table.distance_rms,joint_rms=table.joint_rms,distance_support=table.distance_support)
    # Bias correction diagnostics only: trained cell means, no online truth use.
    mean=np.full((3,3),float(r[cal].mean()));variance=np.full((3,3),float(np.var(r[cal])))
    di=np.searchsorted([5.,10.],data["d"]);pi=np.searchsorted([15.,30.],data["phase"])
    for cell in cells:
        if cell["eligible"]:
            i,j=cell["distance_bin"],cell["phase_bin"];mean[i,j]=cell["calibration"]["mean"];variance[i,j]=cell["calibration"]["variance_centered"]
    corrected=r[ev]-mean[di[ev],pi[ev]]
    write("STEP5_CALIBRATION.json",clean(dict(calibration_indices=train_ids,evaluation_indices=eval_ids,pose_id_intersection=sorted(set(data["ids"][cal])&set(data["ids"][ev])),
        calibration=stats(r[cal],train_ids),evaluation=stats(r[ev],eval_ids),cells=cells,tables=support,oracle_offline=offline,
        oracle_mean_corrected=stats(corrected,eval_ids),mean_table=mean,centered_variance_table=variance,
        definition="3D link distance and antenna yaw phase relative world axes; not measured polarization matching",independence="embargoed disjoint pose IDs within one fixed R2-A-m0 RF world; new route/anchor/mount NOT verified")))


def boot(values, median=False):
    a=np.asarray(values,float);rng=np.random.default_rng(20261008)
    samples=rng.choice(a,size=(2000,len(a)),replace=True)
    means=np.median(samples,axis=1) if median else samples.mean(1)
    return [float(v) for v in np.quantile(means,[.025,.975])]


def aggregate(runs):
    out={}
    for key in ("pos_rmse_m","heading_rmse_deg","nees_mean","pose_cov95","nees_lower_tail","nees_upper_tail","cov_trace_mean","nis_s_mean","nis_r_mean"):
        v=[r[key] for r in runs];out[key]=dict(mean=float(np.mean(v)),median=float(np.median(v)),min=float(min(v)),max=float(max(v)),seed_mean_bootstrap_ci95=boot(v))
    out["worst_position_m"]=max(r["pos_max_m"] for r in runs);out["worst_heading_deg"]=max(r["heading_max_deg"] for r in runs)
    out["rejected_range"]=sum(r["r_rejected"] for r in runs);out["rejected_s"]=sum(r["s_rejected"] for r in runs)
    return out


def stage6(data):
    cal,ev,models,cells=tables(data);runs=[]
    for seed in range(5000,5024):
        inputs,x0=physical(seed,data);obs=makeobs(data,seed)
        for name,model in models.items():
            cfg=cfg0(model.scalar_rms);cfg.s_residual_table=model
            runs.append(dict(seed=seed,model=name,**replay(data,cfg,inputs,obs,x0,ev)))
    summaries={name:aggregate([r for r in runs if r["model"]==name]) for name in models};paired={}
    baseline={r["seed"]:r for r in runs if r["model"]=="constant"}
    for name in ("distance","joint"):
        sr=[r for r in runs if r["model"]==name];paired[name]={}
        for key in ("pos_rmse_m","heading_rmse_deg","nees_mean","pose_cov95"):
            delta=[r[key]-baseline[r["seed"]][key] for r in sr]
            paired[name][key]=dict(mean_delta=float(np.mean(delta)),median_delta=float(np.median(delta)),mean_delta_seed_bootstrap_ci95=boot(delta),median_delta_seed_bootstrap_ci95=boot(delta,median=True))
        ss=summaries[name]
        paired[name]["exploratory_joint_criterion_met"]=bool(paired[name]["pos_rmse_m"]["median_delta_seed_bootstrap_ci95"][1]<=0 and paired[name]["heading_rmse_deg"]["median_delta_seed_bootstrap_ci95"][1]<=0
            and ss["nees_mean"]["seed_mean_bootstrap_ci95"][0]<=3<=ss["nees_mean"]["seed_mean_bootstrap_ci95"][1]
            and .90<=ss["pose_cov95"]["median"]<=.99 and ss["nees_lower_tail"]["median"]<=.05 and ss["nees_upper_tail"]["median"]<=.05)
    factorial=json.loads((OUT/"STEP4_FACTORIAL.json").read_text())["runs"]
    factor={f"range_{int(ar)}_s_{int(ass)}":aggregate([r for r in factorial if r["actual_range"]==ar and r["actual_s"]==ass]) for ar,ass in ((False,False),(True,False),(False,True),(True,True))}
    interactions={}
    for key in ("heading_rmse_deg","pos_rmse_m","nees_mean"):
        ds=[]
        for seed in range(4000,4024):
            a={(r["actual_range"],r["actual_s"]):r[key] for r in factorial if r["seed"]==seed}
            ds.append(a[True,True]-a[True,False]-a[False,True]+a[False,False])
        interactions[key]=dict(mean=float(np.mean(ds)),seed_bootstrap_ci95=boot(ds))
    matched=json.loads((OUT/"STEP2_MATCHED_CONTROL.json").read_text())["seed_results"]
    # Matched controls don't collect innovation NIS: summarize useful metrics.
    matchsum={key:dict(mean=float(np.mean([r[key] for r in matched])),ci=boot([r[key] for r in matched])) for key in ("nees_mean","pose_cov95","nees_lower_tail","nees_upper_tail")}
    write("STEP6_JOINT_EVALUATION.json",clean(dict(runs=runs,summary=summaries,paired=paired,factorial_summary=factor,factorial_interaction=interactions,matched_summary=matchsum,
        evaluation="seed summaries; bootstrap conditional on one deterministic RF realization; no independent-time chi2 average gate",scientific_PASS=False)))


def provenance():
    files=subprocess.check_output(["git","ls-files","results/DRIVE_SIM_20261007"],cwd=ROOT,text=True).splitlines()
    hashes={p:sha(ROOT/p) for p in files if (ROOT/p).is_file()}
    write("PROTECTED_INPUT_HASHES.json",hashes)
    inputs=[RAW/n for n in ("H_R2_aA_m0.npy","freqs_hz.npy","hs_lut_2deg.npy","hs_lut_meta.json")]
    inputs += [ROOT/"results/DRIVE_SIM_20261007/S1/routes/timeline_R2_Tnone.csv",ROOT/"results/DRIVE_SIM_20261007/S1/routes/rf_poses_R2.json",OUT/"EXECUTION_PLAN.json"]
    write("INPUT_MANIFEST.json",dict(revision=REV,branch=subprocess.check_output(["git","branch","--show-current"],cwd=ROOT,text=True).strip(),
          timestamp_utc=datetime.now(timezone.utc).isoformat(),python=sys.executable,numpy=np.__version__,inputs={str(p):dict(sha256=sha(p),bytes=p.stat().st_size) for p in inputs},
          shape_H=list(np.load(inputs[0],mmap_mode="r").shape),shape_freq=list(np.load(inputs[1]).shape),shape_lut=list(np.load(inputs[2]).shape)))


def main():
    a=argparse.ArgumentParser();a.add_argument("stage",choices=["prepare","2","3","4","5","6","preserve"]);args=a.parse_args()
    if subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()!=REV:raise ValueError("BASE_REVISION_MOVED")
    if not (OUT/"EXECUTION_PLAN.json").exists():raise ValueError("EXECUTION_PLAN_MISSING")
    if args.stage=="prepare":provenance();return
    if args.stage=="preserve":
        before=json.loads((OUT/"PROTECTED_INPUT_HASHES.json").read_text());changed=[p for p,h in before.items() if sha(ROOT/p)!=h]
        write("PRESERVATION_CHECK.json",dict(checked=len(before),changed=changed,passed=not changed));assert not changed;return
    required={"3":"STEP2_MATCHED_CONTROL.json","4":"STEP3_OBSERVATION_LAYERS.json","5":"STEP4_FACTORIAL.json","6":"STEP5_CALIBRATION.json"}
    if args.stage in required and not (OUT/required[args.stage]).exists():raise ValueError("PREVIOUS_STAGE_MISSING")
    t=datetime.now(timezone.utc).isoformat();data=load()
    globals()["stage"+args.stage](data)
    write(f"STAGE{args.stage}_RECEIPT.json",dict(start_utc=t,end_utc=datetime.now(timezone.utc).isoformat(),command=sys.argv,exit_code=0,revision=REV,
         timeline_max_geometry_difference=data["max_geometry_diff"],code_sha256={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),ROOT/"src/qclean_uwb/drivesim/filters.py",ROOT/"src/qclean_uwb/drivesim/uncertainty.py"]}))
    print("stage",args.stage,"COMPLETE")


if __name__=="__main__":main()
