"""Check every saved logical arm against fixed lookup/gate/update contract (no rerun)."""
from __future__ import annotations
from bootstrap import *

def main():
    rows=[];scores=pd.read_csv(TABLES/'RECURSIVE_144_LOGICAL_SCORES.csv')
    constants=json.loads((RESULTS/'CONSTANT_VARIANCE_TRAIN_LOCK.json').read_text())['held_route_constants']
    for case in CASES:
        for bias in BIASES:
            D=read_data(case,bias)
            for _,r in scores[(scores.case==case)&(scores.bias==bias)].iterrows():
                T=read_trace(case,bias,r.arm,r.gate);u=T['used'];rej=~u;bg=r.arm[:2]
                prev=np.vstack((D['x0'],T['X'][:-1]))
                rho=np.hypot(prev[:,0]-D['anchor'][0],prev[:,1]-D['anchor'][1])
                sg=np.interp(rho,DG.HAND[0],DG.HAND[1])
                expected_R=D['R'].copy()
                if r.arm.endswith('_VAR'):expected_R[:,1,1]+=sg**2
                if r.arm.endswith('_CONST'):expected_R[:,1,1]+=constants[case]['variance']
                Rerr=float(np.max(abs(T['Ru']-expected_R)))
                innovation_err=float(np.max(abs(T['nu']-(D['z']-T['hx']-D['mu'][bg]))))
                S_err=float(np.max(abs(T['S']-(T['J']@T['Pp']@T['J'].transpose(0,2,1)+T['Ru']))))
                nis2=np.einsum('ni,ni->n',T['nu'],np.linalg.solve(T['S'],T['nu'][...,None])[...,0])
                nis_err=float(np.max(abs(T['nis']-nis2)))
                rejection_x_err=float(np.max(abs(T['X'][rej]-T['xp'][rej]))) if rej.any() else 0.
                rejection_P_err=float(np.max(abs(T['PX'][rej]-T['Pp'][rej]))) if rej.any() else 0.
                lookup_err=float(np.max(abs(T['rho_lookup']-rho)))
                passed=all([Rerr<1e-14,innovation_err<1e-14,S_err<1e-14,nis_err<1e-10,
                            rejection_x_err==0,rejection_P_err==0,lookup_err<1e-12])
                rows.append(dict(case=case,bias=bias,arm=r.arm,gate=r.gate,R_error=Rerr,
                    innovation_error=innovation_err,S_error=S_err,NIS_error=nis_err,
                    rejected_state_change=rejection_x_err,rejected_P_change=rejection_P_err,
                    previous_posterior_lookup_distance_error=lookup_err,pass_check=passed))
    table=pd.DataFrame(rows);table.to_csv(TABLES/'TRACE_CONTRACT_144_CHECKS.csv',index=False,float_format='%.17g')
    qa={'logical_arms':len(rows),'all_pass':bool(table.pass_check.all()),
        'max_errors':{c:float(table[c].max()) for c in table if c.endswith('error') or c.endswith('change')},
        'extra_filter_recursions':0,'audit':'SELF_REVIEW_ONLY'}
    write_json(RESULTS/'TRACE_CONTRACT_QA.json',qa);print(json.dumps(qa,indent=2))
    assert qa['all_pass']
if __name__=='__main__':main()
