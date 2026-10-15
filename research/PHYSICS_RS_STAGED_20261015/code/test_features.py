import numpy as np
import pytest
from features import extract,FEATURES,C0
F=np.linspace(6250400000,6749600000,257)
def packet(a=(1,2j),delay=30e-9):
 return (np.exp(-2j*np.pi*F*delay)[:,None]*np.array(a)[None,:])[None,:,:]
def test_rank_one():
 o=extract(packet(),F)
 assert o['valid'][0]
 assert o['jones_diversity'][0]<1e-12
 assert o['freq_s_var'][0]<1e-24
 assert o['tap_pol_var80'][0]<1e-24
 assert o['eta_fp_win80'][0]<1e-12
 assert o['s_diff16'][0]<1e-12
 assert np.isclose(o['s_fp'][0],-.6)
def test_port_swap():
 rng=np.random.default_rng(7);h=packet()+.4*packet(a=(2,1j),delay=31.1e-9)
 a,b=extract(h,F),extract(h[:,:,::-1],F)
 for k in FEATURES:np.testing.assert_allclose(a[k],b[k],atol=1e-10,rtol=1e-10)
 assert np.isclose(a['s_fp'][0],-b['s_fp'][0])
def test_gain():
 h=packet()+.4*packet(a=(2,1j),delay=31.1e-9);a=extract(h,F)
 for scale in (1e-8,1e8):
  b=extract(h*scale,F)
  for k in FEATURES:
   if k!='log_fp_power':np.testing.assert_allclose(a[k],b[k],atol=1e-10,rtol=1e-10)
  np.testing.assert_allclose(b['log_fp_power'],a['log_fp_power']+2*np.log10(scale))
def test_unitary_jones():
 h=packet()+.6*packet(a=(2,1j),delay=31e-9)
 a=extract(h,F);theta=.714;u=np.array([[np.cos(theta),np.sin(theta)],[-np.sin(theta),np.cos(theta)]])
 b=extract(h@u.T,F)
 np.testing.assert_allclose(a['jones_diversity'],b['jones_diversity'],atol=1e-12)
def test_equal_delay_blindspot():
 h=packet();bad=h+packet(a=(-.8,1),delay=30e-9)
 a,b=extract(h,F),extract(bad,F)
 assert b['jones_diversity'][0]<1e-12
 assert b['tap_pol_var80'][0]<1e-24
 assert abs(a['s_fp'][0]-b['s_fp'][0])>.1
def test_small_delay_mix():
 h=packet()+.8*packet(a=(2,.1j),delay=30.7e-9)
 assert extract(h,F)['jones_diversity'][0]>1e-3
def test_zero_invalid():
 a=extract(np.zeros((1,257,2),complex),F)
 assert not a['valid'][0]
 assert all(np.isnan(a[k][0]) for k in FEATURES)
def test_nonfinite_refused():
 h=packet();h[0,1,0]=np.nan
 with pytest.raises(ValueError):extract(h,F)
def test_scalar_reference():
 h=packet()+.6*packet(a=(2,1j),delay=34e-9);o=extract(h,F)
 a=h[0];circ=np.fft.ifft(a*np.hanning(257)[:,None],n=1028,axis=0)*257
 branch=int(np.argmax(abs(circ).max(axis=0)));peak=max(abs(circ[:,branch]));k=next(i for i,v in enumerate(abs(circ[:,branch])) if v>=.3*peak)
 p=abs(circ)**2;v=(p[k,0]-p[k,1])/sum(p[k]);dt=1/(1028*(F[1]-F[0]))
 assert int(o['tap'][0])==k
 assert abs(o['s_fp'][0]-v)<1e-12
 assert abs(o['range_m'][0]-k*dt*C0)<1e-12
 q=p[k:k+80].sum(axis=1);w=q/sum(q);r=(p[k:k+80,0]-p[k:k+80,1])/q
 var=sum(float(wi*(ri-sum(w*r))**2) for wi,ri in zip(w,r))
 assert abs(o['tap_pol_var80'][0]-var)<1e-12
 c=sum(np.outer(vv,vv.conj()) for vv in a)
 ev=np.linalg.eigvalsh(c)
 assert abs(o['jones_diversity'][0]-ev[0]/sum(ev))<1e-12
