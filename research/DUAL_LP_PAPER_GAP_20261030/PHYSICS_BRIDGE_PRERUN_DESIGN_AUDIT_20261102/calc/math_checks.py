# Independent auditor algebra checks (own code, no implementer/proposer helper)
import numpy as np, json
rng=np.random.default_rng(20261102); res={}
e_s=np.array([0.,1.]); e_r=np.array([1.,0.])
m1=m2=m3=0
for _ in range(2000):
    A=rng.standard_normal((4,4)); P=A@A.T+1e-3*np.eye(4)
    H=np.zeros((2,4)); H[0,:2]=rng.standard_normal(2); H[1,:3]=rng.standard_normal(3)
    B=rng.standard_normal((2,2)); R=B@B.T+1e-3*np.eye(2)
    lam=abs(rng.standard_normal())*0.05
    S0=H@P@H.T+R; K0=np.linalg.solve(S0,H@P).T
    Sl=S0+lam*np.outer(e_s,e_s); Kl=np.linalg.solve(Sl,H@P).T
    c=e_s@np.linalg.solve(S0,e_s)
    m1=max(m1,np.max(np.abs(Kl@e_s-(K0@e_s)/(1+lam*c)))/max(1,np.max(np.abs(K0))))
    # range column is NOT simply scaled: record max relative change
    m2=max(m2,np.max(np.abs(Kl@e_r-K0@e_r))/max(1e-12,np.max(np.abs(K0@e_r))))
    dmu=np.array([rng.standard_normal()*0.02,0.0]); nu=rng.standard_normal(2)
    dx=Kl@(nu-dmu)-Kl@nu; m3=max(m3,np.max(np.abs(dx-(-Kl[:,0]*dmu[0]))))
res['gain_column_shrink_identity_max_scaled_err']=m1
res['range_column_max_relative_change_(nonzero_expected)']=m2
res['mean_shift_identity_max_err_(mu_s_equal)']=m3
# port-ratio derivative and common-scalar invariance
Pp,Pm=0.7,0.3; s=lambda a,b:(a-b)/(a+b); h=1e-7
gP=np.array([2*Pm,-2*Pp])/(Pp+Pm)**2
fd=np.array([(s(Pp+h,Pm)-s(Pp-h,Pm))/(2*h),(s(Pp,Pm+h)-s(Pp,Pm-h))/(2*h)])
res['gP_formula_vs_FD_max_err']=float(np.max(np.abs(fd-gP)))
res['common_scalar_invariance_err']=abs(s(3.7*Pp,3.7*Pm)-s(Pp,Pm))
# range lattice of native first-edge range
c=299792458.0; df=1.95e6; N=257
res['native_range_step_m']=c/(4*N*df); res['uniform_quantization_rms_cm']=100*c/(4*N*df)/np.sqrt(12)
print(json.dumps(res,indent=1))
json.dump(res,open('/home/claude/auditcalc/MATH_CHECKS.json','w'),indent=1)
