"""S0 offline population statistics only. No RF or recursive filter execution."""
from pathlib import Path
import argparse, gzip, hashlib, io, json, math, os, zipfile
import numpy as np
import pandas as pd
from github_io import session, download

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
AUDIT = REPO/'research/POWERJOINT_AUDIT_RERUN_20261020'
B = -0.5315983906250129
DELTA = 299792458/(4*257*1.95e6)
SIGMA = DELTA/math.sqrt(12)

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p, obj): p.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
def stats(g):
    e = g.error_m.to_numpy(float)
    if not len(e): return dict(n=0, **{k:None for k in ['mean_m','rmse_m','q01_m','q05_m','q50_m','q95_m','q99_m','fraction_abs_error_gt_delta_over2','rmse_over_sigma_q']})
    q = np.quantile(e, [.01,.05,.5,.95,.99], method='linear')
    return dict(n=len(e), mean_m=float(e.mean()), rmse_m=float(np.sqrt(np.mean(e*e))),
        **dict(zip(['q01_m','q05_m','q50_m','q95_m','q99_m'], map(float,q))),
        fraction_abs_error_gt_delta_over2=float(np.mean(abs(e)>DELTA/2)), rmse_over_sigma_q=float(np.sqrt(np.mean(e*e))/SIGMA))

def main():
    p=argparse.ArgumentParser();p.add_argument('--cache',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();args.cache.mkdir(parents=True,exist_ok=True);args.out.mkdir(parents=True,exist_ok=True)
    lock=json.loads((HERE/'PROTOCOL_LOCK.json').read_text());receipt=json.loads((HERE/'TRACE_RECEIPT.json').read_text())
    # Receipt schema is checked before any statistical calculation.
    records=receipt['artifacts']
    assert receipt['task_status']=='COMPLETE' and len(records)==44
    inputs={};archives={}
    for aid in [12188081569,11782748118]:
        rec=next(r for r in records if int(r['artifact_id'])==aid)
        dest=args.cache/f'{aid}.zip'
        url=rec['release_asset_url']
        download(session(),url,dest)
        assert sha(dest)==rec['downloaded_sha256']
        assert dest.stat().st_size==rec['downloaded_bytes']
        inputs[str(aid)]=dict(url=url,sha256=sha(dest),bytes=dest.stat().st_size)
        archives[aid]=dest
    with zipfile.ZipFile(archives[12188081569]) as z:
        label=z.read('PACKETS_SOURCE_LABELS.csv.gz')
        assert hashlib.sha256(label).hexdigest()=='02038c4c967750905a80dde31b0bcd0b667bd5d11df1cb02e05023e06893ee4d'
        frame=pd.read_csv(io.BytesIO(label),compression='gzip')
        generator=z.read('scripts/run.py')
        (args.out/'ORIGINAL_LABEL_GENERATOR.py').write_bytes(generator)
    manifest=REPO/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json'
    cases={c['id']:c for c in json.loads(manifest.read_text())['cases']}
    assert not frame.duplicated(['case','channel','pose_id']).any()
    for cid,c in cases.items():
        mask=frame.case==cid
        horizontal=np.hypot(frame.loc[mask,'x_eval']-c['anchor'][0],frame.loc[mask,'y_eval']-c['anchor'][1])
        height=c['anchor'][2]-c['robot_z_m']
        assert height>0
        frame.loc[mask,'distance_m']=np.sqrt(horizontal**2+height**2)
        frame.loc[mask,'theta_deg']=np.degrees(np.arctan2(horizontal,height))
        assert np.max(abs(horizontal-frame.loc[mask,'rho_m']))<1e-12
    frame['error_m']=frame.range_m-(frame.distance_m+B)
    er_diff=float(abs(frame.error_m-frame.e_r).max())
    assert er_diff<1e-12
    los=frame[frame.channel=='los'].copy().sort_values(['case','pose_id'])
    counts={str(k):int(v) for k,v in los.groupby('case').size().items()}
    assert counts==lock['S0_2']['expected_counts'] and len(los)==9519
    assert np.isfinite(los[['error_m','distance_m','theta_deg']].to_numpy()).all()
    taps=np.rint(los.range_m/DELTA).astype(int)
    tap_grid_error=float(abs(los.range_m/DELTA-taps).max());assert tap_grid_error<=1e-6
    assert (taps.to_numpy()==los.tap.to_numpy(int)).all()
    los['original_tap']=taps;los['tap_group']='STABLE'
    for _,g in los.groupby('case',sort=False):
        change=g.original_tap.ne(g.original_tap.shift());los.loc[g.index[change],'tap_group']='TRANSITION';los.loc[g.index[0],'tap_group']='FIRST'
    prior_path=AUDIT/'T6_RANGE/native_execution_r01/NATIVE_RESIDUALS.csv'
    prior=pd.read_csv(prior_path);assert len(prior)==7251 and not prior.duplicated(['case','pose_id']).any()
    matched=prior.merge(los,on=['case','pose_id'],validate='one_to_one',suffixes=('_clock',''))
    assert len(matched)==7251
    comparisons={'range_m':float(abs(matched.observed_m-matched.range_m).max()),
        'distance_m':float(abs(matched.distance_m_clock-matched.distance_m).max()),
        'error_m':float(abs(matched.error_old_m-matched.error_m).max())}
    assert max(comparisons.values())<1e-12
    keys=pd.MultiIndex.from_frame(prior[['case','pose_id']]);los['in_recursive_clock7251']=pd.MultiIndex.from_frame(los[['case','pose_id']]).isin(keys)
    prior_stats=[];group_stats=[]
    for pop,g in [('RF_ARCHIVE_9519',los),('RECURSIVE_CLOCK_7251',los[los.in_recursive_clock7251])]:
        for cid,cg in g.groupby('case'):
            prior_stats.append(dict(population=pop,case=cid,**stats(cg)))
            for axis,edges in [('distance_m',lock['S0_2']['distance_bin_edges_m']),('theta_deg',lock['S0_2']['theta_bin_edges_deg'])]:
                edges=[float(v) for v in edges]
                for i,(lo,hi) in enumerate(zip(edges[:-1],edges[1:])):
                    mask=(cg[axis]>=lo)&((cg[axis]<=hi) if axis=='theta_deg' and i==len(edges)-2 else (cg[axis]<hi))
                    group_stats.append(dict(population=pop,case=cid,grouping=axis,group=f'[{lo},{hi}{"]" if axis=="theta_deg" and i==len(edges)-2 else ")"}',**stats(cg[mask])))
            for name in ['FIRST','STABLE','TRANSITION']:
                group_stats.append(dict(population=pop,case=cid,grouping='tap_transition',group=name,**stats(cg[cg.tap_group==name])))
    pd.DataFrame(prior_stats).to_csv(args.out/'NATIVE_LOS_CASE_STATS.csv',index=False)
    pd.DataFrame(group_stats).to_csv(args.out/'NATIVE_LOS_GROUP_STATS.csv',index=False)
    los[['case','pose_id','range_m','distance_m','theta_deg','error_m','original_tap','tap_group','in_recursive_clock7251']].to_csv(args.out/'NATIVE_LOS_ROWS.csv',index=False)
    failed=[r['case'] for r in prior_stats if r['population']=='RF_ARCHIVE_9519' and not(abs(r['mean_m'])<.01 and .8<=r['rmse_over_sigma_q']<=1.2)]
    # Frozen trace row IDs AND truth AND observations certify the slide's829 population.
    frozen={}
    with zipfile.ZipFile(archives[11782748118]) as z:
        m=next(n for n in z.namelist() if n.endswith('P2_ONE_STEP_SUMMARY.json'))
        for rec in json.loads(z.read(m))['per_case']:
            if rec['channel']!='full' or not rec['case'].startswith('R2'):continue
            name=next(n for n in z.namelist() if n.endswith(rec['trace_file']))
            with np.load(io.BytesIO(z.read(name)),allow_pickle=False) as a:frozen[rec['case']]={k:a[k].copy() for k in a.files}
    slide=[];mapping=[];old={'R2_aA_m0':(.05225,.01708,.525),'R2_aA_m45':(.07187,.01658,.062),'R2_aB_m0':(.03069,.00807,.096)}
    previous=pd.read_csv(AUDIT/'T3_SOURCEFFD_TABLES/SLIDE2_RANGE_STATS.csv')
    for cid,a in frozen.items():
        g=frame[(frame.case==cid)&(frame.channel=='full')].set_index('pose_id')
        gg=g.loc[a['pose_id']]
        deltas=dict(x=float(abs(gg.x_eval.to_numpy()-a['truth_for_offline_scoring_only'][:,0]).max()),y=float(abs(gg.y_eval.to_numpy()-a['truth_for_offline_scoring_only'][:,1]).max()),range=float(abs(gg.range_m.to_numpy()-a['z_r_m']).max()),s=float(abs(gg.s_fp.to_numpy()-a['z_s']).max()))
        assert max(deltas.values())<1e-12,(cid,deltas)
        clock=gg.loc[a['t_s']>=30];assert len(clock)==829 and len(g)==1303
        mapping.append(dict(case=cid,archive_count=len(g),clock_all_count=len(gg),clock_t30_count=len(clock),**deltas))
        for pop,cg in [('ORIGINAL_ALL_RF_1303',g),('SLIDE_SOURCEFFD_T30_829',clock)]:
            er=cg.error_m.to_numpy();es=cg.e_s.to_numpy();mu=float(er.mean());var=float(er.var());rho=float(np.corrcoef(er,es)[0,1])
            slide.append(dict(case=cid,population=pop,n=len(cg),selected_for_slide=pop=='SLIDE_SOURCEFFD_T30_829',range_model='B_OLD',s_model='SourceFFD',mu_r_m=mu,V_r_m2=var,V_r_over_R0_r=var/.0068578637,rho_er_es=rho,old_LUT_all1303_mu_r_m=old[cid][0],old_LUT_all1303_V_r_m2=old[cid][1],old_LUT_all1303_rho_er_es=old[cid][2],original_time_window='NOT_ESTABLISHED_NO_TIMESTAMP' if pop=='ORIGINAL_ALL_RF_1303' else 't>=30s frozen trace clock'))
            if pop=='SLIDE_SOURCEFFD_T30_829':
                prev=previous[previous.case==cid].iloc[0]
                assert max(abs(mu-prev.mu_r_m),abs(var-prev.V_r_m2),abs(rho-prev.rho_er_es))<1e-12
    pd.DataFrame(slide).to_csv(args.out/'SLIDE2_RANGE_STATS_POPULATIONS.csv',index=False)
    pd.DataFrame(mapping).to_csv(args.out/'SLIDE2_ROW_MAPPING.csv',index=False)
    save(args.out/'STATISTICS_SUMMARY.json',dict(technical='TECHNICAL_PASS',work_status='OPEN' if failed else 'CLOSED_QUANTIZATION',scientific='NOT_ESTABLISHED' if failed else 'SUPPORTED_BUT_LIMITED',delta_m=DELTA,sigma_q_m=SIGMA,counts=counts,total=9519,clock_total=7251,failed_cases=failed,independent_geometry_vs_cached_er_max=er_diff,prior_clock_match_max=comparisons,tap_grid_error=tap_grid_error,slide_population='SLIDE_SOURCEFFD_T30_829',no_recursive_or_RF_execution=True))
    save(args.out/'STATISTICS_MANIFEST.json',dict(actions_run_id=os.getenv('GITHUB_RUN_ID'),source_commit=os.getenv('GITHUB_SHA'),inputs=inputs,label_sha256=hashlib.sha256(label).hexdigest(),case_manifest_sha256=sha(manifest),protocol_sha256=sha(HERE/'PROTOCOL_LOCK.json'),prior_native_sha256=sha(prior_path),generator_sha256=hashlib.sha256(generator).hexdigest(),python=__import__('sys').version,numpy=np.__version__,pandas=pd.__version__,output_sha256={p.name:sha(p) for p in args.out.iterdir() if p.is_file()}))

if __name__=='__main__': main()
