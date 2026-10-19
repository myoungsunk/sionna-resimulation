"""Pure numerical primitives for temporal RF error hypotheses.
No file, network, repository or environment access in this module.
"""
import numpy as np

def wrap(a):
    return (np.asarray(a)+np.pi)%(2*np.pi)-np.pi

def update(x,P,z,h,H,R,gate=9.210340371976184,force=None):
    nu=z-h
    S=H@P@H.T+R
    K=np.linalg.solve(S,H@P).T
    nis=float(nu@np.linalg.solve(S,nu))
    accepted=(nis<=gate) if force is None else bool(force)
    dx=K@nu
    y=x.copy();C=P.copy()
    if accepted:
        y=x+dx;y[2]=wrap(y[2])
        A=np.eye(len(x))-K@H
        C=A@P@A.T+K@R@K.T
        C=(C+C.T)*.5
    return y,C,dict(nis=nis,accepted=accepted,K=K,innovation=nu,S=S,proposal=dx)

def error_map(R,f,which='both'):
    """B B^T + Reps = R, preserving total one-packet variance."""
    if not 0<=f<1:raise ValueError('fraction outside [0,1)')
    B=np.zeros((2,2))
    if which=='both':B=np.sqrt(f)*np.linalg.cholesky(R)
    elif which=='r':B[0,0]=np.sqrt(f*(R[0,0]-R[0,1]**2/R[1,1]))
    elif which=='s':B[1,1]=np.sqrt(f*(R[1,1]-R[0,1]**2/R[0,0]))
    elif which!='none':raise ValueError(which)
    E=R-B@B.T
    if np.min(np.linalg.eigvalsh(E))<=0:raise ValueError('nonpositive white error covariance')
    return B,E

def augment(x,P):
    y=np.r_[x,np.zeros(2)]
    C=np.zeros((6,6));C[:4,:4]=P;C[4:,4:]=np.eye(2)
    return y,C

def predict_aug(x,P,ds,gyro,dt,a,transition):
    y,F,G=transition(x[:4],float(ds),float(gyro),float(dt))
    q=np.diag([2e-5*abs(ds),np.radians(.015)**2*dt,0.])
    J=np.zeros((6,6));J[:4,:4]=F;J[4:,4:]=np.eye(2)*a
    Q=np.zeros((6,6));Q[:4,:4]=G@q@G.T;Q[4:,4:]=np.eye(2)*(1-a*a)
    C=J@P@J.T+Q
    return np.r_[y,a*x[4:]],(C+C.T)*.5

def unit_tests():
    rng=np.random.default_rng(20261019);errors=[]
    for _ in range(100):
        L=rng.normal(size=(4,4));P=L@L.T*.01+np.eye(4)*.001
        A=rng.normal(size=(2,2));R=A@A.T*.002+np.eye(2)*.001
        x=rng.normal(size=4)*.05;H=rng.normal(size=(2,4));h=H@x;z=h+rng.normal(size=2)*.05
        y,C,_=update(x,P,z,h,H,R,force=True)
        for f in [0.,.2,.8]:
            xx,PP=augment(x,P);B,E=error_map(R,f)
            yy,CC,_=update(xx,PP,z,h,np.column_stack([H,B]),E,force=True)
            errors.append(max(abs(yy[:4]-y).max(),abs(CC[:4,:4]-C).max()))
    maximum=float(max(errors))
    if maximum>1e-10:raise AssertionError('Memoryless augmentation not marginally equivalent')
    # Finite-horizon covariance with constant shared bias versus independent bias.
    n=100;f=.8;v=1.;truth_variance=f*v+(1-f)*v/n;naive_variance=v/n
    return {'memoryless_equivalence_max':maximum,'linear_trials':300,'shared_bias_mean_variance':truth_variance,'independent_mean_variance':naive_variance}

if __name__=='__main__':
    import json
    print(json.dumps(unit_tests(),indent=2))
