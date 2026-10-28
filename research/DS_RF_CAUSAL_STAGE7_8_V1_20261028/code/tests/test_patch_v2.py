"""Targeted failure-mode tests for the 450a21f Stage2/3/5 audit patch."""
from __future__ import annotations
import numpy as np
import pandas as pd
import pytest
from dsreassess.stage12 import original_lag_pairs, acf_paired, block_bootstrap_cov, summary_residuals
from dsreassess.stage34 import fit_held_route_cov
from dsreassess.observability import fisher,first_pass_windows
from dsreassess.fisher_independent import independent_nominal,independent_fisher
from test_synthetic_stages import make_ctx


def _base_original():
    raw=np.array([0,1,4,5,6,10],dtype=int)
    return pd.DataFrame(dict(case='R2',bias='B0',arm='EXDS',sample='all',
        distance_bin=['near','near','near','near','far','far'],
        packet_index=np.arange(6),raw_sample_index=raw,
        pose_id=101+raw*4,t_s=[0.,.2,.8,1.,1.2,2.],
        accepted_ab=[True,True,True,False,True,True],
        er_m=[.2,.1,-.1,-.2,.4,.6],es=[.2,.09,-.07,-.2,.3,.5],
        Rrr=.01,Rss=.01))


def test_lag_real_native_gaps_not_filtered_adjacency():
    b=_base_original()
    i,j,diag=original_lag_pairs(b,distance_bin='whole',sample='all',lag=1,min_pairs=2)
    assert list(zip(b.raw_sample_index.iloc[i],b.raw_sample_index.iloc[j]))==[(0,1),(4,5),(5,6)]
    assert diag['n_pairs']==3
    assert diag['excluded_missing_native']>0
    i,j,sel=original_lag_pairs(b,distance_bin='near',sample='accepted_A_B',lag=1,min_pairs=1)
    assert [(int(b.raw_sample_index.iloc[q]),int(b.raw_sample_index.iloc[r])) for q,r in zip(i,j)]==[(0,1)]
    assert sel['excluded_distance_bin']>=1 and sel['excluded_accept_mask']==1
    assert sel['elapsed_med_s']==pytest.approx(.2)
    assert np.isnan(acf_paired(b.er_m.to_numpy()[i],b.er_m.to_numpy()[j],min_pairs=5))
    _,_,lag5=original_lag_pairs(b,distance_bin='whole',sample='all',lag=5,min_pairs=1)
    assert lag5['n_pairs']==3  # native rows 0->5, 1->6 and 5->10


def test_fixed_origin_three_block_lengths_and_explicit_na():
    rng=np.random.default_rng(122)
    t=np.arange(160)*.2
    x=rng.normal(size=len(t));y=x*.4+rng.normal(size=len(t))*.1
    keep=(t>=3)&(t<=17)
    z=block_bootstrap_cov(x[keep],y[keep],t[keep],origin_s=0.,seconds=8.,reps=80)
    assert z['status']=='NA_INSUFFICIENT_BLOCKS_OR_PACKETS'
    full=block_bootstrap_cov(x,y,t,origin_s=0.,seconds=8.,reps=80)
    assert full['status']=='PASS' and full['n_blocks']==4
    n=160
    g=pd.DataFrame(dict(case='R2',bias='B0',arm='EXDS',sample='all',
        distance_bin=np.where(np.arange(n)%15<6,'near','far'),
        packet_index=np.arange(n),raw_sample_index=np.arange(n),
        pose_id=100+np.arange(n)*4,t_s=np.arange(n)*.2,
        accepted_ab=(np.arange(n)%7!=0),er_m=x,es=y,
        Rrr=np.full(n,.01),Rss=np.full(n,.01)))
    accepted=g[g.accepted_ab].copy();accepted['sample']='accepted_A_B'
    whole=pd.concat([g,accepted],ignore_index=True)
    whole['distance_bin']='whole'
    stats=summary_residuals(pd.concat([g,accepted,whole],ignore_index=True),reps=30,min_lag_pairs=1)
    assert 'boot_8_status' in stats and 'boot_16_status' in stats and 'boot_32_status' in stats
    assert 'lag1_n_pairs' in stats and 'lag5_n_pairs' in stats
    assert stats['bootstrap_stability'].str.len().gt(0).all()
    assert stats['original_origin_s'].eq(0).all()


def test_covariance_sample_specific_heldout_fallback():
    rng=np.random.default_rng(17)
    r=[]
    for route in ('R2','R4','R5'):
        for i in range(40):
            y=float(rng.normal())
            for samp in ('all','accepted_A_B'):
                if samp=='accepted_A_B' and i>=12:continue
                r.append(dict(route=route,bias='B0',case=route,arm='BASE',
                              sample=samp,distance_bin='near' if i<3 else 'far',
                              er_m=y+(50 if samp=='all' else 0),es=y/4))
    df=pd.DataFrame(r)
    # Primary accepted near has too few observations => same-population whole fallback.
    # With minimum=20 even whole accepted (2 routes x 12) is enough.
    cov,meta=fit_held_route_cov(df,target_route='R2',arm='BASE',
                                dist_bin='near',minimum=20,sample_condition='accepted_A_B')
    assert meta['status']=='WHOLE_SAME_POPULATION_FALLBACK'
    assert meta['n_train']==24 and meta['train_routes']=='R4,R5'
    assert abs(meta['route_mean_er_m'])<10 # rejected/whole +50 offset never leaked
    with pytest.raises(RuntimeError,match='INSUFFICIENT_HELD_ROUTE'):
        fit_held_route_cov(df,target_route='R2',arm='BASE',dist_bin='near',
                           minimum=200,sample_condition='accepted_A_B')
    assert np.linalg.eigvalsh(cov).min()>0


def test_independent_fisher_real_input_synthetic(tmp_path):
    ctx=make_ctx(tmp_path)
    d=next(ctx.cases())
    span=first_pass_windows(ctx,d)[0]
    x,phi=independent_nominal(d,span,'GT')
    _,h=ctx.model.batch(x,d.case)
    for use_pol in (False,True):
        for bias5 in (False,True):
            for use_prior in (False,True):
                ref=fisher(ctx,d,span=span,nominal='GT',use_pol=use_pol,
                           use_prior=use_prior,bias5=bias5)
                qa,W,B,_=independent_fisher(d,span,x,phi,h,pol=use_pol,
                                             prior=use_prior,bias5=bias5,
                                             bias_prior_var=ctx.cfg.augmented_br_prior_std_m**2)
                assert ref['rank']==qa['rank']==qa['rank_svd']
                if np.isinf(ref['sigma_terminal_tan_cm']):
                    assert np.isinf(qa['sigma_terminal_tan_cm'])
                else:
                    assert ref['sigma_terminal_tan_cm']==pytest.approx(qa['sigma_terminal_tan_cm'],abs=.02)
                assert np.all(np.linalg.eigvalsh(W)>=-1e-7)
    # Independently calculated design matrix should not silently accept a
    # deliberately rotated/incorrect nominal Jacobian.
    wrong=h.copy();wrong[:,1,0]+=.5
    qa_bad,Wbad,_,_=independent_fisher(d,span,x,phi,wrong,pol=True,
                                       prior=False,bias5=False)
    qa_ok,Wok,_,_=independent_fisher(d,span,x,phi,h,pol=True,
                                    prior=False,bias5=False)
    assert np.max(abs(Wbad-Wok))>1.0


def test_verified_cache_stage2_reanalysis_without_rf_recompute(tmp_path):
    """End-to-end synthetic cache import, hash gating and source packet alignment."""
    import json,hashlib
    from pathlib import Path
    from dsreassess.io import StageWriter,sha256
    from dsreassess.stage12 import stage2,stage2_from_verified_cache
    original=tmp_path/'old';new=tmp_path/'new'
    original.mkdir();new.mkdir()
    ctx=make_ctx(original)
    stage2(ctx,StageWriter(ctx,'02_residuals'))
    ctx.cfg.output_root=new
    ctx.cfg.source_root=tmp_path/'native'
    evidence=tmp_path/'evidence'
    evidence.joinpath('e1_e4').mkdir(parents=True)
    ctx.base=evidence
    ctx._verified={}
    ctx.verify_manifest_file=lambda p:ctx._verified.update({Path(p).resolve():sha256(Path(p))})
    snap=[]
    seen=set()
    for d in ctx.cases():
        if d.case['id'] in seen:continue
        seen.add(d.case['id'])
        rel=d.case['id']+'/SAMPLES.json'
        d.case['samples_path']=rel
        fn=ctx.cfg.source_root/rel
        fn.parent.mkdir(parents=True,exist_ok=True)
        fn.write_text(json.dumps([{'pose_id':int(x)} for x in d.ids]),encoding='utf-8')
        snap.append({'path':'D:/frozen/p2/'+rel,'sha256':sha256(fn)})
    (evidence/'e1_e4/INPUT_LOCK.json').write_text(json.dumps({'files':snap}))
    stage2_from_verified_cache(ctx,StageWriter(ctx,'02_residuals'),original)
    output=pd.read_csv(new/'02_residuals/RESIDUAL_STATS.csv')
    assert len(output)>0
    assert 'lag1_excluded_missing_native' in output.columns
    assert int(output.lag1_excluded_missing_native.max())==0
    assert output.bootstrap_stability.notna().all()
    # Corrupting one original byte must cause a hard failure, never fallback.
    f=original/'02_residuals/RESIDUALS.csv.gz'
    f.write_bytes(f.read_bytes()+b'CRASH')
    other=tmp_path/'bad';other.mkdir()
    ctx.cfg.output_root=other
    with pytest.raises(RuntimeError,match='UNVERIFIED_STAGE2_CACHE'):
        stage2_from_verified_cache(ctx,StageWriter(ctx,'02_residuals'),original)
