"""Actual pinned GTSAM fixed-lag API/covariance and exact motion preflight.

Run in isolated Linux Python with gtsam==4.2 and numpy==1.26.4. No RF data.
Global-coordinate Vector3 poses avoid untested Pose2 tangent conversion.
Motion uses a latent Vector2 input error and an exact Constrained.All(3)
SE2 equality; no diagonal replacement of rank-two process covariance.
"""
from __future__ import annotations
import argparse
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import sys
import time
import traceback

import numpy as np
import gtsam as g
import gtsam_unstable as u


def arc(p, ds, theta):
    half = theta / 2
    scale = np.sinc(half / np.pi)
    return np.array([p[0]+ds*scale*math.cos(p[2]+half),
                     p[1]+ds*scale*math.sin(p[2]+half),
                     (p[2]+theta+np.pi) % (2*np.pi)-np.pi])


def derivative(fun, x):
    step = 1e-6
    return np.column_stack([(fun(x+np.eye(len(x))[j]*step)-
                             fun(x-np.eye(len(x))[j]*step))/(2*step)
                            for j in range(len(x))])


def timestamp(keys, t):
    result = u.FixedLagSmootherKeyTimestampMap()
    for key in keys:
        result.insert((key, float(t)))
    return result


def vector_difference(k0, k1, displacement, covariance):
    def callback(_, values, jac):
        if jac is not None:
            jac[0] = -np.eye(len(displacement))
            jac[1] = np.eye(len(displacement))
        return values.atVector(k1)-values.atVector(k0)-displacement
    return g.CustomFactor(g.noiseModel.Gaussian.Covariance(covariance), [k0,k1], callback)


def linear_chain_check():
    smooth = u.IncrementalFixedLagSmoother(2.)
    information = np.zeros((50,50))
    means, covariance_errors, times, sizes = [], [], [], []
    information[0,0] = 1/.3
    for k in range(50):
        graph, values = g.NonlinearFactorGraph(), g.Values()
        key = g.symbol('x',k)
        values.insert(key,np.array([float(k)]))
        if k == 0:
            graph.add(g.PriorFactorVector(key,np.array([0.]),g.noiseModel.Isotropic.Sigma(1,math.sqrt(.3))))
        else:
            graph.add(vector_difference(g.symbol('x',k-1),key,np.array([1.]),np.array([[.2]])))
            information[k-1,k-1] += 1/.2
            information[k,k] += 1/.2
            information[k-1,k] -= 1/.2
            information[k,k-1] -= 1/.2
        graph.add(g.PriorFactorVector(key,np.array([float(k)]),g.noiseModel.Isotropic.Sigma(1,math.sqrt(.4))))
        information[k,k] += 1/.4
        start=time.perf_counter()
        smooth.update(graph,values,timestamp([key],k))
        times.append(time.perf_counter()-start)
        actual = smooth.getISAM2().marginalCovariance(key)
        expected=np.linalg.inv(information[:k+1,:k+1])[-1,-1]
        covariance_errors.append(abs(actual[0,0]-expected))
        means.append(abs(smooth.calculateEstimate().atVector(key)[0]-k))
        sizes.append(smooth.calculateEstimate().size())
        if np.linalg.eigvalsh(actual)[0] <= 0:
            raise RuntimeError('Nonpositive marginal covariance')
    if max(covariance_errors)>1e-10 or max(means)>1e-10 or max(sizes)>4:
        raise RuntimeError('Fixed-lag/Schur parity failed')
    return dict(status='PASS',updates=50,lag=2.,max_active_values=max(sizes),
                max_mean_error=max(means),max_covariance_error=max(covariance_errors),
                covariance_api='getISAM2().marginalCovariance(key)',
                max_update_seconds=max(times),mean_update_seconds=float(np.mean(times)))


def exact_motion_factor(previous, current, bias, error, ds, gyro, dt):
    def callback(_, values, jac):
        p=values.atVector(previous)
        eps=values.atVector(error)
        bg=values.atDouble(bias)
        def predicted(pose, noise, b):
            return arc(pose,ds+noise[0],gyro+noise[1]-b*dt)
        if jac is not None:
            jac[0]=-derivative(lambda a: predicted(a,eps,bg),p)
            jac[1]=np.eye(3)
            jac[2]=-derivative(lambda a: predicted(p,eps,a[0]),np.array([bg]))
            jac[3]=-derivative(lambda a: predicted(p,a,bg),eps)
        residual=values.atVector(current)-predicted(p,eps,bg)
        residual[2]=(residual[2]+np.pi)%(2*np.pi)-np.pi
        return residual
    return g.CustomFactor(g.noiseModel.Constrained.All(3),
                          [previous,current,bias,error],callback)


def exact_motion_check():
    smooth=u.IncrementalFixedLagSmoother(.6)
    pk,bk=g.symbol('p',0),g.symbol('b',0)
    x=np.array([1.,2.,.4,.03])
    prior=np.diag([.01,.01,math.radians(5)**2,math.radians(.1)**2])
    graph,values=g.NonlinearFactorGraph(),g.Values()
    values.insert(pk,x[:3]); values.insert(bk,float(x[3]))
    graph.add(g.PriorFactorVector(pk,x[:3],g.noiseModel.Gaussian.Covariance(prior[:3,:3])))
    graph.add(g.PriorFactorDouble(bk,float(x[3]),g.noiseModel.Isotropic.Sigma(1,math.sqrt(prior[3,3]))))
    smooth.update(graph,values,timestamp([pk,bk],0.))
    covariance_error=None
    times=[]
    for k in range(1,31):
        ds,gyro,dt=.2,.015,.2
        key,ek=g.symbol('p',k),g.symbol('e',k)
        q=np.diag([2e-5*abs(ds),math.radians(.015)**2*dt])
        predicted=arc(x[:3],ds,gyro-x[3]*dt)
        graph,values=g.NonlinearFactorGraph(),g.Values()
        values.insert(key,predicted); values.insert(ek,np.zeros(2))
        graph.add(g.PriorFactorVector(ek,np.zeros(2),g.noiseModel.Gaussian.Covariance(q)))
        graph.add(exact_motion_factor(pk,key,bk,ek,ds,gyro,dt))
        start=time.perf_counter()
        # Refresh the global constant bias timestamp; do not introduce bias RW.
        smooth.update(graph,values,timestamp([key,ek,bk],k*dt))
        times.append(time.perf_counter()-start)
        cov=smooth.getISAM2().marginalCovariance(key)
        try:
            estimate=smooth.getISAM2().calculateEstimateVector(key)
        except Exception as e:
            raise RuntimeError(f'Exact motion estimate failed at update {k}, t={k*dt}: {e}') from e
        np.testing.assert_allclose(estimate,predicted,atol=1e-9)
        if k==1:
            f=derivative(lambda v:arc(v[:3],ds,gyro-v[3]*dt),x)
            gg=derivative(lambda v:arc(x[:3],ds+v[0],gyro+v[1]-x[3]*dt),np.zeros(2))
            process=gg@q@gg.T
            if np.linalg.matrix_rank(process,tol=1e-14)!=2:
                raise RuntimeError('Motion process covariance not rank two')
            expected=f@prior@f.T+process
            covariance_error=float(np.max(np.abs(cov-expected)))
            if covariance_error>1e-8:
                raise RuntimeError(f'Exact constrained motion covariance mismatch {covariance_error}')
        if np.linalg.eigvalsh(cov)[0]<=0:
            raise RuntimeError('Invalid pose marginal in exact motion graph')
        pk=key;x=np.r_[predicted,x[3]]
    return dict(status='PASS',updates=30,lag=.6,process_noise_rank=2,
                first_step_covariance_error=covariance_error,
                noise_representation='LATENT_INPUT_ERROR2_EXACT_SE2_CONSTRAINT3',
                pose_coordinates='GLOBAL_VECTOR3',bias_model='GLOBAL_CONSTANT_RW_ZERO',
                max_update_seconds=max(times),final_active_values=smooth.timestamps().size())


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    report=dict(python=sys.executable,python_version=platform.python_version(),
                gtsam=importlib.metadata.version('gtsam'),numpy=np.__version__,
                status='NOT_READY',scientific_PASS=False)
    for name,fun in [('linear_fixedlag',linear_chain_check),('exact_motion',exact_motion_check)]:
        try:
            report[name]=fun()
        except Exception as e:
            report[name]=dict(status='FAIL',error=repr(e),traceback=traceback.format_exc())
    if all(report[x]['status']=='PASS' for x in ('linear_fixedlag','exact_motion')):
        report['status']='PREFLIGHT_PASS'
    path=args.out/'GTSAM_PREFLIGHT.json'
    if path.exists():
        raise FileExistsError('Preserve prior receipt')
    path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    return 0 if report['status']=='PREFLIGHT_PASS' else 1


if __name__=='__main__':
    raise SystemExit(main())
