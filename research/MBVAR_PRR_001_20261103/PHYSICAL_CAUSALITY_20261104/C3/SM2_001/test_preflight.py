"""Offline negative checks on retained rays. Zero solver/model calls."""
from pathlib import Path
import copy,importlib.util,json,sys,unittest
import numpy as np
from authority import HERE,read,check_go,validate_row,sha
import qa

class NegativeChecks(unittest.TestCase):
 def setUp(self):
  self.plan=read(HERE/'PLAN.json');self.row=self.plan['authorized'][0]
  old=HERE.parents[1]/'NEW_RT_DATA/SM0/BATCH_AMENDED_001/captures/R4_aB_m0_168/RAW.npz'
  with np.load(old,allow_pickle=False) as z:self.a={k:z[k].copy() for k in z.files if not k.startswith('archive_')}
  manifest=read(old.parent/'MANIFEST.json');self.lookup={int(k):v for k,v in manifest['object_lookup'].items()}
 def test_retained_raw_baseline(self):
  qa.source_groups(self.a,self.lookup);r,g=qa.evaluate_arrays(self.a);self.assertEqual(r['status'],'C3_RAW_NUMERICAL_PASS')
 def test_scope_yaw_xyz_degrees_and_mount(self):
  for k,v in [('coordinate','R5_982'),('yaw_deg',45.),('yaw_deg',np.pi),('xyz',[5.251464,.325895,.46]),('id','old_pose168')]:
   bad=copy.deepcopy(self.row);bad[k]=v
   with self.assertRaises(ValueError):validate_row(bad,self.plan)
 def test_old_go_missing_go_bindings_budget(self):
  for go in [{},{'schema':'SM0_GO_V1','decision':'GO'}, {'schema':'C3_SM2_GO_V1','decision':'GO','bindings_sha256':{},'authorized':self.plan['authorized']}]:
   with self.assertRaises(ValueError):check_go(go,self.plan,{'producer.py':'actual'})
 def test_raw_dtypes_nan_phase_source_group_direct_freq(self):
  changes=[('tau',lambda a:a.astype(np.float64)),('original_field',lambda a:a.astype(np.complex128)),('frequencies_hz',lambda a:a[::-1]),('source_group',lambda a:a*0),('direct_source_index',lambda a:a+1)]
  for key,fn in changes:
   a=copy.deepcopy(self.a);a[key]=fn(a[key])
   with self.assertRaises(ValueError,msg=key):qa.evaluate_arrays(a)
  a=copy.deepcopy(self.a);a['a'][0,0,0]=complex(float('nan'),0)
  with self.assertRaises(ValueError):qa.evaluate_arrays(a)
 def test_archive_spoof(self):
  a=copy.deepcopy(self.a);a['archive_full']=a['native_f64']
  with self.assertRaises(ValueError):qa.evaluate_arrays(a)
 def test_native_cfr_missing_dtype_shape_nan_inf(self):
  a=copy.deepcopy(self.a);del a['native_cfr32']
  with self.assertRaises(ValueError):qa.evaluate_arrays(a)
  for bad in [np.full((257,2),complex(float('nan'),0),np.complex64),np.full((257,2),complex(float('inf'),0),np.complex64),np.zeros((257,2),np.complex128),np.zeros((257,1),np.complex64)]:
   a=copy.deepcopy(self.a);a['native_cfr32']=bad
   with self.assertRaises(ValueError):qa.evaluate_arrays(a)
  for bad in [np.full((2,),complex(float('nan'),0),np.complex64),np.full((2,),complex(float('inf'),0),np.complex64),np.zeros((2,),np.complex128),np.zeros((1,),np.complex64)]:
   with self.assertRaises(ValueError):qa.native_cfr_check(bad,(2,))
 def test_semantic_counts_missing_invalid_object(self):
  for key in ('group_count','group_missing','source_index'):
   a=copy.deepcopy(self.a);a[key].flat[0]=a[key].flat[0]+1
   with self.assertRaises(ValueError,msg=key):qa.source_groups(a,self.lookup)
  with self.assertRaises(ValueError):qa.source_groups(self.a,{})
 def test_zero_denominator_and_shape(self):
  for ref in [np.zeros(2),np.array([float('nan'),1]),np.ones(3)]:
   with self.assertRaises(ValueError):qa.error(np.ones(2),ref)
 def test_repeat_exact_and_mutation(self):
  old=HERE.parents[1]/'NEW_RT_DATA/SM0/BATCH_AMENDED_001/captures/R4_aB_m0_168/bins/000.npz'
  with np.load(old,allow_pickle=False) as z:a=dict(z)
  a['labels']=a['labels'].tolist();b=copy.deepcopy(a);qa.repeat_check(a,b)
  b['tau'][0]+=np.float32(1e-9)
  with self.assertRaises(ValueError):qa.repeat_check(a,b)
 def test_direct_projection_and_wrong_rotation(self):
  lock=read(HERE/'INPUT_LOCK.json');banks=[]
  for n in ('LP_plus45_bank.npz','LP_minus45_bank.npz'):
   p=lock['banks'][n]['path'];p=Path('/mnt/d/'+p[3:])
   with np.load(p,allow_pickle=False) as z:banks.append(dict(z))
  qa.direct_projection(self.a,banks,[5.251464,.325895,.45],-31.700092)
  for yaw in [0.,-31.700092+45.,float(np.deg2rad(-31.700092))]:
   with self.assertRaises(ValueError):qa.direct_projection(self.a,banks,[5.251464,.325895,.45],yaw)
  swapped=copy.deepcopy(self.a);swapped['a']=swapped['a'][:,::-1,:]
  with self.assertRaises(ValueError):qa.direct_projection(swapped,banks,[5.251464,.325895,.45],-31.700092)

if __name__=='__main__':unittest.main(verbosity=2)
