"""S2 mean feature extension with explicitly approved distance covariance bins."""
import json
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from n4b_rf_errors import row_cov,fix_cov

ARMS=['Q_POWER1','DIST_ONLY','GEOM','GEOM_Q']
FEATURES=['log10_d','log10_d_squared','cos_theta','sin_theta','cos_2theta','sin_2theta','mount_deg_over45','anchor_x_over10','anchor_y_over10','anchor_z_over10']

def geometry(states,case):
    states=np.atleast_2d(states);a=np.asarray(case['anchor'],float)
    dx=a[0]-states[:,0];dy=a[1]-states[:,1]
    d=np.sqrt(dx*dx+dy*dy+(a[2]-case['robot_z_m'])**2)
    theta=(np.arctan2(dy,dx)-states[:,2]-np.radians(case['mount_deg'])+np.pi)%(2*np.pi)-np.pi
    logd=np.log10(np.maximum(d,1e-6))
    X=np.column_stack([logd,logd**2,np.cos(theta),np.sin(theta),np.cos(2*theta),np.sin(2*theta),np.full(len(d),case['mount_deg']/45),*[np.full(len(d),v/10) for v in a]])
    return d,theta,X

def frame_features(frame,cases):
    d=np.empty(len(frame));X=np.empty((len(frame),10));ids=frame.case.to_numpy()
    for cid in np.unique(ids):
        ix=np.flatnonzero(ids==cid)
        d[ix],_,X[ix]=geometry(frame.iloc[ix][['x_eval','y_eval','yaw_rad']].to_numpy(),cases[cid])
    return d,X

def inputs(arm,q,d,X):
    q=np.atleast_1d(q);d=np.atleast_1d(d)
    if arm=='Q_POWER1':return q[:,None],q
    if arm=='DIST_ONLY':return d[:,None],d
    if arm=='GEOM':return np.atleast_2d(X),d
    if arm=='GEOM_Q':return np.column_stack([np.atleast_2d(X),q]),d
    raise ValueError('UNKNOWN_ARM:'+arm)

class PowerModel:
    def __init__(self,record):self.record=record
    @classmethod
    def fit(cls,X,bin_values,Y,w,arm,key_hash):
        X=np.asarray(X,float);w=np.asarray(w,float);Y=np.asarray(Y,float)
        if not np.isfinite(X).all() or not np.isfinite(bin_values).all():raise ValueError('NONFINITE_TRAIN_FEATURE')
        scaler=StandardScaler();A=scaler.fit_transform(X)
        ridge=Ridge(alpha=30.,fit_intercept=True).fit(A,Y,sample_weight=w)
        residual=Y-ridge.predict(A);global_mu,global_cov=row_cov(np,residual,w);global_cov=fix_cov(np,global_cov,True)
        cuts=np.unique(np.quantile(bin_values,[1/3,2/3]));bins=np.searchsorted(cuts,bin_values,side='right')
        offsets=[];covs=[];stats=[]
        for b in range(len(cuts)+1):
            tr=bins==b;n=int(tr.sum())
            if n<15:raise RuntimeError('BAD_STRATA_SIZE:'+arm+':'+str(b)+':'+str(n))
            raw_mu,raw_cov=row_cov(np,residual[tr],w[tr]);effective_w=(w[tr].sum()**2)/(w[tr]**2).sum();alpha=effective_w/(effective_w+100.)
            mean=alpha*raw_mu+(1-alpha)*global_mu;C=fix_cov(np,alpha*raw_cov+(1-alpha)*global_cov,True)
            offsets.append(mean.tolist());covs.append(C.tolist());stats.append(dict(bin=b,n_train=n,effective_w=float(effective_w),alpha=float(alpha)))
        record=dict(arm=arm,feature_names=['q'] if arm=='Q_POWER1' else ['d_3D_m'] if arm=='DIST_ONLY' else FEATURES+(['q'] if arm=='GEOM_Q' else []),bin_feature='q' if arm=='Q_POWER1' else 'd_3D_m',
                    scaler_mean=scaler.mean_.tolist(),scaler_scale=scaler.scale_.tolist(),ridge_coef=ridge.coef_.tolist(),ridge_intercept=ridge.intercept_.tolist(),cuts=cuts.tolist(),offsets=offsets,covs=covs,bin_stats=stats,training_key_sha256=key_hash,alpha=30.)
        obj=cls(record);mu,C=obj.predict(X,bin_values)
        expected=ridge.predict(A)+np.asarray(offsets)[bins]
        if abs(mu-expected).max()>1e-12:raise RuntimeError('SERIALIZED_LINEAR_PREDICTION_MISMATCH')
        return obj
    def predict(self,X,bin_values):
        r=self.record;X=np.atleast_2d(X);bins=np.searchsorted(r['cuts'],np.atleast_1d(bin_values),side='right')
        A=(X-np.asarray(r['scaler_mean']))/np.asarray(r['scaler_scale'])
        mu=A@np.asarray(r['ridge_coef']).T+np.asarray(r['ridge_intercept'])+np.asarray(r['offsets'])[bins]
        C=np.asarray(r['covs'])[bins]
        if not np.isfinite(mu).all() or not np.isfinite(C).all():raise FloatingPointError('NONFINITE_MODEL_PREDICTION')
        return mu,C
