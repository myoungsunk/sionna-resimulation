"""Batch the existing air-only Maxwell interface linear solve over frequency."""
import numpy as np

def reflection_operators(path,frequencies,epsilon):
    if 'T' in path['choices']:raise ValueError('AIR_REFLECTIONS_ONLY')
    f=np.asarray(frequencies,float);k=np.array(path['launch_direction'],float);op=np.broadcast_to(np.eye(3)-np.outer(k,k),(len(f),3,3)).astype(complex).copy();position=np.asarray(path['points'][0])
    for e in path['events']:
        if e['branch']!='R' or e['from_material']!='air':raise ValueError('AIR_REFLECTIONS_ONLY')
        op*=np.exp(-2j*np.pi*f/299792458.*(k@(e['point']-position)))[:,None,None]
        n=np.asarray(e['normal'],float);n/=np.linalg.norm(n);kn=k@n
        if kn<=1e-12:raise ValueError('INCIDENT_DIRECTION_OR_GRAZING')
        kr=k-2*kn*n
        if e.get('ideal') and e['ideal_epsilon'] is None:
            op=np.einsum('ab,fbc->fac',-np.eye(3)+2*np.outer(n,n),op)
        else:
            ep=np.array([e['ideal_epsilon'] if e.get('ideal') else epsilon(e['to_material'],x) for x in f],complex)
            if not np.isfinite(ep).all() or np.any(ep.imag>0):raise ValueError('PASSIVE_EPSILON_REQUIRED')
            tangent=k-kn*n;qt=np.sqrt(ep-tangent@tangent);qt=np.where((qt.imag>0)|((qt.imag==0)&(qt.real<0)),-qt,qt);kt=tangent[None]+qt[:,None]*n
            u=np.cross(n,np.eye(3)[np.argmin(abs(n))]);u/=np.linalg.norm(u);v=np.cross(n,u);proj=np.array([u,v])
            def modes(w):
                s=np.cross(n,w);norm=np.linalg.norm(s,axis=-1,keepdims=True);s=np.where(norm<1e-12,u,s);s/=np.linalg.norm(s,axis=-1,keepdims=True);p=np.cross(w,s);p/=np.linalg.norm(p,axis=-1,keepdims=True);return np.stack((s,p),axis=-1)
            er=modes(kr);et=modes(kt);hr=np.cross(kr,er.T).T;ht=np.swapaxes(np.cross(kt[:,None,:],np.swapaxes(et,-1,-2)),-1,-2)
            top=np.concatenate((np.broadcast_to(proj@er,(len(f),2,2)),-np.einsum('ab,fbc->fac',proj,et)),axis=2)
            bottom=np.concatenate((np.broadcast_to(proj@hr,(len(f),2,2)),-np.einsum('ab,fbc->fac',proj,ht)),axis=2)
            matrix=np.concatenate((top,bottom),axis=1)
            if np.any(np.linalg.cond(matrix)>1e12):raise ValueError('SINGULAR_VECTOR_INTERFACE')
            hi=np.swapaxes(np.cross(k,np.swapaxes(op,-1,-2)),-1,-2)
            rhs=-np.concatenate((np.einsum('ab,fbc->fac',proj,op),np.einsum('ab,fbc->fac',proj,hi)),axis=1)
            coefficients=np.linalg.solve(matrix,rhs);op=np.einsum('ab,fbc->fac',er,coefficients[:,:2,:])
        position=e['point'];k=kr
    op*=np.exp(-2j*np.pi*f/299792458.*(k@(np.array(path['points'][-1])-position)))[:,None,None]
    if not np.isfinite(op).all():raise ValueError('NONFINITE_OPERATOR')
    return op
