"""C0-B amended diagnostics, zero counterfactual reported undefined; channel axes are frequency, RX+45/-45."""
import csv
import json
from pathlib import Path

import numpy as np


def cir(h):
    field = np.asarray(h, dtype=np.complex128)
    assert field.shape[-2:] == (257, 2)
    return np.fft.ifft(field * np.hanning(257)[:, None], n=1028, axis=-2) * 257


def signed(v):
    p = np.abs(v)**2
    den = float(p.sum())
    return (float((p[0]-p[1])/den) if den > 0 else None), den, p.tolist()


def detect(c, df):
    mag = abs(c)
    rx = int(mag.max(axis=0).argmax())
    peak = float(mag[:, rx].max())
    if peak <= 0:
        raise ValueError('undetectable all-zero composite')
    tap = int(np.flatnonzero(mag[:, rx] >= .3 * peak)[0])
    s, den, power = signed(c[tap])
    return dict(tap=tap, rx=rx, peak=peak, leading_edge=.3*peak, range_m=tap*299792458./(1028*df),
                s=s, denominator=den, power=power)


def counterfactual_detect(c, df):
    if not np.isfinite(c).all():
        raise ValueError('nonfinite counterfactual CIR')
    if np.max(abs(c)) == 0:
        return dict(tap=None,s=None,undefined_reason='ZERO_COMPOSITE')
    return detect(c, df)


def decomposition(full, los, df):
    cf, cl = cir(full), cir(los)
    F, L = detect(cf, df), detect(cl, df)
    same, den, _ = signed(cf[L['tap']])
    if same is None:
        raise ValueError('zero power at fixed tap')
    fixed = same-L['s']
    choice = F['s']-same
    error = F['s']-L['s']
    assert abs(error-fixed-choice) <= 1e-12
    return dict(full=F, los=L, delta_tap=F['tap']-L['tap'], delta_range_m=F['range_m']-L['range_m'],
                full_at_los_tap_s=same, full_at_los_tap_denominator=den,
                same_los_tap=fixed, detector_choice=choice, e_mp=error, identity_error=abs(error-fixed-choice))


def evaluate(folder, freq, fields, labels, direct, native_full, archive_full, archive_los):
    """fields[group,frequency,rx] contains coherent per-group spectra with missing bins zero."""
    folder=Path(folder)
    folder.mkdir(parents=True,exist_ok=True)
    assert len(labels)==len(set(labels))==len(fields)
    if 'INVALID' in labels and np.any(fields[list(labels).index('INVALID')]):
        raise ValueError('nonzero field from invalid solver path')
    df=float(freq[1]-freq[0])
    group_cir=cir(fields)
    full=cir(native_full)
    d=group_cir[direct]
    native=decomposition(native_full,fields[direct],df)
    archive=decomposition(archive_full,archive_los,df)
    summary=dict(native=native,archive=archive,zero_denominator_floor=0.,treatment='remove complete group spectrum',rx_order=['+45','-45'])
    rows=[]
    windows={}
    for tap_name,tap in [('fpFull',native['full']['tap']),('fpLoS',native['los']['tap'])]:
        off=np.arange(-4,5)
        idx=(tap+off)%len(full)
        windows[tap_name+'_bins']=idx
        for n,c in [('full',full),('direct',d),('archive_full',cir(archive_full)),('archive_los',cir(archive_los))]:
            windows[tap_name+'_'+n]=c[idx]
        V=group_cir[:,tap,:]
        Q=np.delete(V,direct,axis=0).sum(axis=0)
        baseline,_,_=signed(full[tap])
        allocated=np.zeros(2)
        for group,label in enumerate(labels):
            if group==direct or label=='INVALID':
                continue
            v=V[group]
            removed=full-group_cir[group]
            fixed,den,power=signed(removed[tap])
            nd=counterfactual_detect(removed,df)
            shapley=2*np.real(d[tap].conj()*v)+np.real(v.conj()*Q)
            allocated+=shapley
            rows.append(dict(group_id=label,tap_ref=tap_name,tap=tap,removed_s_fixed=fixed,
                             delta_s_fixed=None if fixed is None else baseline-fixed,removed_denominator=den,
                             removed_plus_power=power[0],removed_minus_power=power[1],
                             removed_detected_tap=nd['tap'],removed_s_redetected=nd['s'],
                             delta_s_redetected=None if nd['s'] is None else native['full']['s']-nd['s'],
                             shapley_plus=shapley[0],shapley_minus=shapley[1]))
        gap=allocated-(abs(full[tap])**2-abs(d[tap])**2)
        summary[tap_name+'_allocation_residual']=gap.tolist()
        if not np.allclose(allocated,abs(full[tap])**2-abs(d[tap])**2,atol=1e-14,rtol=1e-8):
            raise ValueError('coherent power closure')
    (folder/'detector.json').write_text(json.dumps(summary,indent=2,allow_nan=False),encoding='utf8')
    with (folder/'attribution.csv').open('w',newline='',encoding='utf8') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    np.savez_compressed(folder/'tap_windows.npz',**windows)

    # Removing every chain touching a surface is a separate counterfactual.
    surface_groups={}
    for i,label in enumerate(labels):
        if i!=direct and label!='INVALID':
            for surface in {v[0] for v in json.loads(label)}:
                surface_groups.setdefault(surface,[]).append(i)
    surface_rows=[]
    for surface,indices in sorted(surface_groups.items()):
        removed=full-group_cir[indices].sum(axis=0)
        changed=counterfactual_detect(removed,df)
        for tap_name,tap in [('fpFull',native['full']['tap']),('fpLoS',native['los']['tap'])]:
            fixed,den,power=signed(removed[tap])
            baseline,_,_=signed(full[tap])
            surface_rows.append(dict(surface=surface,removed_group_count=len(indices),
                                     tap_ref=tap_name,tap=tap,s_removed_fixed=fixed,
                                     delta_s_fixed=None if fixed is None else baseline-fixed,
                                     removed_denominator=den,removed_plus_power=power[0],removed_minus_power=power[1],
                                     removed_detected_tap=changed['tap'],s_removed_redetected=changed['s'],
                                     delta_s_redetected=None if changed['s'] is None else native['full']['s']-changed['s']))
    with (folder/'surface_removal.csv').open('w',newline='',encoding='utf8') as f:
        writer=csv.DictWriter(f,fieldnames=list(surface_rows[0]))
        writer.writeheader()
        writer.writerows(surface_rows)
    return summary
