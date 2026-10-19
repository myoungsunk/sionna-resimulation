"""R2 two-port effective co-response test; not an incident-field polarimeter.
Full/Native complex channels retain their existing coherent reference.
Only fixed LoS tap interventions are made, so detector shifts are separated.
"""
from pathlib import Path
import numpy as np,pandas as pd,json,sys
ROOT=Path(sys.argv[1]);SOURCE=Path(sys.argv[2]);OUT=ROOT/'review';OUT.mkdir(exist_ok=True)
manifest=json.loads((SOURCE/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())
rows=[];summary=[]
def s(v):
    p=abs(v)**2;return (p[:,0]-p[:,1])/np.maximum(p.sum(axis=1),np.finfo(float).tiny)
for c in manifest['cases']:
    if c['id'] not in ['R2_aA_m0','R2_aA_m45']:continue
    samples=pd.DataFrame(json.loads((SOURCE/c['samples_path']).read_text()))
    trace=np.load(ROOT/'traces'/f"{c['id']}_B0.npz",allow_pickle=False);eval_ids=trace['pose_id'][trace['t']>=30]
    F=np.load(SOURCE/c['full_path'],mmap_mode='r')[:,:,:,0];L=np.load(SOURCE/c['los_path'],mmap_mode='r')[:,:,:,0]
    nf=F.shape[1];w=np.hanning(nf);ii=np.arange(len(F))
    cl=np.fft.ifft(L*w[None,:,None],n=4*nf,axis=1)*nf;cf=np.fft.ifft(F*w[None,:,None],n=4*nf,axis=1)*nf
    amp=abs(cl);branch=amp.max(axis=1).argmax(axis=1);strong=amp[ii,:,branch];tap=(strong>=.3*strong.max(axis=1)[:,None]).argmax(axis=1)
    l=cl[ii,tap];m=cf[ii,tap]-l;PL=np.sum(abs(l)**2,axis=1);PM=np.sum(abs(m)**2,axis=1)
    a=np.sum(l.conj()*m,axis=1)/PL;parallel=a[:,None]*l;perp=m-parallel
    eta=np.divide(abs(np.sum(l.conj()*m,axis=1))**2,PL*PM,out=np.zeros(len(PL)),where=PM>0)
    scale=abs(1+a);p_perp=np.sum(abs(perp)**2,axis=1);fraction=p_perp/np.maximum(scale**2*PL+p_perp,1e-300)
    ds=s(l+m)-s(l);ds_par=s(l+parallel)-s(l);ds_perp=s(l+perp)-s(l);ds_align=s((1+abs(a))[:,None]*l+perp)-s(l)
    select=np.isin(samples.pose_id,eval_ids)
    data=pd.DataFrame(dict(case=c['id'],pose_id=samples.pose_id,x=samples.x,y=samples.y,yaw_deg=samples.yaw_body_deg,eta_effective_co=eta,residual_to_los_power=PM/PL,parallel_gain_amplitude=scale,perpendicular_fraction_after_sum=fraction,delta_s_fixed=ds,delta_s_parallel_only=ds_par,delta_s_perpendicular_only=ds_perp,delta_s_align_co=ds_align,evaluation=select))
    rows.append(data)
    for name,mask in [('all_eval',select),('high_co_eta_ge09',select&(eta>=.9)),('co_cancellation_gain_lt05',select&(scale<.5))]:
        if not mask.any():continue
        summary.append(dict(case=c['id'],scope=name,n=int(mask.sum()),eta_median=float(np.median(eta[mask])),co_fraction_ge09=float(np.mean(eta[mask]>=.9)),co_cancellation_lt05=float(np.mean(scale[mask]<.5)),delta_s_rmse=float(np.sqrt(np.mean(ds[mask]**2))),parallel_only_s_max=float(np.max(abs(ds_par[mask]))),perpendicular_only_rmse=float(np.sqrt(np.mean(ds_perp[mask]**2))),co_phase_aligned_rmse=float(np.sqrt(np.mean(ds_align[mask]**2)))))
pd.concat(rows).to_csv(OUT/'R2_CO_PORT_DIAGNOSTICS.csv.gz',index=False,compression='gzip');pd.DataFrame(summary).to_csv(OUT/'POLARIZATION_OVERLAP.csv',index=False)
print('CO_PORT_SUMMARY',json.dumps(summary),flush=True)
