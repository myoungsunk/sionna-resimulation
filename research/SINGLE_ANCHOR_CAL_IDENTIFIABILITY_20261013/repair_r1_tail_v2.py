"""Analytic DR evidence lower bound and posterior tail enclosure; no quadrature denominator."""
import math
import numpy as np
import mpmath as mp


def tail_certificate(public, cfg, center_z, bound, halfwidth=1e-4, digits=50):
    if bound<=0 or halfwidth<=0: raise ValueError('positive bound and width required')
    if np.asarray(center_z).shape!=(3,) or not np.all(np.isfinite(center_z)): raise ValueError('finite center required')
    iv=mp.iv; old=iv.dps; iv.dps=digits
    try:
        point=lambda x:iv.mpf(float(x))
        z=[iv.mpf([float(v-halfwidth),float(v+halfwidth)]) for v in center_z]
        std=[point(v) for v in cfg['p0_std'][3:]]
        bg,sf,eps=[z[i]*std[i] for i in range(3)]
        den=1+sf;level=1-eps**2/4
        if float(den.a)<=0 or float(level.a)<=0:raise ValueError('lower-evidence box crosses invalid support')
        ratio=level/den;b=point(cfg['wheel_base']);lp=-sum(v**2 for v in z)/2-3*iv.log(2*iv.pi)/2
        upper=iv.mpf(0)
        for k in range(1,len(public['t_s'])):
            dt,d,g,o=[point(public[key][k]) for key in ('dt_s','ds_odom','dtheta_gyro','dtheta_odom')]
            qd=point(cfg['k_s'])*abs(d);qg=point(cfg['gyro_N_rad_sqrt_s'])**2*dt
            qo=point(cfg['k_theta'])*abs(o)+point(cfg['k_stheta'])*abs(d)
            if float(qo.a)<=0:raise ValueError('positive qo required for this global bound')
            s=(eps/b)**2*qd+ratio**2*qg+qo
            resid=o-(ratio*(g-bg*dt)+eps*d/b)
            lp-= (iv.log(2*iv.pi*s)+resid**2/s)/2
            upper-=iv.log(2*iv.pi*qo)/2
        volume=iv.mpf(1)
        for v in z: volume*=v.b-v.a
        lower=lp+iv.log(volume)
        lower_float=float(np.nextafter(float(lower.a),-np.inf))
        bnd=point(bound)
        logprior=iv.log(4)-bnd**2/2-iv.log(bnd)-iv.log(2*iv.pi)/2
        logtail=logprior+upper-point(lower_float)
        logtail_float=float(np.nextafter(float(logtail.b),np.inf))
        probability=float(np.nextafter(float(iv.exp(point(min(0,logtail_float))).b),np.inf))
        return dict(bound=bound,halfwidth=halfwidth,center_z=list(map(float,center_z)),digits=digits,
                    log_evidence_lower_bound=lower_float,log_likelihood_upper_bound=float(np.nextafter(float(upper.b),np.inf)),
                    log_posterior_tail_upper_bound=min(0.,logtail_float),posterior_tail_upper_bound=min(1.,probability),
                    method='interval lower-density times exact box volume; global likelihood upper; Mills union tail; no numerical evidence denominator',
                    scope='conditional measured-input DR target; bg integrated over full real line, outside box concerns SF/eps only')
    finally:iv.dps=old
