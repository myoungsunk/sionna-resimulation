#!/usr/bin/env python3
"""Independent tiny 2-pose Sionna RT ENGINE SMOKE, NOT MBVAR-INFO/PRE-P3 Track R.
Empty scene, ideal isotropic single-polarization antennas, LoS max_depth=0.
No real room, no FFD-pattern parity, no reflection, no new blind test.
Enforces at most 2 solver calls. Explicit execution capped by CI timeout.
"""
import datetime,hashlib,importlib.metadata,json,math,os,pathlib,sys
import numpy as np

def main(out):
    out=pathlib.Path(out);out.mkdir(exist_ok=True,parents=True)
    import drjit as dr
    import sionna.rt
    from sionna.rt import load_scene,PlanarArray,Transmitter,Receiver,PathSolver
    try:
        version=importlib.metadata.version("sionna-rt")
    except importlib.metadata.PackageNotFoundError:
        version="UNKNOWN"
    if version!="2.0.1":raise RuntimeError("ERR_VERSION_NOT_PINNED "+version)
    tx=np.array([2.,2.,2.65])
    positions=[np.array([3.,7.,.45]),np.array([5.,7.,.45])]
    receipts=[];num_calls=0
    for idx,rx in enumerate(positions):
        scene=load_scene()
        scene.frequency=6.5e9
        scene.tx_array=PlanarArray(num_rows=1,num_cols=1,vertical_spacing=.5,
                                   horizontal_spacing=.5,pattern="iso",polarization="V")
        scene.rx_array=PlanarArray(num_rows=1,num_cols=1,vertical_spacing=.5,
                                   horizontal_spacing=.5,pattern="iso",polarization="V")
        scene.add(Transmitter(name="tx",position=tx.tolist()))
        scene.add(Receiver(name="rx",position=rx.tolist()))
        solver=PathSolver()  # sionna-rt 2.0.1 has no deterministic constructor argument
        paths=solver(scene,max_depth=0,max_num_paths_per_src=16,samples_per_src=1,
          los=True,specular_reflection=False,diffuse_reflection=False,
          refraction=False,diffraction=False,edge_diffraction=False,
          synthetic_array=True,seed=20261030)
        num_calls+=1
        delays=np.asarray(dr.to_numpy(paths.tau),float).ravel()
        delays=delays[np.isfinite(delays)&(delays>0)]
        if not len(delays):raise RuntimeError("ERR_NO_LOS_PATH")
        analytical=float(np.linalg.norm(tx-rx)/299792458.)
        err=float(np.min(abs(delays-analytical)))
        if err>1e-10:raise RuntimeError("ERR_ANALYTIC_DIRECT_DELAY "+str(err))
        receipts.append(dict(index=idx,tx_xyz_m=tx.tolist(),rx_xyz_m=rx.tolist(),
          analytical_tau_s=analytical,solver_tau_s=float(delays[np.argmin(abs(delays-analytical))]),
          delay_abs_err_s=err,n_valid_solver_delays=int(len(delays)),
          source_multipath=False,scene_mesh_faces=0,reflections_enabled=False,
          has_original_FFD=False))
        print("RA5_RT_MICRO_POSE "+json.dumps(receipts[-1]),flush=True)
    if num_calls!=2:raise RuntimeError("ERR_SOLVER_BUDGET")
    (out/"RT_ENGINE_RECEIPT.json").write_text(json.dumps(dict(
       status="PASS_MINIMAL_RT_ENGINE_LOS_ONLY",
       solver="sionna-rt",solver_version=version,
       n_scene_configurations=2,solver_calls=num_calls,
       max_depth=0,antenna_pattern="ideal_iso_V_only",
       actual_new_physical_reflections=0,
       source_antenna_FFD_complex_parity="NOT_ATTEMPTED",
       authorized_MBVAR_P3=False,
       claim="ENGINE_SMOKE_ONLY_NO_PHYSICAL_RA5_SCENE",
       time_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
       independent_auditor=False),indent=2)+"\n")
    print("RA5_RT_MICRO_FINAL "+(out/"RT_ENGINE_RECEIPT.json").read_text(),flush=True)
if __name__=="__main__":
    main(sys.argv[1] if len(sys.argv)>1 else "rt_engine_smoke")
