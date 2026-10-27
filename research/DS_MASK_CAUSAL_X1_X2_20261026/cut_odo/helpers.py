from common import *

def cache_inputs():
 feat=pd.read_csv(S.one('OBSERVATION_FEATURES_LABELS.csv.gz'));par=pd.read_csv(S.one('OOF_PARAMETERS.csv.gz'));mr=pd.read_csv(S.PKG/'results_murec/MR_SERIES.csv.gz');hg=pd.read_csv(S.PKG/'results_hgate/HG_SERIES.csv.gz')
 cache=[]
 for case in V.MANIFEST['cases']:
  for bias in ['B0','L2']:
   inp=S.load_case(case,bias,feat,par,mr,hg);ref=load(E1/'E1'/f'{case["id"]}_{bias}.npz');check('t',inp['t'],ref['t_s'],0);check('ids',inp['ids'],ref['pose_id'],0)
   mask=np.column_stack([ref['acc'][:,0],ref['acc'][:,-1]]);check('fixed_mask',mask[:,0],mask[:,1],0)
   cache.append((case,bias,inp,ref,mask))
 return cache

def exact_compare(label,out,j,ref,jr):
 for k in ['x','P','prior','Pprior','h','H','K','mu','R','nu','acc']:
  check(label+'_'+k,out[k][:,j],ref[k][:,jr])