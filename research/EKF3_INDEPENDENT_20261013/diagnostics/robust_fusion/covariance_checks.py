"""Independent Gaussian synthetic draws check local covariance; robust mixture descriptive."""
import sys,json,math
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from m1_bias_robust_ekf import RobustBiasEKF

def run(n=3000):
 rng=np.random.default_rng(430271);out=[];mu=np.zeros(2);R=np.diag([.03**2,.2**2]);H=np.array([.1,.05,1.]);model=lambda x:(float(H@x),H.copy())
 for contamination,delta in [(False,float('inf')),(False,1.345),(True,1.345)]:
  nees=[];cover=[]
  for k in range(n):
   f=RobustBiasEKF(np.zeros(3));P=f.Ppose.copy();truth=rng.multivariate_normal(np.zeros(3),P);noise=rng.normal(0,.03)
   if contamination and rng.random()<.1:noise+=rng.normal(0,.3)
   f.update('A',float(H@truth+noise),None,model,[10,0,0],0,mu,R,delta)
   e=f.pose-truth;e[2]=math.atan2(math.sin(e[2]),math.cos(e[2]));q=float(e@np.linalg.solve(f.Ppose,e));nees.append(q);cover.append(q<=7.814727903251179)
  out.append(dict(independent_draws=n,contamination=contamination,loss='Gaussian' if math.isinf(delta) else 'Huber',mean_pose_nees=float(np.mean(nees)),pose95=float(np.mean(cover))))
 assert .93<=out[0]['pose95']<=.97,'Gaussian calibration failed'
 return dict(status='GAUSSIAN_CALIBRATION_PASS_ROBUST_DESCRIPTIVE_ONLY',seed=430271,rows=out,covariance='Local IRLS Gaussian approximation, no robust calibration guarantee',scientific_PASS=False)
if __name__=='__main__':
 result=run();Path(sys.argv[1]).write_text(json.dumps(result,indent=2));print(json.dumps(result))
