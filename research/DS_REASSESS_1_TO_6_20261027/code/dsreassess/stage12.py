"""1: fixed-mask EX delta; 2: RF residual covariance/serial-correlation audit."""
from __future__ import annotations
import numpy as np
import pandas as pd
from .io import Context,StageWriter
from .engine import replay,score,score_window,assert_off_parity,save_replay
from .numerics import range_h


def stage1(ctx:Context,writer:StageWriter):
    """B, EX, EXDS, truth-range-oracle on the identical frozen A_B schedule."""
    scores=[];raw_mu=[]
    for d in ctx.cases():
        runs={}
        for name,kind in [('BB','BASE'),('EX','EX'),('EXDS','EXDS'),('R_ORACLE','ORACLE')]:
            runs[name]=replay(ctx,d,name,mu_kind=kind)
        assert_off_parity(writer,d,runs['BB'],0)
        assert_off_parity(writer,d,runs['EXDS'],4)
        for arm in runs.values():
            scores.extend([score(d,arm),score_window(d,arm,ctx)])
            save_replay(writer,d,arm)
        raw_mu.append(pd.DataFrame({'case':d.case['id'],'bias':d.bias,'t_s':d.t,
                                    'pose_id':d.ids,'mu_base_m':d.mu_b,
                                    'mu_ex_m':d.mu_ex,'mu_exds_m':d.mu_exds,
                                    'mu_oracle_m':d.z[:,0]-np.array([range_h(t[:2],d.case,b_old=d.b_old)[0] for t in d.truth]),
                                    'delta_ex_minus_base_m':d.mu_ex-d.mu_b,
                                    'delta_exds_minus_ex_m':d.mu_exds-d.mu_ex}))
    df=pd.DataFrame(scores)
    writer.csv('SCORES.csv',df)
    writer.csv('PREDICTION_DECOMPOSITION.csv',pd.concat(raw_mu,ignore_index=True))
    joined=df[df.scope=='scoring'].pivot(index=['case','bias'],columns='arm',values='heading_rmse_deg')
    joined['EX_vs_BB']=joined['EX']/joined['BB']
    joined['EXDS_vs_EX']=joined['EXDS']/joined['EX']
    joined['EXDS_vs_BB']=joined['EXDS']/joined['BB']
    writer.csv('HEADING_CONTRASTS.csv',joined.reset_index())
    writer.finish({'interpretation':'EX->EXDS isolates added DS features conditional on unchanged HGB architecture, fixed A_B and frozen prediction; does not identify DS by randomized features',
                   'oracle_truth':'R_ORACLE uses z_r minus GT geometric range (diagnosis only)'})


def acf_one(x,lag):
    x=np.asarray(x,float)
    if len(x)<lag+3:return np.nan
    a=x[:-lag]-np.mean(x[:-lag]);b=x[lag:]-np.mean(x[lag:])
    den=np.sqrt((a@a)*(b@b))
    return float(a@b/den) if den>1e-24 else np.nan


def block_bootstrap_cov(x,y,t,*,seconds=8.,reps=300,seed=2710):
    """Contiguous nonoverlapping blocks; resample blocks, not i.i.d. packets."""
    x=np.asarray(x,float);y=np.asarray(y,float);t=np.asarray(t,float)
    if len(x)<6:return (np.nan,np.nan,np.nan)
    blocks=np.floor((t-t[0])/seconds).astype(int)
    block_ids=np.unique(blocks)
    if len(block_ids)<4:return (np.nan,np.nan,float(len(block_ids)))
    ids=[np.flatnonzero(blocks==b) for b in block_ids]
    gen=np.random.default_rng(seed)
    outcomes=[]
    for _ in range(reps):
        picks=gen.integers(0,len(ids),size=len(ids))
        take=np.concatenate([ids[i] for i in picks])
        outcomes.append(np.cov(x[take],y[take],ddof=1)[0,1])
    return (*map(float,np.percentile(outcomes,[2.5,97.5])),float(len(ids)))


def summary_residuals(df, *, secs=8., reps=300):
    out=[]
    for (case,bias,arm,bin_name,sample),g in df.groupby(['case','bias','arm','distance_bin','sample'],observed=True):
        if len(g)<8:continue
        x=g['er_m'].to_numpy(float);y=g['es'].to_numpy(float)
        px=g['Rrr'].to_numpy(float);py=g['Rss'].to_numpy(float)
        cov=float(np.cov(x,y,ddof=1)[0,1]);cxy=np.corrcoef(x,y)[0,1]
        low,high,nb=block_bootstrap_cov(x,y,g.t_s.to_numpy(),seconds=secs,reps=reps,
                                         seed=abs(sum(map(ord,case+bias+arm+str(bin_name)+sample)))+2710)
        out.append({'case':case,'bias':bias,'arm':arm,'distance_bin':bin_name,'sample':sample,
                    'n_packets':len(g),'duration_s':float(g.t_s.max()-g.t_s.min()),
                    'mean_er_m':float(np.mean(x)),'mean_es':float(np.mean(y)),
                    'var_er_centered':float(np.var(x,ddof=1)),'var_es_centered':float(np.var(y,ddof=1)),
                    'Rrr_mean':float(np.mean(px)),'Rss_mean':float(np.mean(py)),
                    'err_over_assumed_Rrr':float(np.var(x,ddof=1)/np.mean(px)),
                    'err_over_assumed_Rss':float(np.var(y,ddof=1)/np.mean(py)),
                    'cov_er_es':cov,'corr_er_es':float(cxy),
                    'cross_moment_er_es':float(np.mean(x*y)),
                    'cov_block_CI95_lo':low,'cov_block_CI95_hi':high,
                    'n_blocks':nb,'acf1_er':acf_one(x,1),'acf1_es':acf_one(y,1),
                    'acf5_er':acf_one(x,5),'acf5_es':acf_one(y,5)})
    return pd.DataFrame(out)


def _source_gt_batch(ctx,d,*,batch=32):
    n=len(d.t);h=np.empty((n,2));tap=np.empty(n,int);margin=np.empty(n)
    for start in range(0,n,batch):
        end=min(n,start+batch)
        obs,_,diag=ctx.model.batch(d.truth[start:end],d.case,
                                    gradient=False,return_diagnostics=True)
        h[start:end]=obs
        tap[start:end]=diag['tap']
        margin[start:end]=diag['fp_margin']
    return h,tap,margin


def stage2(ctx:Context,writer:StageWriter):
    """Use GT only for offline measurement-model residual scoring."""
    rows=[]; model_checks=[]
    for d in ctx.cases():
        hgt,tap,margin=_source_gt_batch(ctx,d)
        native=ctx.native_fp(d)
        measured_tap=native['tap']
        measured_margin=native['margin']
        tap_shift=measured_tap-tap
        abs_shift=abs(tap_shift)
        tap_class=np.select([abs_shift==0,abs_shift==1,abs_shift<=3],['0','1','2-3'],'4+')
        rgt=np.array([range_h(t[:2],d.case,b_old=d.b_old)[0] for t in d.truth])
        writer.check(d.key+'_source_GT_r_model',hgt[:,0],rgt,1e-10)
        # These are *measurement error at GT* rather than EKF innovation.
        er_true=d.z[:,0]-hgt[:,0]
        es_true=d.z[:,1]-hgt[:,1]
        dg=np.linalg.norm(d.truth[:,:2]-np.asarray(d.case['anchor'])[:2],axis=1)
        dist_bin=np.select([dg<1.5,dg<4],['near','mid'],'far')
        tap_transition=np.r_[False,tap[1:]!=tap[:-1]]
        measured_transition=np.r_[False,measured_tap[1:]!=measured_tap[:-1]]
        for arm,mu in [('BASE',d.mu_b),('EX',d.mu_ex),('EXDS',d.mu_exds)]:
            frame=pd.DataFrame({'case':d.case['id'],'route':d.case['route'],
                                'bias':d.bias,'arm':arm,'t_s':d.t,'pose_id':d.ids,
                                'distance_bin':dist_bin,'d_gt_m':dg,
                                'er_m':er_true-mu,'es':es_true-d.mu_s,
                                'Rrr':d.R[:,0,0],'Rss':d.R[:,1,1],
                                'mu_r':mu,'mu_s':d.mu_s,
                                'predicted_los_tap':tap,'predicted_los_fp_margin':margin,
                                'predicted_los_tap_transition':tap_transition,
                                'measured_full_tap':measured_tap,
                                'measured_full_fp_margin':measured_margin,
                                'measured_full_tap_transition':measured_transition,
                                'measured_minus_los_tap':tap_shift,
                                'fp_shift_class':tap_class,
                                'accepted_ab':d.mask})
            frame['sample']='all'
            rows.append(frame)
            accepted=frame[frame.accepted_ab].copy()
            accepted['sample']='accepted_A_B'
            rows.append(accepted)
        model_checks.append({'case':d.case['id'],'bias':d.bias,'taps_gt_changes':int(tap_transition.sum()),
                             'measured_tap_transitions':int(measured_transition.sum()),
                             'n_full_minus_los_tap_nonzero':int(np.count_nonzero(tap_shift)),
                             'min_predicted_fp_margin':float(margin.min()),
                             'min_measured_fp_margin':float(measured_margin.min()),
                             'note':'Native full RF FP tap is recomputed from input CIR; LoS tap is frozen SourceFFD prediction at GT'})
    df=pd.concat(rows,ignore_index=True)
    df.to_csv(writer.dir/'RESIDUALS.csv.gz',index=False,compression='gzip',float_format='%.16g')
    # Whole-sequence correlations (t bins are not contiguous; lag only all window).
    result=summary_residuals(df[df['distance_bin']=='far'],secs=ctx.cfg.block_seconds)
    more=[]
    for key,g in df.groupby(['case','bias','arm','sample'],observed=True):
        if len(g)<8:continue
        h=g.sort_values('t_s').copy()
        h['distance_bin']='whole'
        more.append(h)
    whole=pd.concat(more,ignore_index=True)
    result=pd.concat([result,summary_residuals(whole,secs=ctx.cfg.block_seconds)],ignore_index=True)
    # Add near and mid without interpreting gappy bins as continuous time lags.
    bins=summary_residuals(df[df['distance_bin']!='far'],secs=ctx.cfg.block_seconds)
    for field in ['acf1_er','acf1_es','acf5_er','acf5_es']:
        bins[field]=np.nan
    writer.csv('RESIDUAL_STATS.csv',pd.concat([result,bins],ignore_index=True))
    writer.csv('SOURCE_GT_DIAGNOSTICS.csv',model_checks)
    tap_stats=[]
    for key,g in df[(df['sample']=='all')&(df['bias']=='B0')].groupby(['route','case','arm','fp_shift_class'],observed=True):
        if len(g)<5:continue
        a=g['er_m'].to_numpy(float);b=g['es'].to_numpy(float)
        tap_stats.append({'route':key[0],'case':key[1],'arm':key[2],
                          'fp_shift_class':key[3],'n':len(g),
                          'mean_er_m':float(np.mean(a)),
                          'mean_es':float(np.mean(b)),
                          'cov_er_es':float(np.cov(a,b,ddof=1)[0,1]),
                          'RMS_es':float(np.sqrt(np.mean(b*b))),
                          'RMS_er_m':float(np.sqrt(np.mean(a*a)))})
    writer.csv('MEASURED_FP_SHIFT_STRATA.csv',tap_stats)
    writer.finish({'note':'B0/L2 share the same RF; no i.i.d. packet confidence intervals. Discontiguous distance-bin ACF not reported.',
                   'measurement_vs_prediction_tap':'Measured full RF FP tap is recomputed from original 4x Hann/IFFT/30-percent algorithm and checked against E1 s_fp.',
                   'R_target':'Rrr/Rss are prior POWER covariances; centered residual variance does not absorb mean bias.'})
