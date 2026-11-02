"""MB_VAR residual LUT/SourceFFD gap: saved traces and common-state evaluations only."""
from pathlib import Path
import sys,json,datetime,hashlib,os,traceback
import numpy as np,pandas as pd
OUT=Path(__file__).resolve().parent;FIX=OUT.parent;OLD=FIX.parent/'lut_observer_swap_20261102'
sys.path.insert(0,str(OLD));sys.path.insert(0,str(FIX))
import replay_observer_swap as A
from pole_regularized_lut import PoleRegularizedLut
DG=A.DG
LEDGER=A.BASE/'검토 기록/LUT_SourceFFD_관측모델_대조_20261102/SAME_STATE_COMPARISON_3136.csv'
def dump(n,x):(OUT/n).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def rms(x):return float(np.sqrt(np.mean(np.asarray(x)**2)))
def nees(e,p):return np.einsum('ni,ni->n',e,np.linalg.solve(p,e[...,None])[...,0])
def acf(x):
    return float(np.corrcoef(x[:-1],x[1:])[0,1]) if np.std(x)>1e-14 else 0.
def main():
    assert not (OUT/'CONTRACT.json').exists()
    prior=json.loads((FIX/'CONTRACT.json').read_text());paths=list(prior['input_hashes'])+[str(FIX/'pole_regularized_lut.py'),str(FIX/'RESULT_CHECKS.json'),str(LEDGER),str(__file__)]
    for c in A.CASES:
      for b in A.BIASES:paths += [str(FIX/f'{c}_{b}_PROPOSED_MB_VAR_LUT_fixed.npz'),str(A.refpath(c,b,'PROPOSED_MB_VAR'))]
    locked={p:A.sha(p) for p in sorted(set(paths))}
    dump('CONTRACT.json',dict(question_id='DLP-MBVAR-POSTPOLE-RESIDUAL-GAP-20261102',role='AUDITOR self-check, not independent',source_identity=prior['source_identity'],declared_source_commit=prior['declared_source_commit'],scope='All 12 MB_VAR conditions; saved trace rescore, same-state h/H evaluation, truth-only offline RF/model residual decomposition, algebraic e/P substitutions; NO filter rerun, tuning, manuscript mutation',competitors=['10m versus actual-distance first-path chain','scalar interpolation and remaining cap approximation','unchanged donor mismatch','Jacobian and covariance difference','gate/R state dependence','multipath residual common to both models'],score='t>=30s all points; same 1D/2D/3D NEES as parent; no new statistical/generalization claim',input_hashes=locked,started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),managed_run_id=os.environ.get('MANAGED_PROCESS_RUN_ID')))
    model=DG.C.base_model();lut=PoleRegularizedLut(A.FrozenLut(A.OLD));ledger=pd.read_csv(LEDGER)
    allsummary=[];cross=[];truthrows=[];pkts=[];windows=[];donors=[];validation=[]
    for c in A.CASES:
      phys=ledger[ledger.case==c].reset_index(drop=True)
      for b in A.BIASES:
        A.stop_check();l=dict(np.load(FIX/f'{c}_{b}_PROPOSED_MB_VAR_LUT_fixed.npz'));s=dict(np.load(A.refpath(c,b,'PROPOSED_MB_VAR')))
        t=l['t'];gt=l['gt'];m=t>=30-1e-9;sp=DG.C.CASES[c];n=len(t)
        assert np.array_equal(t,phys.t_s.to_numpy())
        if b=='B0':
            hg,jg=lut.batch(gt[:,:4],sp)
            hs0=np.column_stack([phys.distance_m.to_numpy()-.5315983906250129,phys.s_source])
            delta=hs0[:,1]-hg[:,1];interp=phys.s_direct_10m.to_numpy()-hg[:,1];distance=phys.delta_distance.to_numpy();source=phys.delta_source.to_numpy()
            assert np.max(abs(delta-interp-distance-source))<1e-12
            tr=phys[['case','k','t_s','distance_m','theta_deg']].copy()
            tr['s_fixed']=hg[:,1];tr['s_source']=hs0[:,1];tr['fixed_model_delta']=delta;tr['interpolation_and_cap_delta']=interp;tr['distance_processing_delta']=distance
            truthrows.append(tr)
        hs,js=model.batch(s['xp'],sp);hl,jl=lut.batch(l['xp'],sp);hls,jls=lut.batch(s['xp'],sp)
        assert np.allclose(hs,s['hx'],atol=1e-12) and np.allclose(hl,l['hx'],atol=1e-12)
        assert np.allclose(js,s['J'],atol=1e-10) and np.allclose(jl,l['J'],atol=1e-10)
        # z and frozen donor mu are common by the parent replay contract.
        assert np.allclose(s['nu'],l['z']-hs-l['mu'],atol=1e-12)
        nu_delta=l['nu']-s['nu'];function_delta=hs-hls;trajectory_delta=hls-hl
        assert np.max(abs(nu_delta-function_delta-trajectory_delta))<1e-12
        erfs=l['z']-hs0-l['mu'];erfl=l['z']-hg-l['mu']
        assert np.max(abs(erfl[:,1]-erfs[:,1]-delta))<1e-12
        cases={};prev_rho={}
        for ob,z,j,rf,htruth in [('SourceFFD',s,js,erfs,hs0),('LUT_fixed',l,jl,erfl,hg)]:
            e=gt[:,:3]-z['X'][:,:3];e[:,2]=np.angle(np.exp(1j*e[:,2]));p=z['PX'][:,:3,:3]
            nn=nees(e,p);xy=nees(e[:,:2],p[:,:2,:2]);head=e[:,2]**2/p[:,2,2]
            beta=np.linalg.solve(p[:,:2,:2],p[:,:2,2,None])[...,0];vc=p[:,2,2]-np.einsum('ni,ni->n',p[:,2,:2],beta);ec=e[:,2]-np.einsum('ni,ni->n',beta,e[:,:2])
            assert np.allclose(nn,xy+ec**2/vc,rtol=1e-8,atol=1e-8)
            innovation=rf+htruth-z['hx'];assert np.allclose(innovation,z['nu'],atol=1e-12)
            cases[ob]=(e,p,nn)
            summary=dict(case=c,route=c[:2],bias=b,observer=ob,n_score=int(m.sum()),heading_rmse_deg=rms(np.degrees(e[m,2])),xy_rmse_cm=float(np.sqrt(np.mean(np.sum(e[m,:2]**2,axis=1)))*100),
                mean_heading_error_deg=float(np.degrees(e[m,2].mean())),heading_constant_mean_MSE_fraction=float(e[m,2].mean()**2/np.mean(e[m,2]**2)),rms_sigma_heading_deg=float(np.degrees(np.sqrt(p[m,2,2].mean()))),rms_sigma_xy_cm=float(100*np.sqrt(np.trace(p[m,:2,:2],axis1=1,axis2=2).mean())),
                nees_heading=float(head[m].mean()),nees_xy=float(xy[m].mean()),nees_pose=float(nn[m].mean()),nees_cond_heading=float((ec[m]**2/vc[m]).mean()),n_used_score=int(z['used'][m].sum()),
                RF_range_mean_cm=float(rf[m,0].mean()*100),RF_range_rms_cm=rms(rf[m,0])*100,RF_s_mean=float(rf[m,1].mean()),RF_s_rms=rms(rf[m,1]),RF_s_acf1=acf(rf[m,1]),
                Rss_mean=float(z['Ru'][m,1,1].mean()),Rrr_mean=float(z['Ru'][m,0,0].mean()),Jpsi_rms=rms(j[m,1,2]),Jxy_rms=rms(np.linalg.norm(j[m,1,:2],axis=1)))
            allsummary.append(summary)
            df=pd.DataFrame(dict(case=c,route=c[:2],bias=b,observer=ob,k=np.arange(n),t_s=t,scored=m,heading_error_deg=np.degrees(e[:,2]),ex_cm=e[:,0]*100,ey_cm=e[:,1]*100,xy_error_cm=np.linalg.norm(e[:,:2],axis=1)*100,
                sigma_heading_deg=np.degrees(np.sqrt(p[:,2,2])),sigma_x_cm=np.sqrt(p[:,0,0])*100,sigma_y_cm=np.sqrt(p[:,1,1])*100,nees_heading=head,nees_xy=xy,nees_pose=nn,nees_cond_heading=ec**2/vc,
                RF_r_cm=rf[:,0]*100,RF_s=rf[:,1],nu_s=z['nu'][:,1],nu_r=z['nu'][:,0],nis=z['nis'],used=z['used'],J_spsi=j[:,1,2],J_sx=j[:,1,0],J_sy=j[:,1,1],Rss=z['Ru'][:,1,1]))
            pkts.append(df)
            for win in range(30,int(t[-1])+1,10):
                w=(t>=win)&(t<win+10)
                if w.any():windows.append(dict(case=c,bias=b,observer=ob,t_start=win,n=int(w.sum()),heading_mean_deg=float(np.degrees(e[w,2].mean())),heading_rmse_deg=rms(np.degrees(e[w,2])),xy_rmse_cm=float(np.sqrt(np.mean(np.sum(e[w,:2]**2,axis=1)))*100),nees_pose=float(nn[w].mean()),RF_s_mean=float(rf[w,1].mean()),RF_r_mean_cm=float(rf[w,0].mean()*100),Jpsi_rms=rms(j[w,1,2]),sigma_heading_rms_deg=float(np.degrees(np.sqrt(p[w,2,2].mean())))))
        es,ps,ns=cases['SourceFFD'];el,pl,nl=cases['LUT_fixed'];flips=l['used']!=s['used']
        cross.append(dict(case=c,bias=b,n_score=int(m.sum()),NEES_eS_PS=float(ns[m].mean()),NEES_eL_PS=float(nees(el,ps)[m].mean()),NEES_eS_PL=float(nees(es,pl)[m].mean()),NEES_eL_PL=float(nl[m].mean()),
          gate_flips_all=int(flips.sum()),gate_flips_score=int((flips&m).sum()),Rss_max_abs_difference=float(np.max(abs(l['Ru'][:,1,1]-s['Ru'][:,1,1]))),
          same_source_prior_s_delta_rms=rms(function_delta[m,1]),trajectory_s_delta_rms=rms(trajectory_delta[m,1]),total_nu_s_delta_rms=rms(nu_delta[m,1]),
          same_source_prior_Jpsi_delta_rms=rms(jls[m,1,2]-js[m,1,2]),same_source_prior_Jxy_delta_rms=rms(np.linalg.norm(jls[m,1,:2]-js[m,1,:2],axis=1))))
        donors.append(dict(case=c,bias=b,mu_s_min=float(l['mu'][:,1].min()),mu_s_max=float(l['mu'][:,1].max()),mu_r_mean_cm=float(l['mu'][m,0].mean()*100),mu_r_min_cm=float(l['mu'][:,0].min()*100),mu_r_max_cm=float(l['mu'][:,0].max()*100)))
        validation.append(dict(case=c,bias=b,stored_h_J_and_nu_match=True,NEES_Schur_identity=True))
        print('CASE_BIAS_DONE',c,b,flush=True)
    pd.DataFrame(allsummary).to_csv(OUT/'SUMMARY_24.csv',index=False);pd.DataFrame(cross).to_csv(OUT/'CROSS_COV_GATE_JACOBIAN_12.csv',index=False)
    pd.concat(truthrows,ignore_index=True).to_csv(OUT/'TRUTH_FORWARD_DECOMPOSITION_3136.csv',index=False)
    pd.concat(pkts,ignore_index=True).to_csv(OUT/'PACKET_DIAGNOSTICS.csv.gz',index=False);pd.DataFrame(windows).to_csv(OUT/'WINDOWS_10S.csv',index=False);pd.DataFrame(donors).to_csv(OUT/'FROZEN_DONOR_MEANS.csv',index=False)
    assert all(A.sha(p)==h for p,h in locked.items())
    dump('CHECKS.json',dict(status='COMPLETED',filter_replayed=False,inputs_unchanged=True,checks=validation,independent_audit=False,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    print('SUMMARY');print(pd.DataFrame(allsummary).groupby(['route','observer']).mean(numeric_only=True).to_string())
    print('CROSS');print(pd.DataFrame(cross).to_string(index=False))
if __name__=='__main__':
    try:main()
    except BaseException as e:dump('FAILURE.json',dict(error=repr(e),traceback=traceback.format_exc()));raise
