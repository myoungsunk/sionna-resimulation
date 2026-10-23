"""Truth-only diagnosis and scoring. Runtime feature/replay modules must not import this."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scipy.stats import chi2
from .common import readonly, require
from .numerics import delta, wrap, psd, solve_spd, moments, episode_curve

@dataclass(frozen=True)
class Truth:
    state: np.ndarray
    s_los: np.ndarray
    fp_shift: np.ndarray

    def __post_init__(self):
        object.__setattr__(self, 'state', readonly(self.state))
        object.__setattr__(self, 's_los', readonly(self.s_los))
        object.__setattr__(self, 'fp_shift', readonly(self.fp_shift))
        require(self.state.shape == (len(self.s_los),4) and len(self.fp_shift) == len(self.s_los), 'Truth schema')

class OracleCorrector:
    name='ORACLE'; diagnostic=True; model_hash='TRUTH_ONLY_MATCHED_ALGORITHM'
    def __init__(self, inputs, truth):
        self.values={p.pose_id: float(p.z[1]-truth.s_los[k]-p.mu[1]) for k,p in enumerate(inputs.packets)}
    def __call__(self, packet, x, h, model):
        return self.values[packet.pose_id], {'profile_status':'ORACLE_ONLY'}


def error_arrays(inputs, truth, trace):
    a=trace.arrays; ks=a['k'].astype(int); e=delta(a['x_plus'], truth.state[ks]); P=a['P_plus']
    v=truth.state[ks,:2]-inputs.anchor[:2]; radius=np.linalg.norm(v,axis=1)
    valid=radius>1e-9
    ur=np.full_like(v,np.nan); ur[valid]=v[valid]/radius[valid,None]; ut=np.c_[-ur[:,1],ur[:,0]]
    er=np.sum(e[:,:2]*ur,axis=1); et=np.sum(e[:,:2]*ut,axis=1)
    dz=inputs.anchor[2]-inputs.robot_z
    dtrue=np.sqrt(radius**2+dz**2); dhat=np.sqrt(np.sum((a['x_plus'][:,:2]-inputs.anchor[:2])**2,axis=1)+dz**2)
    out=dict(e=e, heading_deg=np.degrees(e[:,2]), xy_cm=100*np.linalg.norm(e[:,:2],axis=1),
             radial_cm=100*er,tangential_cm=100*et,bias_dps=np.degrees(e[:,3]),range_cm=100*(dhat-dtrue),
             radial_valid=valid, ur=ur,ut=ut)
    for name,ix in [('heading',[2]),('xy',[0,1]),('pose',[0,1,2]),('all4',[0,1,2,3])]:
        values=[]
        for k in range(len(e)):
            cov=P[k][np.ix_(ix,ix)]; err=e[k,ix]
            values.append(float(err@solve_spd(cov,err)))
        out[name+'_nees']=np.array(values)
    for name,u in [('radial',ur),('tangential',ut)]:
        var=np.einsum('ni,nij,nj->n',u,P[:,:2,:2],u)
        val=np.sum(e[:,:2]*u,axis=1)**2/var
        out[name+'_nees']=val
    return out


def score_trace(inputs, truth, trace, windows=None):
    a=trace.arrays; E=error_arrays(inputs,truth,trace); t=a['t']
    windows=windows or {'initial_0_10':(0,10),'middle_10_30':(10,30),'stable_30_plus':(30,np.inf),'all':(0,np.inf)}
    rows=[]
    for name,(lo,hi) in windows.items():
        m=(t>=lo)&(t<hi)
        row={**inputs.identity,'arm':trace.metadata['arm'],'window':name,'n':int(m.sum()),'status':'PASS'}
        if not m.any():
            rows.append({**row,'status':'EMPTY_WINDOW'});continue
        for comp in ('heading_deg','xy_cm','radial_cm','tangential_cm','bias_dps','range_cm'):
            v=E[comp][m]
            if not np.isfinite(v).all():
                row[comp+'_status']='UNDEFINED_AT_ANCHOR';continue
            row[comp+'_mse']=float(np.mean(v*v));row[comp+'_rmse']=float(np.sqrt(np.mean(v*v)))
            row[comp+'_mean']=float(v.mean());row[comp+'_q95']=float(np.quantile(abs(v),.95));row[comp+'_q99']=float(np.quantile(abs(v),.99));row[comp+'_peak']=float(np.max(abs(v)))
        for comp,df in [('heading',1),('xy',2),('pose',3),('all4',4),('radial',1),('tangential',1)]:
            v=E[comp+'_nees'][m]
            if not np.isfinite(v).all():
                row[comp+'_covariance_status']='UNDEFINED';continue
            row[comp+'_nees']=float(v.mean());row[comp+'_cov95']=float(np.mean(v<=chi2.ppf(.95,df)))
            row[comp+'_nees_log_deviation']=float(abs(np.log(max(v.mean(),1e-300)/df)))
            row[comp+'_cov95_deviation']=abs(row[comp+'_cov95']-.95)
        for comp,thresholds in [('heading_deg',[1,2,5,10,20]),('xy_cm',[5,10,20,50,100])]:
            for episode in episode_curve(t[m],abs(E[comp][m]),thresholds):
                suffix=f"{comp}_above_{episode['threshold']:g}"
                row[suffix+'_duration_s']=episode['duration_total_s']
                row[suffix+'_longest_s']=episode['duration_max_s']
                row[suffix+'_right_censored']=episode['right_censored']
        row['accepted_fraction']=float(a['accepted'][m].mean());row['nis_mean']=float(a['NIS'][m].mean())
        row['nis_accepted_mean']=float(a['NIS'][m & a['accepted'].astype(bool)].mean()) if (m & a['accepted'].astype(bool)).any() else np.nan
        rows.append(row)
    episodes=[]
    for comp,thresholds in [('heading_deg',[1,2,5,10,20]),('xy_cm',[5,10,20,50,100])]:
        for r in episode_curve(t,abs(E[comp]),thresholds):
            episodes.append({**inputs.identity,'arm':trace.metadata['arm'],'component':comp,**r})
    return rows,episodes


def residual_table(inputs, truth, model, prior, correctors, common_accept):
    rows=[]
    for ii,k in enumerate(prior.arrays['k'].astype(int)):
        p=inputs.packets[k];x=prior.arrays['x_minus'][ii];h,H=model.observe(x);hg,_=model.observe(truth.state[k])
        e_model=p.z[1]-hg[1];c_model=truth.s_los[k]-hg[1];rb=e_model-p.mu[1]
        for corrector in correctors:
            c,_=corrector(p,x,h,model);c_gt,_=corrector(p,truth.state[k],hg,model)
            c1=rb-c_gt;c2=c_gt-c;rp=rb-c
            require(abs(c1+c2-rp)<1e-10, 'c1+c2 closure')
            rows.append({**inputs.identity,'source_prior':prior.metadata['arm'],'arm':corrector.name,'model_hash':corrector.model_hash,'source_hash':inputs.source_hash,'k':k,'pose_id':p.pose_id,'t_s':p.t,
                         'r_B':rb,'correction':c,'r_candidate':rp,'D_s':2*rb*c-c*c,'c1':c1,'c2':c2,'c_model':c_model,
                         'e_full_minus_los':p.z[1]-truth.s_los[k], 'fp_shift_diagnostic_only':truth.fp_shift[k],
                         'common_accepted':bool(common_accept[ii]),'own_accepted':None,'small_base_residual':abs(rb)<.05})
    return rows


def all4_budget(inputs, truth, model, trace, corrector):
    """Exact realized-linearization accounting, centered and uncentered moments kept separately."""
    a=trace.arrays;n=len(a['t']);ks=a['k'].astype(int)
    require(ks[0]==0,'Budget requires full trace; branch impulse is handled separately')
    dm=delta(a['x_minus'],truth.state);dp=delta(a['x_plus'],truth.state)
    names=('initial','odom','gyro','range','pol_c1_fp0','pol_c1_fp1','pol_c1_fp2','pol_c2','r_pred','r_meas','angle_chart')
    D=np.zeros((len(names),4));Y=np.empty((n,len(names),4))
    ds_reference,dtheta_reference=model.reference_increments(inputs.t,truth.state)
    for k,p in enumerate(inputs.packets):
        hg,Hg=model.observe(truth.state[k]);cgt,_=corrector(p,truth.state[k],hg,model)
        eps=p.z-p.mu-hg;eps=eps.copy();eps[1]-=a['correction'][k]
        c2=cgt-a['correction'][k];c1=eps[1]-c2
        if k==0:
            Dm=np.zeros_like(D);Dm[0]=dm[0]
        else:
            # Match native legacy-euler controls used by build_positive_bias_controls.
            dpos=truth.state[k,:2]-truth.state[k-1,:2];theta=truth.state[k-1,2]
            ds_true=float(ds_reference[k])
            dtheta_true=float(dtheta_reference[k])
            w=np.array([inputs.controls[k,0]-ds_true,inputs.controls[k,1]-dtheta_true-truth.state[k,3]*inputs.controls[k,2],0.])
            F,G=a['F'][k],a['G'][k]
            rp=dm[k]-F@dp[k-1]-G@w
            Dm=D@F.T;Dm[1]+=G[:,0]*w[0];Dm[2]+=G[:,1]*w[1];Dm[8]+=rp
        K,H=a['K'][k],a['H'][k];D=Dm@(np.eye(4)-K@H).T
        D[3]+=K[:,0]*eps[0];layer=0 if truth.fp_shift[k]==0 else (1 if abs(truth.fp_shift[k])==1 else 2)
        D[4+layer]+=K[:,1]*c1;D[7]+=K[:,1]*c2
        remainder=hg-a['h'][k]+H@dm[k]
        D[9]+=K@remainder
        # Wrapped posterior chart can add an integer 2pi remainder; keep it explicit.
        chart=dp[k]-D.sum(0)
        require(np.max(abs(chart[[0,1,3]]))<1e-8,'Non-angular budget mismatch must not be hidden in chart remainder')
        require(abs(chart[2]/(2*np.pi)-round(chart[2]/(2*np.pi)))<1e-8,'Heading chart remainder is not a multiple of 2pi')
        D[10,2]+=chart[2]
        Y[k]=D
    require(np.max(np.abs(Y.sum(1)-dp))<1e-8,'All4 budget closure')
    rows=[];mat=[];m=a['t']>=30
    if not m.any(): m=np.ones(n,bool)
    E=error_arrays(inputs,truth,trace)
    projections=[('x',Y[:,:,0],dp[:,0]),('y',Y[:,:,1],dp[:,1]),('heading',Y[:,:,2],dp[:,2]),('gyro_bias',Y[:,:,3],dp[:,3])]
    for nm,u in [('radial',E['ur']),('tangential',E['ut'])]:
        if np.isfinite(u).all():
            projections.append((nm,np.einsum('nsi,ni->ns',Y[:,:,:2],u),np.sum(dp[:,:2]*u,1)))
    for comp,Z,total in projections:
        mean,C,M=moments(Z[m]);mse=float(np.mean(total[m]**2));variance=float(np.var(total[m]))
        for i,name in enumerate(names):
            rows.append({**inputs.identity,'arm':trace.metadata['arm'],'component':comp,'source':name,
                         'mean':mean[i],'M_diag':M[i,i],'C_diag':C[i,i],'contribution_mse':M[i].sum(),
                         'share_mse':M[i].sum()/mse if mse>0 else np.nan,'share_var':C[i].sum()/variance if variance>0 else np.nan,
                         'interpretation':'realized-linearization accounting, not removal effect'})
            for j,other in enumerate(names):
                mat.append({**inputs.identity,'arm':trace.metadata['arm'],'component':comp,'i':name,'j':other,'M':M[i,j],'C':C[i,j]})
    return rows,mat,Y


def process_noise_statistics(inputs,truth,model):
    """Truth-only input-noise audit; mean square is never labelled variance."""
    ds,dtheta=model.reference_increments(inputs.t,truth.state)
    w=np.c_[inputs.controls[:,0]-ds,inputs.controls[:,1]-dtheta-truth.state[:,3]*inputs.controls[:,2]]
    q=np.c_[2e-5*abs(inputs.controls[:,0]),np.deg2rad(.015)**2*inputs.controls[:,2]]
    rows=[]
    for window,mask in [('all',inputs.t>=inputs.t[0]),('stable_30_plus',inputs.t>=30)]:
        mask=mask.copy();mask[0]=False
        for j,signal in enumerate(('odom','gyro')):
            v=w[mask,j];qq=q[mask,j]
            if not len(v):
                rows.append({**inputs.identity,'window':window,'signal':signal,'status':'EMPTY_WINDOW'});continue
            mu=float(v.mean());var=float(v.var());ms=float(np.mean(v*v));qm=float(qq.mean())
            require(abs(ms-var-mu*mu)<1e-12,'Input mean-square/variance identity failed')
            z=v-mu;den=float(z@z)
            rows.append({**inputs.identity,'window':window,'signal':signal,'n':len(v),'mean':mu,'variance':var,'mean_square':ms,'q_mean':qm,
                         'variance_over_q':var/qm if qm>0 else np.nan,'mean_square_over_q':ms/qm if qm>0 else np.nan,
                         'mean_squared_over_q':mu*mu/qm if qm>0 else np.nan,'rho1':float(z[:-1]@z[1:]/den) if den>0 else np.nan,
                         'status':'PASS' if qm>0 else 'ZERO_PROCESS_VARIANCE','classification':'TRUTH_ONLY_INPUT_AUDIT'})
    return rows
