#!/usr/bin/env python3
"""Draw independently inspectable static trajectory/IMU/RF/filter comparison figures.

Plots use evaluator truth only for post-hoc comparison. Gyro/ds were exactly
recovered from archived predictor traces by analyze_cases.py.
"""
from pathlib import Path
import argparse,json
import numpy as np,pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
ROOT=Path(__file__).resolve().parent
C={
 'gt':'#192938','off':'#2872b8','on':'#be6434','imu':'#167761','s':'#916caf', 'minor':'#788b9d'
}
plt.rcParams.update({'font.family':'NanumGothic','font.size':10,'axes.titlesize':11.7,'axes.labelsize':9.2,'legend.fontsize':7.6,
                     'axes.unicode_minus':False,'figure.facecolor':'#fafcff','axes.facecolor':'white','savefig.facecolor':'#fafcff','axes.grid':True,'grid.alpha':.17})

def rawDR(w,yaw0,x0,y0,use_bg):
 yy=[yaw0];xs=[x0];ys=[y0]
 for i in range(1,len(w)):
  row=w.iloc[i];prev=w.iloc[i-1]
  dt=row.t_s-prev.t_s
  g=float(row.gyro_increment_rad)-(np.radians(prev.bias_off_deg_s)*dt if use_bg else 0)
  mid=yy[-1]+g/2;sinc=np.sinc(g/(2*np.pi));ds=float(row.odom_distance_increment_m)
  xs.append(xs[-1]+ds*sinc*np.cos(mid));ys.append(ys[-1]+ds*sinc*np.sin(mid));yy.append(yy[-1]+g)
 return np.asarray(xs),np.asarray(ys),np.asarray(yy)

def align(a,ref):
 a=np.unwrap(np.asarray(a,float));return a+np.arctan2(np.sin(ref[0]-a[0]),np.cos(ref[0]-a[0]))

def render(c,d,out,span=8.0):
 k=int(c.k);t=float(c.t_s);q=d[(d.t_s>=t-span-.0001)&(d.t_s<=t+span+.0001)].sort_values('k').reset_index(drop=True)
 if len(q)<3:return False
 tt=q.t_s.to_numpy();target=q[q.k==k].iloc[0]
 yawGT=align(q.yaw_true_rad,np.asarray(q.yaw_true_rad));yawOFF=align(np.radians(q.yaw_off_deg),yawGT);yawON=align(np.radians(q.yaw_on_deg),yawGT)
 xgt,ygt,_=rawDR(q,yawGT[0],q.x_true.iloc[0],q.y_true.iloc[0],False)
 xdr,ydr,yawdr=rawDR(q,yawOFF[0],q.x_off_m.iloc[0],q.y_off_m.iloc[0],True)
 _,_,yawgyro=rawDR(q,yawGT[0],q.x_true.iloc[0],q.y_true.iloc[0],False)
 _,_,yawcorr=rawDR(q,yawGT[0],q.x_true.iloc[0],q.y_true.iloc[0],True)
 fig,ax=plt.subplots(4,2,figsize=(17.4,13.7),layout='constrained')
 fig.suptitle(f"B-MCG #{c.route}/{c.stratum}/k{k:04d}   t={t:.1f} s   Status={c.guard_status}   beta=({c.r_beta:.3f}, {c.s_beta:.3f})",fontsize=16,fontweight='bold')
 # trajectory
 a=ax[0,0];a.plot(q.x_true,q.y_true,color=C['gt'],lw=2.8,label='GT');a.plot(q.x_off_m,q.y_off_m,color=C['off'],label='B OFF');a.plot(q.x_on_m,q.y_on_m,color=C['on'],label='B-MCG ON');
 a.plot(xgt,ygt,color=C['imu'],lw=1.5,ls='--',label='Raw IMU+odom (GT start)');a.plot(xdr,ydr,color=C['s'],lw=1.5,ls=':',label='DR+est. bg (OFF start)');a.scatter([target.x_true],[target.y_true],color='black',marker='x',s=60,zorder=5)
 a.set_aspect('equal',adjustable='datalim');a.set(xlabel='x [m]',ylabel='y [m]',title='XY trajectory (true, OFF, ON, DR)');a.legend(loc='best',ncol=2)
 # heading
 a=ax[0,1];a.plot(tt,np.degrees(yawGT),color=C['gt'],lw=2.7,label='GT');a.plot(tt,np.degrees(yawOFF),color=C['off'],label='B OFF');a.plot(tt,np.degrees(yawON),color=C['on'],label='MCG ON');a.plot(tt,np.degrees(yawgyro),color=C['imu'],ls='--',lw=1.4,label='Raw gyro (GT-aligned)');a.plot(tt,np.degrees(yawcorr),color=C['s'],ls=':',lw=1.4,label='gyro - OFF bias (GT-align)')
 a.set(xlabel='t [s]',ylabel='unwrapped yaw [deg]',title='Heading and integrated IMU');a.legend(loc='best',ncol=2)
 # gyro rate vs true and bias
 a=ax[1,0];dt=np.diff(tt);gr=np.degrees(q.gyro_increment_rad.to_numpy()[1:]/dt);gt=np.degrees(q.true_yaw_increment_rad.to_numpy()[1:]/dt)
 a.plot(tt[1:],gr,color=C['imu'],label='gyro rate (recovered)');a.plot(tt[1:],gt,color=C['gt'],ls='--',label='GT yaw rate');a.set(xlabel='t [s]',ylabel='rate [deg/s]',title='Gyroscope input vs true yaw rate')
 a2=a.twinx();a2.plot(tt,q.bias_off_deg_s,color=C['on'],alpha=.85,label='OFF estimated gyro bias');a2.set_ylabel('estimated gyro bias [deg/s]',color=C['on']);a.legend(loc='upper left');a2.legend(loc='upper right')
 # s observation
 a=ax[1,1];a.plot(tt,q.s_F,color=C['on'],lw=1.8,label='Full B s');a.plot(tt,q.s_L,color=C['gt'],ls='--',label='LoS-only B s (eval)');a.plot(tt,q.s_pred_off,color=C['off'],ls=':',label='predicted s OFF');a.plot(tt,q.e_s_mp,color=C['s'],ls='--',label='Full-LoS delta s')
 a.set(xlabel='t [s]',ylabel='s',title='Polarization s: distortion and prediction');a.legend(ncol=2)
 # range
 a=ax[2,0];a.plot(tt,q.r_observed_m,color=C['on'],label='Full B range');a.plot(tt,q.B_L*299792458/(1028*1950000),color=C['gt'],ls='--',label='LoS-only B range');a.plot(tt,q.r_pred_off_m,color=C['off'],ls=':',label='predicted range OFF');a.set(xlabel='t [s]',ylabel='range [m]',title='B range / reference / model');a.legend(ncol=2)
 # errors
 a=ax[2,1];a.plot(tt,q.heading_error_off_deg,color=C['off'],label='OFF heading err');a.plot(tt,q.heading_error_on_deg,color=C['on'],label='ON heading err');a.set(xlabel='t [s]',ylabel='signed heading error [deg]',title='Position and heading estimation errors')
 a2=a.twinx();a2.plot(tt,q.xy_error_off_cm,color=C['off'],ls=':',label='OFF XY error');a2.plot(tt,q.xy_error_on_cm,color=C['on'],ls=':',label='ON XY error');a2.set_ylabel('XY error [cm]');a.legend(loc='upper left');a2.legend(loc='upper right')
 # guard
 a=ax[3,0];a.plot(tt,q.beta_r,color=C['on'],label='beta_r');a.plot(tt,q.beta_s,color=C['imu'],label='beta_s');a.set_ylim(-.05,1.09);a.set(xlabel='t [s]',ylabel='beta',title='Guard intervention and compatibility score')
 a2=a.twinx();a2.plot(tt,q.score_r,color=C['off'],alpha=.8,ls=':',label='score r');a2.plot(tt,q.score_s,color=C['s'],alpha=.8,ls='--',label='score s');a2.set_ylabel('score');a.legend(loc='upper left');a2.legend(loc='upper right')
 # CIR features
 a=ax[3,1];a.plot(tt,q.local_complex_distortion,color=C['off'],label='CIR local complex distortion');a.set(xlabel='t [s]',ylabel='local distortion index',title='CIR-derived features (NOT raw waveform)')
 a2=a.twinx();a2.plot(tt,q.B_F-q.B_L,color=C['on'],label='tap delta Full-LoS');a2.plot(tt,q.e_s_mp,color=C['imu'],ls='--',label='delta s Full-LoS');a2.set_ylabel('tap offset / delta s');a.legend(loc='upper left');a2.legend(loc='upper right')
 for one in ax.ravel():
  if one is ax[0,0]:continue
  one.axvline(t,color='#3e5162',alpha=.62,ls='--',lw=1)
 footer=(f"Posthoc: guard harm heading={target.guard_harm_heading_deg2:+.5f} deg², XY={target.guard_harm_xy_cm2:+.3f} cm²; "
         f"B update harm heading={target.B_update_harm_heading_deg2:+.5f} deg²; e_s_mp={target.e_s_mp:+.4f}. "
         "Only first GT pose aligns idealized IMU/DR curve; no evaluator data in online guard. ")
 fig.text(.5,-.002,footer,ha='center',fontsize=8.6,color='#536575')
 out.parent.mkdir(parents=True,exist_ok=True)
 fig.savefig(out,dpi=128,bbox_inches='tight');plt.close(fig)
 return True

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=ROOT/'panels');ap.add_argument('--max',type=int,default=115);args=ap.parse_args()
    cat=pd.read_csv(ROOT/'CASE_CATALOG.csv',encoding='utf-8-sig');data=pd.read_csv(ROOT/'FULL_ENRICHED_6272.csv',encoding='utf-8-sig')
    d={(r,st):g.sort_values('k') for (r,st),g in data.groupby(['route','stratum'])}
    # All 23 actual interventions. Add 8 per class, respecting route stratum representation.
    chosen=cat[cat.categories.str.contains('ACTIVE_ALL')].copy()
    more=[]
    cats=['COMPATIBLE_HARM_HEADING','COMPATIBLE_HARM_XY','COMPATIBLE_CORRUPTED_S','UNKNOWN_HARM_HEADING',
          'UNKNOWN_HARM_XY','BENEFICIAL_FULL_HEADING','BENEFICIAL_FULL_XY','CLEAN_TAP_S_DISTORTED','TAP_CHANGED_S_STABLE',
          'LOW_NIS_HIGH_NEES','GYRO_BIAS_EXTREME','RF_SMALL_AFTER_LARGE','HIGH_S_MP']
    for group in cats:
       sub=cat[cat.categories.str.contains(group)].copy()
       # balance path+stratum; case order source-fixed and not optimized by result
       sub=sub.sort_values(['route','stratum','k'])
       take=sub.groupby(['route','stratum']).head(2)
       more.extend(list(take.index))
    chosen=pd.concat([chosen,cat.loc[sorted(set(more))]],ignore_index=True).drop_duplicates('id')
    if len(chosen)>args.max:
        active=chosen[chosen.categories.str.contains('ACTIVE_ALL')]
        remaining=chosen[~chosen.categories.str.contains('ACTIVE_ALL')].sort_values(['primary_category','route','stratum','k']).head(args.max-len(active))
        chosen=pd.concat([active,remaining])
    out=[]
    for i,(_,c) in enumerate(chosen.iterrows()):
        stem=f'{c.route}_{c.stratum}_k{int(c.k):04d}'
        target=args.out/f'{stem}.png'
        if (target.exists() or render(c,d[(c.route,c.stratum)],target)):out.append({'case_id':c.id,'file':f'panels/{target.name}','categories':c.categories,'route':c.route,'stratum':c.stratum,'k':int(c.k)})
        if (i+1)%15==0:print('rendered',i+1,'of',len(chosen),flush=True)
    (ROOT/'PANEL_MANIFEST.json').write_text(json.dumps({'status':'RENDERED_FROM_ORIGINAL_STORED_TRACES','panels':out},ensure_ascii=False,indent=2)+'\n')
    print('STATIC_PANELS',len(out))

if __name__=='__main__':main()
