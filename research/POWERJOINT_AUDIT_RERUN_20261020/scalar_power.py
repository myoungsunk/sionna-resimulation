"""Serializable scalar version of the unchanged P1 Ridge/tertile covariance fitter."""
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from n4b_rf_errors import fit_model
class ScalarPower:
 def __init__(self,train,q,weights,groups):
  frame=train.copy();frame['log_fp_power']=q
  self.scaler=StandardScaler().fit(np.asarray(q)[:,None]);self.ridge=Ridge(alpha=30.,fit_intercept=True).fit(self.scaler.transform(np.asarray(q)[:,None]),frame[['e_r','e_s']].to_numpy(),sample_weight=weights)
  mu,C,info=fit_model(np,frame,frame,weights,'POWER_BIN_JOINT',groups)
  self.cuts=np.asarray(info['cutpoints_train']);self.offsets=[];self.covs=[]
  linear=self.ridge.predict(self.scaler.transform(np.asarray(q)[:,None]));bins=np.searchsorted(self.cuts,q,side='right')
  for b in range(len(self.cuts)+1):
   ix=np.flatnonzero(bins==b)[0];self.offsets.append(mu[ix]-linear[ix]);self.covs.append(C[ix])
  self.offsets=np.asarray(self.offsets);self.covs=np.asarray(self.covs);self.info=info
  got,cov=self.predict(q)
  if max(abs(got-mu).max(),abs(cov-C).max())>1e-12:raise RuntimeError('SCALAR_FITTER_PARITY')
 def predict(self,q):
  q=np.atleast_1d(q);b=np.searchsorted(self.cuts,q,side='right')
  return self.ridge.predict(self.scaler.transform(q[:,None]))+self.offsets[b],self.covs[b]
