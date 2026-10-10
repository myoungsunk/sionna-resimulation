"""Read-only RF artifact subset evaluation. Does not validate or retune LUT gates."""
import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from qclean_uwb.drivesim import experiment as E, filters as F, sensors as S, sensor_v2 as V
from qclean_uwb.drivesim.filter_v2 import run_filter_v2
from qclean_uwb.drivesim.evaluation_v2 import serialize,directional
from qclean_uwb.drivesim.hs_lut import HsLut
from qclean_uwb.drivesim.config import build_manifest


def evaluate(directory,out):
    if out.exists():raise FileExistsError(out)
    out.mkdir(parents=True);(out/'raw').mkdir()
    timeline=ROOT/'results/DRIVE_SIM_20261007/S1/timeline_y0_Tnone.csv'
    rows,ids=E.read_timeline(timeline);rows=rows[:201];ids=ids[:201]
    h=np.load(directory/'H_selected.npy',allow_pickle=False)
    provenance=json.loads((directory/'provenance.json').read_text())
    if ids.tolist()!=provenance['selected_pose_ids']:raise ValueError('H/timeline subset mismatch')
    if h.shape!=(201,257,2,2) or not np.isfinite(h).all():raise ValueError('unexpected selected H shape')
    # Stored h-store frequency grid is adopted from its production manifest below.
    Hmanifest=json.loads((directory/'H_y0_m0.manifest.json').read_text())
    if Hmanifest['outputs'][0]['sha256']!=provenance['source_sha256']:raise ValueError('H-store changed since manifest')
    freqs=np.load(directory/'freqs_hz.npy',allow_pickle=False)
    if len(freqs)!=h.shape[1]:raise ValueError('frequency grid mismatch')
    world=E.World(rows,h,freqs,0.,0.,None)
    meta=json.loads((directory/'hs_lut_meta.json').read_text())
    lut=HsLut(dict(theta_deg=np.array(meta['meta']['theta_deg']),phi_deg=np.arange(-180.,180.,meta['meta']['phi_deg'][2]),s=np.load(directory/'hs_lut_2deg.npy',allow_pickle=False)))
    ds,a=V.motion_increments(world.t,world.truth,convention="legacy-euler");outputs=[];records=[]
    for init in ('exact','legacy-prior'):
        for wb in ('matched','unknown'):
            for seed in range(200,208):
                scfg=V.SensorV2Config()
                inputs,ev=V.generate(world.t,ds,a,scfg,seed,dict(wheelbase=0 if wb=='matched' else .0075))
                # Separate v2 namespace; E.observe_world does NOT use sensor generator streams.
                obs=E.observe_world(world,35.,(V.NAMESPACE,seed,V.STREAMS['observation']),S.SensorNoise(),meta['range_bias']['mean_m'])
                cfg=F.FilterConfig(model_version='sensor-v2',use_range=False,use_s=False,bias_rw_std=0.,noise_var_cir_tap=6*obs['noise_var'],range_offset=meta['range_bias']['mean_m'])
                x0=np.r_[world.truth[0],0.,0.,0.];P0=np.diag(np.array(cfg.p0_std)**2)
                if init=='exact':P0[:3,:3]=0
                else:x0[:3]+=V.rng(seed,'initial').normal(size=3)*np.array(cfg.p0_std[:3])
                for method in ('online','online_range','online_range_s_RF'):
                    cfg=replace(cfg,use_range=method!='online',use_s=method=='online_range_s_RF')
                    outfilter=run_filter_v2(cfg,lut if cfg.use_s else None,inputs,obs,dict(turn_phase=world.turn_phase),x0,P0)
                    result=E.summarize_output(world,outfilter)
                    error=outfilter['est'][-1,:3]-world.truth[-1];error[2]=V.wrap(error[2])
                    nees=float(error@np.linalg.solve(outfilter['cov3'][-1],error))
                    records.append(dict(seed=seed,initial=init,wheelbase=wb,method=method,metrics=result['metrics'],endpoint_pose_nees=nees,endpoint_pose_cov95=nees<=E.CHI2_3_95))
                    archive=dict(time_s=world.t,evaluation_truth_pose=world.truth,estimate_state=outfilter['est'],estimate_covariance_full=outfilter['cov_full'],
                                 initial_state=x0,initial_prior=P0,seed=np.array(seed),evaluation_mask=world.t>=30,
                                 evaluation_integration_mismatch_pose=V.integrate(ds,a,world.truth[0])-world.truth,
                                 common_mask=(world.probe_id<0)&(world.drive_g>=E.COMMON_FROM_DRIVE_G))
                    archive.update(outfilter['observation_trace'])
                    archive.update({'sensor_'+k:np.asarray(v) for k,v in inputs.items()})
                    archive.update({'evaluation_'+k:np.asarray(v) for k,v in ev.items()})
                    archive.update({'observation_'+k:np.asarray(v) for k,v in obs.items() if isinstance(v,np.ndarray)})
                    archive.update(directional(world.truth,outfilter['est'],ds,a,cfg.anchor_xyz))
                    path=out/'raw'/f'{init}_{wb}_{seed}_{method}.npz'
                    with path.open('xb') as f:np.savez_compressed(f,**archive)
                    outputs.append(path)
    resultpath=out/'runs.json';resultpath.write_text(json.dumps(serialize(records),indent=2,allow_nan=False),encoding='utf8');outputs.append(resultpath)
    config=dict(model_version='sensor-v2',filter=asdict(cfg),sensor=scfg.manifest(),seeds=list(range(200,208)),n_samples=201,snr_db=35.,
                code_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),RF_input_provenance=provenance,
                claim='connection smoke/limited evaluation only; F01/F02 remain open; no calibration or LUT validation rerun',
                truth_motion_convention='legacy-euler',filter_motion_convention='SE2 exponential; discretization mismatch retained',
                frequency_grid_source='existing LP_plus45_bank.npz freqs_hz member; member hash recorded')
    source=[Path(__file__),ROOT/'src/qclean_uwb/drivesim/filter_v2.py',ROOT/'src/qclean_uwb/drivesim/sensor_v2.py',ROOT/'src/qclean_uwb/drivesim/observation.py',ROOT/'src/qclean_uwb/drivesim/hs_lut.py']
    manifest=build_manifest(config=config,inputs=source+[timeline,ROOT/'results/SENSOR_V2_20261008/PREREG_V2.md']+list(directory.iterdir()),outputs=outputs)
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
    print('completed',len(records),'runs')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path,required=True);args=p.parse_args();evaluate(args.input,args.out)
