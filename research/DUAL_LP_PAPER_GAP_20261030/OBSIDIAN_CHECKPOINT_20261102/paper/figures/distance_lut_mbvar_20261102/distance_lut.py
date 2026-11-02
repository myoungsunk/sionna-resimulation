"""Distance correction on the frozen 2deg scalar grid, with the same pole chart.

Only analytic synthetic grid geometry and verified FFD banks build nodes.
No RF, truth, donor or filter result is used to fit or select nodes.
The table is sparse/lazy for cost only: each key has one deterministic value.
"""
import numpy as np
from p0_initial import direct, O
from p3_rf_adapter4 import FrozenLut
from pole_regularized_lut import PoleRegularizedLut


class CorrectedArray:
    def __init__(self, original, banks, height=2.2, enabled=True):
        self.original=original; self.banks=banks; self.height=height
        self.enabled=enabled; self.cache={}; self.shape=original.shape

    def raw(self, keys, override=None):
        """Independent direct-spectrum evaluation at synthetic table nodes."""
        keys=np.asarray(keys,int).reshape(-1,3)
        theta=2.*keys[:,0]; alpha=180.-2.*keys[:,1]
        rx=-180.+2.*keys[:,2]; psi=alpha+180.-rx
        assert np.all(theta<90), 'DISTANCE_TABLE_NO_90DEG_NODE'
        rho=self.height*np.tan(np.radians(theta))
        xyz=np.column_stack([rho*np.cos(np.radians(alpha)),rho*np.sin(np.radians(alpha)),np.zeros(len(keys))])
        anchor=np.array([0.,0.,self.height])
        h=direct(self.banks,xyz,psi,anchor,dist_override=override)
        return O.observe(h,self.banks[0].freqs_hz,None,None)['s']

    def ensure(self, keys):
        missing=sorted(set(map(tuple,np.asarray(keys,int).reshape(-1,3)))-self.cache.keys())
        for start in range(0,len(missing),96):
            ks=missing[start:start+96]
            s=self.raw(ks); s10=self.raw(ks,10.)
            delta=s-s10
            assert np.isfinite(delta).all()
            for key,a,b,c in zip(ks,delta,s,s10):self.cache[key]=(float(a),float(b),float(c))

    def __getitem__(self, index):
        if not self.enabled:return self.original[index]
        aa=np.broadcast_arrays(*[np.asarray(v,int) for v in index])
        keys=np.stack([x.ravel() for x in aa],axis=1)
        self.ensure(keys)
        delta=np.array([self.cache[tuple(k)][0] for k in keys]).reshape(aa[0].shape)
        return self.original[index]+delta

    def save(self,path):
        keys=sorted(self.cache)
        np.savez_compressed(path,keys=np.asarray(keys,int),delta_s=np.asarray([self.cache[k][0] for k in keys]),s_actual=np.asarray([self.cache[k][1] for k in keys]),s_10m=np.asarray([self.cache[k][2] for k in keys]),height_m=self.height,grid_deg=2.)


class DistanceBase(FrozenLut):
    def __init__(self,base,banks,height=2.2,enabled=True):
        self.__dict__.update(base.__dict__)
        self.s=CorrectedArray(base.s,banks,height,enabled)


class DistanceLut:
    def __init__(self,base,banks,height=2.2,enabled=True):
        self.height=height
        self.base=DistanceBase(base,banks,height,enabled)
        self.lut=PoleRegularizedLut(self.base)

    def model(self,x,case):
        height=case['anchor'][2]-case['robot_z_m']
        assert abs(height-self.height)<1e-12 and case['mount_deg']==0
        theta=np.degrees(np.arctan2(np.linalg.norm(np.asarray(x)[:2]-case['anchor'][:2]),height))
        assert theta<88., 'OUTSIDE_DECLARED_DISTANCE_TABLE_DOMAIN'
        return self.lut.model(x,case)

    def batch(self,states,case):
        pairs=[self.model(x,case) for x in states]
        return np.stack([v[0] for v in pairs]),np.stack([v[1] for v in pairs])
