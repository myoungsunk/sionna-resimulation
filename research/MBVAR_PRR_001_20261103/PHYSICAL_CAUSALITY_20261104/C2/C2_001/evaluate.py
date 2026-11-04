"""Truth-only evaluator, separate from every filter/gate function."""
import numpy as np

INTERVALS = ((0.,2.),(2.,5.),(5.,10.),(10.,20.))


def score_states(x, P, truth):
    y = np.asarray(truth['truth'])
    e = x[...,:3]-y[:,None,:]
    e[...,2] = (e[...,2]+np.pi)%(2*np.pi)-np.pi
    C3,C2 = P[...,:3,:3],P[...,:2,:2]
    for matrix in (P,C3,C2):
        if not np.isfinite(matrix).all():raise ValueError('evaluation covariance nonfinite')
        np.linalg.cholesky(matrix)
    if not np.isfinite(e).all():raise ValueError('truth/state error nonfinite')
    nees3 = np.sum(e*np.linalg.solve(C3,e[...,None])[...,0],axis=-1)
    xy2 = np.sum(e[...,:2]*np.linalg.solve(C2,e[...,:2,None])[...,0],axis=-1)
    bg = truth.get('bg')
    available = bg is not None and np.asarray(bg).shape==() and np.isfinite(bg)
    if available:
        eb = x[...,3]-float(bg)
        e4 = np.concatenate([e,eb[...,None]],axis=-1)
        nees4 = np.sum(e4*np.linalg.solve(P,e4[...,None])[...,0],axis=-1)
        bg_error = np.abs(eb)
    else:
        nees4 = np.full(e.shape[:2],np.nan);bg_error = nees4.copy()
    sigma = np.sqrt(P[...,2,2])
    return dict(xy_m=np.linalg.norm(e[...,:2],axis=-1),heading_deg=np.abs(np.degrees(e[...,2])),
        bg_abs_rad_s=bg_error,NEES3=nees3,NEES4=nees4,NEES4_available=np.array(bool(available)),
        XY_mahalanobis2=xy2,heading68=np.abs(e[...,2])<=sigma,
        heading95=np.abs(e[...,2])<=1.959963984540054*sigma,XY95=xy2<=5.991464547107979,
        NEES3_upper95=nees3<=7.814727903251179,NEES4_upper95=nees4<=9.487729036781154,
        Ppsi_rad2=P[...,2,2].copy(),Pxy_trace_m2=np.trace(C2,axis1=-2,axis2=-1),
        Pbg_rad2_s2=P[...,3,3].copy())


def baseline_score(trace, truth):
    values = score_states(trace['x'][:,None],trace['P'][:,None],truth)
    return {key:(value[:,0] if value.ndim==2 else value) for key,value in values.items()}


def acf(values):
    result = []
    for lag in range(1,11):
        a,b = values[:-lag],values[lag:]
        if len(a)<2 or np.ptp(a)==0 or np.ptp(b)==0:
            result.append(None);continue
        a,b = a-a.mean(),b-b.mean();den = np.linalg.norm(a)*np.linalg.norm(b)
        result.append(float(a@b/den) if den else None)
    return result


def integral(t, values, start, left, right):
    mask = (t>=start+left-1e-9)&(t<=start+right+1e-9)
    times = t[mask]
    if len(times)<2 or abs(times[0]-start-left)>1e-9 or abs(times[-1]-start-right)>1e-9:
        return None
    return float(np.trapezoid(values[mask],times))


def primary(values, mask, available):
    result = {}
    for name in ('xy_m','heading_deg'):
        result[name+'_mean'] = float(values[name][mask].mean())
        result[name+'_rmse'] = float(np.sqrt(np.mean(values[name][mask]**2)))
    for name in ('NEES3','NEES4','heading68','heading95','XY95','NEES3_upper95','NEES4_upper95','Ppsi_rad2','Pxy_trace_m2','Pbg_rad2_s2','bg_abs_rad_s'):
        result[name+'_mean'] = None if not available and name in ('NEES4','NEES4_upper95','bg_abs_rad_s') else float(values[name][mask].mean())
    return result


def window_score(data, full_trace, baseline, truth, reference, window, route, bias, seed):
    """All oracle/GT accesses occur after the complete branch recursion."""
    start = int(data['first_index']);t = full_trace['t'];suffix_t = data['t']
    values = score_states(data['x'],data['P'],dict(truth=truth['truth'][start:],**({'bg':truth['bg']} if 'bg' in truth else {})))
    hg = reference['h'][start:]
    epsilon = data['z']-hg[:,None,:]-data['mu'][:,None,:]
    delta = hg[:,None,:]-data['h']
    residual = epsilon+delta-data['nu']
    if not np.all(np.abs(residual)<=1e-10+1e-10*np.abs(data['nu'])):
        raise ValueError('epsilon + delta_h innovation identity')
    values.update(epsilon=epsilon,delta_h=delta,identity_error=residual)
    active = np.arange(start,len(t))<=window['last_index']
    available = bool(values['NEES4_available'])
    primary_mask = t>=30.
    ff_primary = primary(baseline,primary_mask,available)
    rf = reference['physical_delta'][start:]
    rf_tap = reference['physical_delta_tap'][start:]
    summaries,blocks,diagnostics = [],[],[]
    def first(mask):
        indices = np.flatnonzero(active & mask)
        return (None,None) if not len(indices) else (int(data['pose_id'][indices[0]]),float(suffix_t[indices[0]]))
    for j,(mode,arm) in enumerate(zip(data['modes'],data['arms'])):
        summary = dict(route=route,bias=bias,seed=seed,window=window['id'],mode=str(mode),arm=str(arm),
            start_s=window['start_s'],end_s=window['end_s'],first_index=start,suffix_rows=len(suffix_t),
            primary_rows=int(primary_mask.sum()),NEES4_available=available,
            NEES4_unavailable_reason='' if available else 'source scalar gyro-bias truth unavailable',
            epsilon_identity_max=float(np.abs(residual[:,j]).max()))
        combined = {name:np.concatenate([baseline[name][:start],value[:,j]])
                    for name,value in values.items() if value.ndim==2 and name in baseline}
        current = primary(combined,primary_mask,available)
        for name,value in current.items():
            summary['primary_'+name] = value;summary['FF_primary_'+name] = ff_primary[name]
            summary['delta_primary_'+name] = None if value is None else value-ff_primary[name]
        for left,right in INTERVALS:
            label = f'{left:g}_{right:g}'
            for name,unit in (('heading_deg','deg_s'),('xy_m','m_s')):
                value = integral(suffix_t,values[name][:,j],window['start_s'],left,right)
                ff = integral(t,baseline[name],window['start_s'],left,right)
                key = 'I_'+name+'_'+label+'_'+unit
                summary[key] = value;summary['FF_'+key] = ff
                summary['delta_'+key] = None if value is None or ff is None else value-ff
                summary[key+'_available'] = value is not None and ff is not None
                subset=(suffix_t>=window['start_s']+left-1e-9)&(suffix_t<=window['start_s']+right+1e-9)
                summary[key+'_actual_packets'] = int(subset.sum())
                summary[key+'_unavailable_reason'] = '' if value is not None and ff is not None else 'complete interval endpoints unavailable; no partial integral'
        full_s = arm in ('LF','FF')
        bad_pose,bad_t = first(data['mask'][:,j] & (np.abs(rf[:,1])>.20) & full_s)
        shift_pose,shift_t = first(data['mask'][:,j] & (rf_tap!=0))
        summary.update(first_delivered_Full_s_bad_pose=bad_pose,first_delivered_Full_s_bad_t=bad_t,
                       first_original_RF_tap_change_accepted_pose=shift_pose,
                       first_original_RF_tap_change_accepted_t=shift_t,
                       gate_flips_all=int(np.sum(data['mask'][:,j]!=full_trace['mask'][start:])))
        diagnostics.append(dict(route=route,bias=bias,seed=seed,window=window['id'],mode=str(mode),arm=str(arm),
            epsilon_range_acf=acf(epsilon[active,j,0]),epsilon_s_acf=acf(epsilon[active,j,1]),
            physical_range_acf=acf(rf[active,0]),physical_s_acf=acf(rf[active,1])))
        for kind,key in (('time_1s','time_bin'),('distance_0p2m','distance_bin')):
            labels = reference[key][start:]
            for label in np.unique(labels[active]):
                selected = active & (labels==label)
                blocks.append(dict(route=route,bias=bias,seed=seed,window=window['id'],mode=str(mode),arm=str(arm),
                    block_kind=kind,block_id=int(label),n=int(selected.sum()),
                    mean_original_eMP_range_m=float(rf[selected,0].mean()),
                    mean_original_eMP_s=float(rf[selected,1].mean()),
                    mean_delivered_eMP_range_m=0. if arm in ('LF','LL') else float(rf[selected,0].mean()),
                    mean_delivered_eMP_s=0. if arm in ('FL','LL') else float(rf[selected,1].mean()),
                    mean_epsilon_range_m=float(epsilon[selected,j,0].mean()),mean_epsilon_s=float(epsilon[selected,j,1].mean()),
                    mean_heading_deg=float(values['heading_deg'][selected,j].mean()),mean_xy_m=float(values['xy_m'][selected,j].mean()),
                    mean_delta_heading_vs_FF=float((values['heading_deg'][:,j]-baseline['heading_deg'][start:])[selected].mean()),
                    mean_delta_xy_vs_FF=float((values['xy_m'][:,j]-baseline['xy_m'][start:])[selected].mean()),
                    mean_Ppsi_rad2=float(data['P'][selected,j,2,2].mean()),accepted_fraction=float(data['mask'][selected,j].mean())))
        summaries.append(summary)
    paired = [key for key in summaries[0] if (key.startswith('primary_') and key!='primary_rows')
              or (key.startswith('I_') and key.endswith(('deg_s','m_s')))]
    for summary in summaries:
        for key in paired:summary['own_minus_fixed_'+key] = None
    fixed = {row['arm']:row for row in summaries if row['mode']=='fixed'}
    for row in summaries:
        if row['mode']=='own':
            for key in paired:
                a,b = row[key],fixed[row['arm']][key]
                row['own_minus_fixed_'+key] = None if a is None or b is None else a-b
    values.update(pose_id=data['pose_id'],t=suffix_t,modes=data['modes'],arms=data['arms'])
    return values,summaries,blocks,diagnostics
