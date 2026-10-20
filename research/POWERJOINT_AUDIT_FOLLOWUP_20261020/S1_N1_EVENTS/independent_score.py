"""Independent scalar/Cholesky scorer. No imports from engine or replay scorer."""
import math
import numpy as np

def score_window(state, covariance, truth, bias_dps):
    heading=[]; hnees=[]; variance=[]; pose=[]; conditional=[]; xy=[]; be=[]; bg=[]
    for x,p,gt in zip(state,covariance,truth):
        e=np.array([float(x[0]-gt[0]),float(x[1]-gt[1]),
                    math.atan2(math.sin(x[2]-gt[2]),math.cos(x[2]-gt[2]))])
        deg=math.degrees(float(e[2]));heading.append(deg)
        hnees.append(float(e[2]**2/p[2,2]));variance.append(float(p[2,2]))
        y=np.linalg.solve(np.linalg.cholesky(p[:3,:3]),e)
        pose.append(float(y@y))
        r=e[:2]-p[:2,2]*(e[2]/p[2,2])
        schur=p[:2,:2]-np.outer(p[:2,2],p[2,:2])/p[2,2]
        y=np.linalg.solve(np.linalg.cholesky(schur),r)
        conditional.append(float(y@y));xy.append(float(e[0]**2+e[1]**2))
        v=math.degrees(float(x[3]));bg.append(v);be.append((v-bias_dps)**2)
    n=len(heading)
    mean=lambda v:math.fsum(v)/n
    return dict(heading_rmse_deg=math.sqrt(mean([x*x for x in heading])),
        signed_heading_deg=mean(heading),heading_sigma_rms_deg=math.degrees(math.sqrt(mean(variance))),
        heading95=sum(x<=3.841458820694124 for x in hnees)/n,heading_nees=mean(hnees),
        pose_nees=mean(pose),conditional_xy_nees=mean(conditional),xy_rmse_m=math.sqrt(mean(xy)),
        bias_rmse_dps=math.sqrt(mean(be)),bias_mean_dps=mean(bg),bias_final_dps=bg[-1])
