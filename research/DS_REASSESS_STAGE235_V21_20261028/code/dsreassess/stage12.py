"""1: fixed-mask EX delta; 2: RF residual covariance/serial-correlation audit."""
from __future__ import annotations
import hashlib
from itertools import product
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


# Legacy acf_one(array, lag) was invalid for a filtered, gappy packet sequence.
# All lag statistics below use a stable row number from the original Full RF.
BOOT_SECONDS=(8.,16.,32.)
LAGS=(1,5)
MIN_LAG_PAIRS=8
MIN_BOOT_BLOCKS=4


def acf_paired(x0, x1, min_pairs=MIN_LAG_PAIRS):
    """Pearson correlation on eligible *original packet* (k,k+lag) pairs."""
    a=np.asarray(x0,float);b=np.asarray(x1,float)
    if len(a)<min_pairs:return np.nan
    a=a-a.mean();b=b-b.mean()
    den=float(np.sqrt((a@a)*(b@b)))
    return float(a@b/den) if den>1e-24 else np.nan


def original_lag_pairs(base, *, distance_bin, sample, lag, min_pairs=MIN_LAG_PAIRS):
    """Return valid pair indices, diagnostics, and elapsed-time distribution.

    base is the unfiltered `whole/all` sequence with unique native RF row IDs.
    Missing E1 packets, rejected packets and distance-bin excursions MUST NOT
    become new neighbors after filtering. pose_id is a key, never a clock.
    """
    if sample not in ('all','accepted_A_B') or distance_bin not in ('whole','near','mid','far'):
        raise ValueError('unknown sample or distance bin')
    b=base.sort_values('packet_index',kind='stable').reset_index(drop=True)
    native=b.raw_sample_index.to_numpy(np.int64)
    stored=b.packet_index.to_numpy(np.int64)
    time=b.t_s.to_numpy(float)
    if len(native)<2 or np.any(np.diff(native)<=0) or np.any(np.diff(stored)!=1) or np.any(np.diff(time)<=0):
        raise RuntimeError('original packet order/time not strictly increasing')
    if b.pose_id.duplicated().any():raise RuntimeError('duplicate raw pose_id in E1 sequence')
    # Find the actual native Full RF packet at +lag, NOT position i+lag after filtering.
    j=pd.Index(native).get_indexer(native+lag)
    exists=j>=0
    i=np.flatnonzero(exists)
    v=j[i]
    inbin=(np.ones(len(b),bool) if distance_bin=='whole' else
           b.distance_bin.to_numpy(str)==distance_bin)
    inbin_pair=inbin[i]&inbin[v]
    acc=b.accepted_ab.to_numpy(bool)
    acc_pair=acc[i]&acc[v]
    good=inbin_pair if sample=='all' else (inbin_pair&acc_pair)
    i_good=i[good];j_good=v[good]
    seconds=time[j_good]-time[i_good]
    result={'lag_packet':int(lag),'n_pairs':int(len(i_good)),
            'candidate_existing_pairs':int(len(i)),
            'excluded_missing_native':int(np.count_nonzero((native+lag<=native[-1])&~exists)),
            'excluded_distance_bin':int(np.count_nonzero(~inbin_pair)),
            'excluded_accept_mask':int(np.count_nonzero(inbin_pair&~acc_pair)) if sample=='accepted_A_B' else 0,
            'elapsed_min_s':float(seconds.min()) if len(seconds) else np.nan,
            'elapsed_med_s':float(np.median(seconds)) if len(seconds) else np.nan,
            'elapsed_max_s':float(seconds.max()) if len(seconds) else np.nan,
            'status':'PASS' if len(i_good)>=min_pairs else 'NA_INSUFFICIENT_NATIVE_LAG_PAIRS'}
    return i_good,j_good,result


def block_bootstrap_cov(x,y,t, *, origin_s, seconds=8., reps=300,
                        seed=2710,min_blocks=MIN_BOOT_BLOCKS):
    """Fixed-origin time blocks with paired, block-resampled centered covariance.

    Block boundaries are anchored to the ORIGINAL case start, never the first
    accepted/binned packet. Resample nonempty blocks (pairs stay together).
    All nonavailability is explicit rather than reported as a zero covariance.
    """
    x=np.asarray(x,float);y=np.asarray(y,float);t=np.asarray(t,float)
    if not (x.shape==y.shape==t.shape) or seconds<=0 or reps<10:
        raise ValueError('bootstrap covariance parameters/shapes invalid')
    if not len(x):
        return {'lo':np.nan,'hi':np.nan,'n_blocks':0,'block_n_min':0,
                'block_n_median':np.nan,'block_n_max':0,'status':'NA_NO_SAMPLES'}
    if np.any(np.diff(t)<0):raise ValueError('bootstrap needs original time order')
    if np.any(t < origin_s-1e-7):raise ValueError('origin after first sample')
    # Epsilon only avoids roundoff when a packet falls on a nominal boundary.
    bid=np.floor((t-origin_s)/seconds+1e-10).astype(np.int64)
    _,rev=np.unique(bid,return_inverse=True)
    B=int(rev.max()+1)
    counts=np.bincount(rev,minlength=B)
    out={'n_blocks':B,'block_n_min':int(counts.min()),
         'block_n_median':float(np.median(counts)),'block_n_max':int(counts.max())}
    if B<min_blocks or len(x)<8:
        return dict(out,lo=np.nan,hi=np.nan,status='NA_INSUFFICIENT_BLOCKS_OR_PACKETS')
    # Block sufficient statistics: no concatenation and O(B*reps) memory.
    nx=counts.astype(float)
    sx=np.bincount(rev,weights=x,minlength=B)
    sy=np.bincount(rev,weights=y,minlength=B)
    sxy=np.bincount(rev,weights=x*y,minlength=B)
    gen=np.random.default_rng(seed)
    pick=gen.integers(0,B,size=(reps,B))
    n=nx[pick].sum(axis=1)
    u=sx[pick].sum(axis=1);v=sy[pick].sum(axis=1)
    w=sxy[pick].sum(axis=1)
    vals=(w-u*v/n)/(n-1)
    if not np.isfinite(vals).all():
        raise RuntimeError('nonfinite bootstrap covariance')
    lo,hi=np.percentile(vals,[2.5,97.5])
    return dict(out,lo=float(lo),hi=float(hi),status='PASS')


def summary_residuals(df, *, secs=8., reps=300, block_sizes=BOOT_SECONDS,
                      min_lag_pairs=MIN_LAG_PAIRS):
    """Per-bin, selected-population diagnostics on the unfiltered raw time axis.

    Expected `df`: one copy of each raw packet for sample=all/accepted_A_B,
    and for distance_bin=(original bin, whole). The original distance-labelled all rows supply
    packet alignment; observed E1/native gaps are never bridged.
    """
    required={'case','bias','arm','distance_bin','sample','packet_index',
              'raw_sample_index','pose_id','accepted_ab','t_s','er_m','es',
              'Rrr','Rss'}
    if m:=required-set(df.columns):raise ValueError(f'missing residual columns {m}')
    if tuple(float(v) for v in block_sizes)!=BOOT_SECONDS:
        raise ValueError('pre-registered bootstrap block sizes must be 8/16/32s')
    # Keep the native distance labels: the whole copy is for reporting only.
    native=df[(df['sample']=='all') & df['distance_bin'].isin(('near','mid','far'))]
    source={key:g.sort_values('packet_index',kind='stable').reset_index(drop=True)
            for key,g in native.groupby(['case','bias','arm'],observed=True)}
    expected_keys=set(map(tuple,df[['case','bias','arm']].drop_duplicates().to_numpy()))
    if set(source)!=expected_keys:
        raise ValueError('original distance-labelled all population required')
    groups={key:g for key,g in df.groupby(
        ['case','bias','arm','distance_bin','sample'],observed=True)}
    out=[]
    # Explicit rows even when a bin or its accepted subset has no observations.
    for (case,bias,arm),bin_name,sample in product(
            sorted(source),('whole','near','mid','far'),('all','accepted_A_B')):
        g=groups.get((case,bias,arm,bin_name,sample),df.iloc[:0])
        full=source[(case,bias,arm)]
        valid_ids=set(full.raw_sample_index.to_numpy(np.int64))
        if (len(full.raw_sample_index)!=len(valid_ids) or
                not set(g.raw_sample_index.to_numpy(np.int64)).issubset(valid_ids)):
            raise RuntimeError('subset does not match original RF packet index')
        g=g.sort_values('packet_index',kind='stable')
        x=g['er_m'].to_numpy(float);y=g['es'].to_numpy(float)
        px=g['Rrr'].to_numpy(float);py=g['Rss'].to_numpy(float)
        enough=len(g)>=8
        sample_status=('PASS' if enough else
                       'NA_NO_SAMPLES' if not len(g) else 'NA_INSUFFICIENT_PACKETS')
        cov=float(np.cov(x,y,ddof=1)[0,1]) if enough else np.nan
        varx=float(np.var(x,ddof=1)) if enough else np.nan
        vary=float(np.var(y,ddof=1)) if enough else np.nan
        def mean_or_na(values):
            return float(np.mean(values)) if len(values) else np.nan

        corr=float(cov/np.sqrt(varx*vary)) if varx>0 and vary>0 else np.nan
        label=f'{case}|{bias}|{arm}|{bin_name}|{sample}'
        seed=int.from_bytes(hashlib.sha256(label.encode('utf-8')).digest()[:8],'little')
        result={'case':case,'bias':bias,'arm':arm,'distance_bin':bin_name,'sample':sample,
                'n_packets':len(g),'duration_s':float(g.t_s.max()-g.t_s.min()),
                'sample_status':sample_status,
                'mean_er_m':mean_or_na(x) if enough else np.nan,
                'mean_es':mean_or_na(y) if enough else np.nan,
                'var_er_centered':varx,'var_es_centered':vary,
                'Rrr_mean':mean_or_na(px),'Rss_mean':mean_or_na(py),
                'err_over_assumed_Rrr':float(varx/mean_or_na(px)),
                'err_over_assumed_Rss':float(vary/mean_or_na(py)),
                'cov_er_es':cov,'corr_er_es':corr,
                'cross_moment_er_es':mean_or_na(x*y) if enough else np.nan,
                'original_origin_s':float(full.t_s.iloc[0])}
        selected=full.raw_sample_index.isin(g.raw_sample_index).to_numpy()
        expected=(np.ones(len(full),bool) if bin_name=='whole' else
                  full.distance_bin.to_numpy(str)==bin_name)
        if sample=='accepted_A_B':expected &= full.accepted_ab.to_numpy(bool)
        if int(selected.sum())!=len(g) or not np.array_equal(selected,expected):
            raise AssertionError('population mismatch')
        for lag in LAGS:
            ii,jj,m=original_lag_pairs(full,distance_bin=bin_name,sample=sample,
                                        lag=lag,min_pairs=min_lag_pairs)
            for col in ('er_m','es'):
                vec=full[col].to_numpy(float)
                result[f'acf{lag}_{"er" if col=="er_m" else "es"}']=acf_paired(vec[ii],vec[jj],min_lag_pairs)
            for key,val in m.items():result[f'lag{lag}_{key}']=val
        signs=[];n_ok=0
        for duration in BOOT_SECONDS:
            name=str(int(duration))
            boot=block_bootstrap_cov(x,y,g.t_s.to_numpy(float),
                                     origin_s=float(full.t_s.iloc[0]),
                                     seconds=duration,reps=reps,seed=seed+int(duration))
            for col,val in boot.items():result[f'boot_{name}_{col}']=val
            if boot['status']=='PASS':
                n_ok+=1
                signs.append(1 if boot['lo']>0 else -1 if boot['hi']<0 else 0)
        # Preserve legacy 8-second columns for easy comparison of old tables.
        result.update(cov_block_CI95_lo=result['boot_8_lo'],
                      cov_block_CI95_hi=result['boot_8_hi'],
                      n_blocks=result['boot_8_n_blocks'])
        result['bootstrap_stability']=(
            'STABLE_POS' if n_ok==3 and signs==[1,1,1] else
            'STABLE_NEG' if n_ok==3 and signs==[-1,-1,-1] else
            'INSUFFICIENT_8_16_32' if n_ok<3 else 'SENSITIVE_OR_INCLUDES_ZERO')
        out.append(result)
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
                                'packet_index':np.arange(len(d.t),dtype=np.int64),
                                'raw_sample_index':native['raw_sample_index'],
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
                             'n_missing_native_rf_rows_between_e1_packets':int(np.sum(np.maximum(
                                 np.diff(native['raw_sample_index'])-1,0))),
                             'min_predicted_fp_margin':float(margin.min()),
                             'min_measured_fp_margin':float(measured_margin.min()),
                             'note':'Native full RF FP tap is recomputed from input CIR; LoS tap is frozen SourceFFD prediction at GT'})
    df=pd.concat(rows,ignore_index=True)
    df.to_csv(writer.dir/'RESIDUALS.csv.gz',index=False,compression='gzip',float_format='%.16g')
    # All groups are aligned against the same original packet sequence.
    # Distance bins and accepted groups remain explicit subsets; neither
    # ACF nor bootstrap interprets their filtered rows as adjacent packets.
    entire=df.copy()
    entire['distance_bin']='whole'
    statistics_input=pd.concat([df,entire],ignore_index=True)
    result=summary_residuals(statistics_input,reps=300)
    writer.csv('RESIDUAL_STATS.csv',result)
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
    writer.finish({'note':'B0/L2 share the same RF; no i.i.d. packet confidence intervals. Distance-bin ACF uses native packet lag pairs, never filtered adjacency.',
                   'measurement_vs_prediction_tap':'Measured full RF FP tap is recomputed from original 4x Hann/IFFT/30-percent algorithm and checked against E1 s_fp.',
                   'R_target':'Rrr/Rss are prior POWER covariances; centered residual variance does not absorb mean bias.',
                   'lag_definition':'native Full RF row index difference = 1/5; both endpoints pass subset masks',
                   'bootstrap':'8/16/32 s; fixed original RF sequence start; explicit NA for insufficient blocks',
                   'statistics_revision':'v2 packet-aligned, sample-consistent lag statistics; no EKF replay'})


def stage2_from_verified_cache(ctx:Context,writer:StageWriter,old_results_root):
    """Recalculate *statistics only* from the original hashed Stage-2 residuals.

    No Full CIR FFT/SourceFFD batch is rerun. The original 450a21f residuals
    must match its SHA manifest; packet indices come from the original native
    `samples_path` order AND frozen E1 trace. No CSV row order is trusted.
    """
    from pathlib import Path
    from .io import sha256,read_json
    old=Path(old_results_root).resolve()/'02_residuals'
    manifest=read_json(old/'OUTPUT_SHA256.json')
    required=['RESIDUALS.csv.gz','SOURCE_GT_DIAGNOSTICS.csv',
              'MEASURED_FP_SHIFT_STRATA.csv','CHECKS.json','RUN_STATUS.json']
    for fn in required:
        path=old/fn
        if not path.is_file() or fn not in manifest or sha256(path)!=manifest[fn]:
            # RUN_STATUS.json was written AFTER OUTPUT_SHA256.json in the
            # original StageWriter, so it is not in the old per-stage manifest.
            if fn=='RUN_STATUS.json' and path.is_file() and fn not in manifest:
                continue
            raise RuntimeError(f'UNVERIFIED_STAGE2_CACHE: {path}')
    status=read_json(old/'RUN_STATUS.json')
    if status.get('status')!='CODE_EXECUTION_PASS_NOT_SCIENTIFIC_VALIDATION':
        raise RuntimeError('cached Stage2 was not a completed technical PASS')
    original_check=read_json(old/'CHECKS.json')
    if not original_check or any(x.get('status')!='PASS' for x in original_check):
        raise RuntimeError('cached Stage2 CHECKS are missing/failed')
    df=pd.read_csv(old/'RESIDUALS.csv.gz',compression='gzip')
    cols={'case','route','bias','arm','sample','distance_bin','t_s','pose_id',
          'er_m','es','accepted_ab','Rrr','Rss'}
    if m:=cols-set(df.columns):raise RuntimeError(f'cached Stage2 missing fields {m}')
    if df.duplicated(['case','bias','arm','sample','pose_id']).any():
        raise RuntimeError('duplicate cache case/arm/population packet')
    fixed=[];provenance=[]
    # Key by exact original pose_id instead of relying on inferred integer
    # continuity or on the stored Stage-2 CSV sorting convention.
    contexts={(d.case['id'],d.bias):d for d in ctx.cases()}
    valid_pairs=set(contexts)
    cached_pairs=set(zip(df.case,df.bias))
    if cached_pairs!=valid_pairs:
        raise RuntimeError('cached and requested case/bias populations differ')
    native_cache={}
    for (caseid,bias),d in contexts.items():
        if caseid not in native_cache:
            sample=ctx.cfg.source_root/d.case['samples_path']
            original_lock=read_json(ctx.base/'e1_e4/INPUT_LOCK.json')
            rel=d.case['samples_path'].replace('\\','/')
            digest_candidates=[r['sha256'] for r in original_lock['files']
                               if r['path'].replace('\\','/').endswith('/'+rel)]
            if len(digest_candidates)!=1 or sha256(sample)!=digest_candidates[0]:
                raise RuntimeError(f'ORIGINAL_SAMPLE_SNAPSHOT_SHA256_MISMATCH: {sample}')
            ctx.verify_manifest_file(sample)
            source=read_json(sample)
            raw_ids=pd.DataFrame(source)['pose_id'].to_numpy()
            native_index=pd.Index(raw_ids)
            if native_index.has_duplicates:raise RuntimeError('duplicate native Full RF pose_id')
            native_cache[caseid]=native_index
        native_index=native_cache[caseid]
        raw_ix=native_index.get_indexer(d.ids)
        if np.any(raw_ix<0) or np.any(np.diff(raw_ix)<=0):
            raise RuntimeError(f'E1/native RF original order mismatch: {d.key}')
        align=pd.DataFrame({'pose_id':d.ids,'packet_index':np.arange(len(d.ids)),
                            'raw_sample_index':raw_ix,'reference_time':d.t,
                            'reference_accepted':d.mask})
        cut=df[(df.case==caseid)&(df.bias==bias)].drop(
            columns=['packet_index','raw_sample_index'],errors='ignore').merge(
            align,on='pose_id',how='left',validate='many_to_one')
        if cut.packet_index.isna().any() or cut.raw_sample_index.isna().any():
            raise RuntimeError(f'cached packet outside frozen E1: {d.key}')
        if len(cut)!=len(df[(df.case==caseid)&(df.bias==bias)]):
            raise RuntimeError('cached row count changed in alignment')
        cut.packet_index=cut.packet_index.astype(np.int64)
        cut.raw_sample_index=cut.raw_sample_index.astype(np.int64)
        writer.check(d.key+'_cached_times',cut.t_s,cut.reference_time,1e-10)
        writer.check(d.key+'_cached_accept',cut.accepted_ab.to_numpy(bool),
                     cut.reference_accepted.to_numpy(bool),0)
        for arm in ('BASE','EX','EXDS'):
            part=cut[(cut.arm==arm)&(cut['sample']=='all')]
            if len(part)!=len(d.t) or set(part.pose_id)!=set(d.ids):
                raise RuntimeError(f'cached full packet coverage incomplete {d.key}/{arm}')
            acc=cut[(cut.arm==arm)&(cut['sample']=='accepted_A_B')]
            if len(acc)!=int(d.mask.sum()) or not acc.accepted_ab.all():
                raise RuntimeError(f'cached accepted subset inconsistent {d.key}/{arm}')
        fixed.append(cut.drop(columns=['reference_time','reference_accepted']))
        provenance.append({'case':caseid,'bias':bias,'n_E1':len(d.t),
                           'n_native':len(native_index),'n_native_gaps':int(
                               np.maximum(np.diff(raw_ix)-1,0).sum()),
                           'SHA256_native_sample_id_manifest':ctx._verified[sample.resolve()]})
    full_df=pd.concat(fixed,ignore_index=True)
    expected_rows=len(df)
    if len(full_df)!=expected_rows:raise RuntimeError('cached residual rows changed')
    # The second copy is only for grouping `whole`; all pair alignment uses
    # the original, unchanged `whole/all` packet population.
    whole=full_df.copy();whole['distance_bin']='whole'
    summary=summary_residuals(pd.concat([full_df,whole],ignore_index=True),reps=300)
    if summary.empty:raise RuntimeError('empty statistics after cache alignment')
    full_df.to_csv(writer.dir/'RESIDUALS.csv.gz',index=False,
                   compression='gzip',float_format='%.16g')
    writer.csv('RESIDUAL_STATS.csv',summary)
    for fn in ('SOURCE_GT_DIAGNOSTICS.csv','MEASURED_FP_SHIFT_STRATA.csv'):
        writer.csv(fn,pd.read_csv(old/fn))
    writer.csv('CACHE_NATIVE_ALIGNMENT.csv',provenance)
    writer.json('CACHED_INPUT_IDENTITY.json',{'source_Stage2':str(old),
                 'old_manifest_sha256':sha256(old/'OUTPUT_SHA256.json'),
                 'old_residuals_sha256':sha256(old/'RESIDUALS.csv.gz'),
                 'raw_inputs_sha256_verified':True,
                 'mode':'DERIVED_FROM_VERIFIED_ORIGINAL_CACHE_NO_NEW_RF_EXTRACTION'})
    writer.finish({'statistics_revision':'packet-native-indexed ACF, fixed-origin 8/16/32 bootstrap',
                   'upstream':'old Stage2 RF measurement predictions reused byte-verifiably',
                   'new_physics_runs':0,'new_filter_runs':0,
                   'comparison':'Stage3 will use regenerated selected populations; original E1 frozen'})
