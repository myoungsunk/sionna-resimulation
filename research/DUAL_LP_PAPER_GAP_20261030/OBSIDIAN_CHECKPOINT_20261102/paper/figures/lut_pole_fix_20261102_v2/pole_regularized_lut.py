"""LUT-only Cartesian pole cap; original 10m scalar LUT unchanged at theta>=2deg.

Fit a quadratic Cartesian scalar chart to frozen 2deg and 4deg rings.
No RF observations, truth states, SourceFFD predictions or run scores are used.
Inner/outer radii 1/2deg are fixed from the original angular grid before replay.
"""
import numpy as np

class PoleRegularizedLut:
    def __init__(self,base,enabled=True):
        self.base=base;self.enabled=enabled
        self.inner=1.;self.outer=2.;self.scale=np.tan(np.radians(2.))
        # alpha=global horizontal bearing, psi=tag heading + mount.
        # Original geometry gives phi_tx=-alpha, phi_rx=alpha+180-psi.
        self.psi=np.arange(-180.,180.,2.)
        alpha=np.arange(-180.,180.,2.)
        tx=np.rint(((-alpha+180)%360)/2).astype(int)
        rx=np.rint(((alpha[:,None]+180-self.psi[None]+180)%360)/2).astype(int)
        designs=[];values=[]
        for index,theta in [(1,2.),(2,4.)]:
            radius=np.tan(np.radians(theta))/self.scale
            qx=radius*np.cos(np.radians(alpha));qy=radius*np.sin(np.radians(alpha))
            designs.append(np.column_stack([np.ones(len(alpha)),qx,qy,qx*qx,qx*qy,qy*qy]))
            values.append(np.asarray(base.s[index,tx[:,None],rx],float))
        design=np.vstack(designs);value=np.vstack(values)
        self.coeff=np.linalg.lstsq(design,value,rcond=None)[0]
        assert np.linalg.matrix_rank(design)==6 and np.isfinite(self.coeff).all()
        self.fit_residual=value-design@self.coeff

    def _cap(self,x,case):
        height=case['anchor'][2]-case['robot_z_m']
        length=height*self.scale
        qx=(x[0]-case['anchor'][0])/length;qy=(x[1]-case['anchor'][1])/length
        psi=np.degrees(x[2])+case['mount_deg']
        pos=((psi+180)%360)/2;i=int(np.floor(pos));w=pos-i
        c=(1-w)*self.coeff[:,i]+w*self.coeff[:,(i+1)%180]
        dc=(self.coeff[:,(i+1)%180]-self.coeff[:,i])/(2*np.pi/180)
        terms=np.array([1.,qx,qy,qx*qx,qx*qy,qy*qy])
        s=float(terms@c)
        g=np.zeros(len(x));g[0]=(c[1]+2*c[3]*qx+c[4]*qy)/length
        g[1]=(c[2]+c[4]*qx+2*c[5]*qy)/length;g[2]=terms@dc
        return s,g

    def model(self,x,case):
        x=np.asarray(x,float)
        if not self.enabled:return self.base.model(x,case)
        u=x[0]-case['anchor'][0];v=x[1]-case['anchor'][1]
        height=case['anchor'][2]-case['robot_z_m'];rho=np.sqrt(u*u+v*v)
        theta=np.degrees(np.arctan2(rho,height))
        if theta>=self.outer:return self.base.model(x,case)
        cap,gcap=self._cap(x,case)
        distance=np.sqrt(u*u+v*v+height*height)
        # Original range row and offset are obtained unchanged from original adapter.
        h,H=self.base.model(x,case)
        if theta<=self.inner:
            h[1]=cap;H[1]=gcap
            return h,H
        z=(theta-self.inner)/(self.outer-self.inner)
        w=6*z**5-15*z**4+10*z**3
        dw=(30*z**4-60*z**3+30*z**2)/(self.outer-self.inner)
        dtheta=np.zeros(len(x));dtheta[:2]=height/(rho*rho+height*height)*np.array([u,v])/rho*180/np.pi
        # Continue the NORMAL theta=2..4deg cell downwards. Never blend the
        # contaminated original theta=0 ring back into the repaired region.
        tx=np.degrees(np.arctan2(-v,u))
        rx=(np.degrees(np.arctan2(-v,-u))-np.degrees(x[2])-case['mount_deg']+180)%360-180
        s2,g2=self.base(2.,tx,rx);s4,g4=self.base(4.,tx,rx)
        original=s2+(theta-2)*(s4-s2)/2
        gt=(s4-s2)/2;ga=g2[1]+(theta-2)*(g4[1]-g2[1])/2;gb=g2[2]+(theta-2)*(g4[2]-g2[2])/2
        k=180/np.pi;gold=gt*dtheta
        gold[0]+=(ga-gb)*v/(rho*rho)*k
        gold[1]+=(-ga+gb)*u/(rho*rho)*k
        gold[2]+=-gb*k
        h[1]=(1-w)*cap+w*original
        H[1]=(1-w)*gcap+w*gold+(original-cap)*dw*dtheta
        assert np.isfinite(h).all() and np.isfinite(H).all()
        return h,H

    def batch(self,states,case):
        pairs=[self.model(x,case) for x in np.asarray(states)]
        return np.stack([v[0] for v in pairs]),np.stack([v[1] for v in pairs])
