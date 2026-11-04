"""Independent Markov branches of the frozen MB_VAR. No truth arguments."""
import math
import numpy as np

BRANCHES = tuple((mode,arm) for mode in ('fixed','own') for arm in ('LF','FL','LL'))
GATE = 9.210340371976184


class RecursionFailure(RuntimeError):
    def __init__(self, error, context, partial):
        super().__init__(str(error))
        self.context = context
        self.partial = partial


def predict(core, x, P, k, controls):
    if k == 0:
        return x.copy(),P.copy(),np.eye(4),np.zeros((4,3)),np.zeros((3,3))
    ds,gy,dt = (float(controls[key][k]) for key in ('ds','gy','dt'))
    Q = np.diag([2e-5*abs(ds),math.radians(.015)**2*dt,0.])
    y,C,F,G = core.predict(x,P,ds,gy,dt,Q)
    return y,C,F,G,Q


def observation(full, los, k, arm, inside):
    z = full['z'][k].copy()
    if inside and arm in ('LF','LL'):z[0] = los['z'][k,0]
    if inside and arm in ('FL','LL'):z[1] = los['z'][k,1]
    return z


def covariance_check(stats, matrices):
    a = np.asarray(matrices)
    if not np.isfinite(a).all():raise ValueError('nonfinite covariance')
    sym = np.max(np.abs(a-a.swapaxes(-1,-2)),axis=(-1,-2))
    eigen = np.linalg.eigvalsh((a+a.swapaxes(-1,-2))*.5)
    scale = np.maximum(1.,np.max(np.abs(eigen),axis=-1))
    stats['minimum_eigenvalue'] = min(stats['minimum_eigenvalue'],float(eigen.min()))
    stats['maximum_symmetry_error'] = max(stats['maximum_symmetry_error'],float(sym.max()))
    if np.any(sym>1e-12*scale) or np.any(eigen[...,0]<-1e-12*scale):
        raise ValueError('covariance symmetry/PSD')


def run(core, online, model, spec, full, los, controls, trace, base, windows,
        *, verify_ff=False, progress=None):
    """Reuse identical Full prefix; batch only stateless observer evaluations."""
    n = len(full['t'])
    branches = (('own','FF'),) if verify_ff else BRANCHES
    own = [j for j,(mode,_) in enumerate(branches) if mode=='own']
    if verify_ff:
        windows = [dict(id='FF_VERIFY',first_index=0,last_index=-1)]
    mb_dims = dict(x=(4,),P=(4,4),prior=(4,),Pprior=(4,4),F=(4,4),G=(4,3),Qstate=(4,4),
                   h=(2,),H=(2,4),K=(4,2),S=(2,2),nu=(2,),u=(4,),R=(2,2),z=(2,),
                   rho=(),sigma_b=(),nis=(),tap=(),fp_margin=(),cells=(6,))
    base_dims = dict(x=(4,),P=(4,4),prior=(4,),Pprior=(4,4),F=(4,4),G=(4,3),Qstate=(4,4),
                     h=(2,),H=(2,4),S=(2,2),nis=(),tap=(),fp_margin=(),cells=(6,))
    records, states = {}, {}
    ends = {window['id']:window['last_index'] for window in windows}
    for window in windows:
        key = window['id'];start = window['first_index'];length = n-start
        data = {name:np.full((length,len(branches),*shape),np.nan) for name,shape in mb_dims.items()}
        data.update({'BASE_'+name:np.full((length,len(own),*shape),np.nan) for name,shape in base_dims.items()})
        data.update(mask=np.zeros((length,len(branches)),bool),BASE_mask=np.zeros((length,len(own)),bool),
                    pose_id=full['pose_id'][start:].copy(),t=full['t'][start:].copy(),
                    modes=np.array([mode for mode,_ in branches]),arms=np.array([arm for _,arm in branches]),
                    BASE_branch_indices=np.array(own),first_index=np.array(start),
                    last_intervention_index=np.array(window['last_index']),filled_rows=np.array(0),
                    Qinput=np.full((length,3,3),np.nan),
                    mu=full['muMB'][start:].copy(),BASE_mu=full['muBASE'][start:].copy(),
                    BASE_R=full['R'][start:].copy())
        records[key] = data
        if start:
            x,P = trace['x'][start-1],trace['P'][start-1]
            bx,bP = base['BASE_x'][start-1],base['BASE_P'][start-1]
        else:
            x = np.r_[controls['x0'],0.];P = full['P0']
            bx,bP = x,P
        states[key] = dict(x=np.repeat(x[None],len(branches),axis=0),
                           P=np.repeat(P[None],len(branches),axis=0),
                           bx=np.repeat(bx[None],len(own),axis=0),
                           bP=np.repeat(bP[None],len(own),axis=0))
    stats = dict(FFD_states=0,MB_transitions=0,BASE_transitions=0,
                 minimum_eigenvalue=float('inf'),maximum_symmetry_error=0.)
    context = {}
    try:
        for k in range(min(w['first_index'] for w in windows),n):
            context = dict(index=k,pose_id=int(full['pose_id'][k]),t=float(full['t'][k]),stage='predict')
            if progress:progress(context)
            mb, shadow = [], []
            for window in windows:
                key = window['id'];start = window['first_index']
                if k<start:continue
                state = states[key];out = records[key];i = k-start
                inside = start<=k<=window['last_index']
                for j,(_,arm) in enumerate(branches):
                    context.update(window=key,branch=j,stage='MB predict',x=state['x'][j].tolist(),P=state['P'][j].tolist())
                    rho = math.hypot(state['x'][j,0]-spec['anchor'][0],state['x'][j,1]-spec['anchor'][1])
                    xp,pp,F,G,Q = predict(core,state['x'][j],state['P'][j],k,controls)
                    sigma = float(np.interp(rho,[0.,1.5,3.,6.,10.],[.011,.020,.050,.120,.240]))
                    rv = full['R'][k].copy();rv[1,1] += sigma**2
                    mb.append((key,i,j,xp,pp,rho,sigma,rv,observation(full,los,k,arm,inside)))
                    for name,value in [('prior',xp),('Pprior',pp),('F',F),('G',G),('Qstate',G@Q@G.T),('rho',rho),('sigma_b',sigma),('R',rv)]:
                        out[name][i,j] = value
                    out['Qinput'][i] = Q
                    stats['MB_transitions'] += 1
                for b,j in enumerate(own):
                    context.update(window=key,branch=j,stage='BASE predict',x=state['bx'][b].tolist(),P=state['bP'][b].tolist())
                    xp,pp,F,G,Q = predict(core,state['bx'][b],state['bP'][b],k,controls)
                    shadow.append((key,i,b,j,xp,pp))
                    for name,value in [('prior',xp),('Pprior',pp),('F',F),('G',G),('Qstate',G@Q@G.T)]:
                        out['BASE_'+name][i,b] = value
                    stats['BASE_transitions'] += 1
            context.update(stage='batched source observer')
            # Keep all MB requests first, then all shadow requests, exactly once.
            all_states = np.stack([*(r[3] for r in mb),*(r[4] for r in shadow)])
            h,H,diag = model.batch(all_states,spec,return_diagnostics=True)
            stats['FFD_states'] += len(all_states)
            if not np.isfinite(h).all() or not np.isfinite(H).all():raise ValueError('source nonfinite')
            for p,(key,i,b,j,xp,pp) in enumerate(shadow,start=len(mb)):
                context.update(window=key,branch=j,stage='BASE update')
                out = records[key];state = states[key]
                inside = ends[key]>=k
                z = observation(full,los,k,branches[j][1],inside)
                v = z-h[p]-full['muBASE'][k];S = H[p]@pp@H[p].T+full['R'][k]
                nis = float(v@np.linalg.solve(S,v));allowed = bool(nis<=GATE)
                if not np.isfinite(nis):raise ValueError('nonfinite BASE NIS')
                x,C = xp,pp
                if allowed:
                    gain = np.linalg.solve(S,H[p]@pp).T
                    x = xp+gain@v;x[2] = core.wrap(x[2])
                    A = np.eye(4)-gain@H[p]
                    C = A@pp@A.T+gain@full['R'][k]@gain.T;C = (C+C.T)*.5
                state['bx'][b] = x;state['bP'][b] = C
                for name,value in [('x',x),('P',C),('h',h[p]),('H',H[p]),('S',S),('nis',nis),('tap',diag['tap'][p]),('cells',diag['cells'][p]),('fp_margin',diag['fp_margin'][p])]:
                    out['BASE_'+name][i,b] = value
                out['BASE_mask'][i,b] = allowed
            for p,(key,i,j,xp,pp,rho,sigma,rv,z) in enumerate(mb):
                context.update(window=key,branch=j,stage='MB update')
                out = records[key];state = states[key]
                permitted = bool(trace['mask'][k]) if branches[j][0]=='fixed' else bool(out['BASE_mask'][i,own.index(j)])
                v = z-h[p]-full['muMB'][k]
                x,C,K,S = online.joseph(xp,pp,H[p],v,rv,permitted,1.)
                nis = float(v@np.linalg.solve(S,v))
                if not np.isfinite(nis):raise ValueError('nonfinite MB NIS')
                state['x'][j] = x;state['P'][j] = C
                for name,value in [('x',x),('P',C),('h',h[p]),('H',H[p]),('K',K),('S',S),('nu',v),('u',xp+K@v),('z',z),('nis',nis),('tap',diag['tap'][p]),('cells',diag['cells'][p]),('fp_margin',diag['fp_margin'][p])]:
                    out[name][i,j] = value
                out['mask'][i,j] = permitted
            covariance_check(stats,np.stack([r[4] for r in mb]+[r[5] for r in shadow]))
            active_keys=[w['id'] for w in windows if k>=w['first_index']]
            covariance_check(stats,np.concatenate([states[key]['P'] for key in active_keys]))
            covariance_check(stats,np.concatenate([states[key]['bP'] for key in active_keys]))
            for window in windows:
                if k>=window['first_index']:records[window['id']]['filled_rows'][...] = k-window['first_index']+1
        for data in records.values():
            for name,value in data.items():
                if value.dtype.kind in 'fc' and not np.isfinite(value).all():raise ValueError('nonfinite trace '+name)
    except BaseException as error:
        raise RecursionFailure(error,context.copy(),records) from error
    return records,stats
