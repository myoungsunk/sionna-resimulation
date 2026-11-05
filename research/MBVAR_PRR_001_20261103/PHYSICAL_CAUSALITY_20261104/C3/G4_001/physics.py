"""Stored legacy spectra attribution. No RT, raw rephasing, model or EKF."""
import json
import numpy as np
def signed(D,v):
 s,den,p=D.signed(v)
 if s is None or not np.isfinite([s,den,*p]).all() or den<=0:raise ValueError('undefined polarization denominator')
 return float(s),float(den),p

def complex_closure(actual,reference,tolerance):
 checks={}
 for name,a,r in [('joint',actual,reference),('RX_plus',actual[:,0],reference[:,0]),('RX_minus',actual[:,1],reference[:,1])]:
  den=np.linalg.norm(r);peak=np.max(abs(r))
  if not np.isfinite(a).all() or not np.isfinite(r).all() or den<=0 or peak<=0:raise ValueError('undefined CIR closure reference')
  error=a-r;erel=float(np.linalg.norm(error)/den);emax=float(np.max(abs(error))/peak)
  if erel>tolerance or emax>tolerance:raise ValueError('CIR linearity')
  checks[name]=dict(Erel=erel,Emax=emax)
 return checks
def replay(a):
 labels=a['group_labels'].tolist();fields=a['legacy_group_fields'];freq=a['frequencies_hz'];ng=len(labels)
 if fields.shape!=(ng,257,2) or fields.dtype!=np.complex128 or len(set(labels))!=ng or labels.count('DIRECT')!=1 or int(a['direct_group'])!=labels.index('DIRECT'):raise ValueError('legacy group schema')
 if freq.shape!=(257,) or freq.dtype!=np.float64 or not np.array_equal(freq,6250400000.+1950000.*np.arange(257)):raise ValueError('frequency grid')
 if a['original_field'].dtype!=np.complex64 or a['original_field'].shape!=(len(a['source_group']),2):raise ValueError('legacy raw schema')
 if a['offsets'].shape!=(258,) or a['offsets'][0]!=0 or a['offsets'][-1]!=len(a['original_field']) or np.any(np.diff(a['offsets'])<=0):raise ValueError('offsets')
 if np.any(a['source_group']<0) or np.any(a['source_group']>=ng):raise ValueError('group range')
 if not np.isfinite(fields).all() or not np.isfinite(a['original_field']).all():raise ValueError('nonfinite legacy')
 rebuilt=np.zeros_like(fields);counts=np.zeros((ng,257),np.int32)
 for fi in range(257):
  lo,hi=map(int,a['offsets'][fi:fi+2])
  for j in range(lo,hi):
   gi=int(a['source_group'][j]);rebuilt[gi,fi]+=a['original_field'][j];counts[gi,fi]+=1
 if not np.array_equal(fields,rebuilt) or not np.array_equal(fields.sum(0),a['legacy_native_full']):raise ValueError('exact saved legacy replay')
 if not np.array_equal(counts,a['group_count']) or not np.array_equal(counts==0,a['group_missing']):raise ValueError('group count/missing')
 if 'INVALID' in labels and np.any(fields[labels.index('INVALID')]):raise ValueError('nonzero INVALID')
 return fields,labels,int(a['direct_group']),float(freq[1]-freq[0])
def analyze(a,D,plan):
 fields,labels,direct,df=replay(a);full_h=fields.sum(0);los_h=fields[direct]
 gc=D.cir(fields);full=D.cir(full_h);los=gc[direct];reflected=full-los
 cir_closure=complex_closure(gc.sum(0),full,plan['closure_rel_tol'])
 det=D.decomposition(full_h,los_h,df)
 if det['identity_error']>plan['decomposition_abs_tol']:raise ValueError('fixed/selector identity')
 for name in ('full','los'):
  if det[name]['s'] is None or det[name]['denominator']<=0:raise ValueError('detector denominator')
 group_rows=[];surface_rows=[];windows=[];powers=[];crosses=[];closure=[]
 reflections=[i for i,n in enumerate(labels) if i!=direct and n!='INVALID']
 surface_groups={}
 for i in reflections:
  for surface in {p[0] for p in json.loads(labels[i])}:surface_groups.setdefault(surface,set()).add(i)
 for tap_ref,tap in [('fpFull',det['full']['tap']),('fpLoS',det['los']['tap'])]:
  idx=(tap+np.arange(-4,5))%1028;windows.append(idx)
  v=gc[:,tap,:];individual=abs(v)**2;cross=2*np.real(v[:,None,:]*v[None,:,:].conj())
  for i in range(len(v)):cross[i,i,:]=0.
  pair_sum=np.triu(cross[:,:,0],1).sum(),np.triu(cross[:,:,1],1).sum()
  predicted=individual.sum(0)+np.asarray(pair_sum);actual=abs(full[tap])**2;error=predicted-actual
  if not np.all(np.abs(error)<=plan['power_abs_tol']+plan['closure_rel_tol']*np.abs(actual)):raise ValueError('pairwise coherent power identity')
  powers.append(individual);crosses.append(cross);closure.append(dict(tap_ref=tap_ref,residual=error.tolist(),individual_plus_cross=predicted.tolist(),full_power=actual.tolist()))
  baseline,_,_=signed(D,full[tap]);q=gc[reflections,tap,:].sum(0);allocated=np.zeros(2)
  for i in reflections:
   removed=full-gc[i];s,den,power=signed(D,removed[tap]);redetected=D.detect(removed,df)
   if redetected['s'] is None:raise ValueError('undefined removed detector')
   dc=2*np.real(los[tap].conj()*v[i]);allocation=dc+np.real(v[i].conj()*q);allocated+=allocation
   group_rows.append(dict(group_id=i,group_label=labels[i],tap_ref=tap_ref,tap=tap,group_plus_power=individual[i,0],group_minus_power=individual[i,1],direct_cross_plus=dc[0],direct_cross_minus=dc[1],allocated_plus=allocation[0],allocated_minus=allocation[1],removed_s_fixed=s,delta_s_fixed=baseline-s,removed_denominator=den,removed_plus_power=power[0],removed_minus_power=power[1],removed_detected_tap=redetected['tap'],removed_s_redetected=redetected['s'],delta_s_redetected=det['full']['s']-redetected['s']))
  target=abs(full[tap])**2-abs(los[tap])**2
  if not np.all(np.abs(allocated-target)<=plan['power_abs_tol']+plan['closure_rel_tol']*abs(full[tap])**2):raise ValueError('allocation coherent identity')
  closure[-1]['allocation_residual']=(allocated-target).tolist()
  for surface,indices in sorted(surface_groups.items()):
   indices=sorted(indices);removed=full-gc[indices].sum(0);s,den,power=signed(D,removed[tap]);rd=D.detect(removed,df)
   if rd['s'] is None:raise ValueError('undefined surface removal')
   surface_rows.append(dict(surface=surface,removed_group_indices=json.dumps(indices),removed_group_count=len(indices),tap_ref=tap_ref,tap=tap,removed_s_fixed=s,delta_s_fixed=baseline-s,removed_denominator=den,removed_plus_power=power[0],removed_minus_power=power[1],removed_detected_tap=rd['tap'],removed_s_redetected=rd['s'],delta_s_redetected=det['full']['s']-rd['s']))
 indices=np.stack(windows)
 arrays=dict(full_spectrum=full_h,direct_spectrum=los_h,reflected_spectrum=full_h-los_h,full_cir=full,direct_cir=los,reflected_cir=reflected,full_power=abs(full)**2,direct_power=abs(los)**2,reflected_power=abs(reflected)**2,group_labels=np.asarray(labels),window_indices=indices,group_windows=np.stack([gc[:,ix,:] for ix in indices]),full_windows=full[indices],direct_windows=los[indices],reflected_windows=reflected[indices],individual_power_center=np.stack(powers),pair_cross_center=np.stack(crosses))
 return dict(detector=det,groups=len(labels),reflection_groups=len(reflections),cir_closure=cir_closure,power_closure=closure,attribution_reference='stored complex64-compatible legacy group sums; no F64 substitution',cross_convention='individual diagonal separate; upper triangular 2Re only; matrix symmetric'),arrays,group_rows,surface_rows
