"""Finite air-boundary extraction and exhaustive planar reflection image candidates.

Union occupancy on the two sides of each supporting plane removes internal
prism triangulation faces. Candidate enumeration is independent of launch seeds.
Actual volume visibility and material transport must still validate candidates.
"""
from dataclasses import dataclass
import numpy as np
from shapely.geometry import MultiPoint,Polygon
from shapely.ops import unary_union
from shapely import contains_xy,intersects_xy

EDGES=((0,1),(1,2),(2,0),(3,4),(4,5),(5,3),(0,3),(1,4),(2,5))

@dataclass
class AirFace:
    normal: np.ndarray
    offset: float
    u: np.ndarray
    v: np.ndarray
    polygon: object

    def contains(self,points):
        points=np.asarray(points)
        return intersects_xy(self.polygon,points@self.u,points@self.v)


def air_faces(scene,tolerance=1e-10):
    vertices=np.array([np.vstack((p.triangle,np.asarray(p.triangle)-np.asarray(p.normal)*p.thickness)) for p in scene.prisms])
    planes={}
    def add(n,d):
        n=np.asarray(n,float);sign=1 if n[np.argmax(abs(n))]>0 else -1;n=sign*n;d=sign*d
        planes.setdefault(tuple(np.round(np.r_[n,d],10)),(n,d))
    for p in scene.prisms:
        for n,d in p.planes():add(n,d)
    for t in scene.ideal_surfaces:
        n=np.cross(t.triangle[1]-t.triangle[0],t.triangle[2]-t.triangle[0]);n/=np.linalg.norm(n);add(n,n@t.triangle[0])
    faces=[]
    for key,(n,d) in sorted(planes.items()):
        u=np.cross(n,np.eye(3)[np.argmin(abs(n))]);u/=np.linalg.norm(u);v=np.cross(n,u)
        plus=[];minus=[];ideals=[]
        if len(vertices):
            signed=vertices@n-d
            candidates=np.flatnonzero((signed.min(axis=1)<=tolerance)&(signed.max(axis=1)>=-tolerance))
            for j in candidates:
                vv=vertices[j];s=signed[j];points=[vv[k] for k in np.flatnonzero(abs(s)<=tolerance)]
                for a,b in EDGES:
                    if s[a]*s[b]<0 and abs(s[a])>tolerance and abs(s[b])>tolerance:points.append(vv[a]+s[a]/(s[a]-s[b])*(vv[b]-vv[a]))
                if len(points)<3:continue
                points=np.asarray(points);poly=MultiPoint(np.column_stack((points@u,points@v))).convex_hull
                if poly.area<=1e-12:continue
                if max(s)>tolerance:plus.append(poly)
                if min(s)<-tolerance:minus.append(poly)
        for t in scene.ideal_surfaces:
            if np.max(abs(t.triangle@n-d))<=tolerance:ideals.append(Polygon(np.column_stack((t.triangle@u,t.triangle@v))))
        poly=unary_union(plus).symmetric_difference(unary_union(minus))
        if ideals:poly=unary_union([poly,*ideals])
        if poly.area>1e-12:faces.append(AirFace(n,float(d),u,v,poly))
    return faces


def image_candidates(faces,tx,rx,max_depth=3):
    """Exhaust every ordered finite-face sequence, vectorized by first face.

    Images and back intersections are geometric candidates. Neither random
    seeds nor nonlinear connection searches are used in this enumeration.
    """
    tx=np.asarray(tx,float);rx=np.asarray(rx,float)
    if max_depth<0 or max_depth>3:raise ValueError('SUPPORTED_DEPTH_ZERO_TO_THREE')
    yield (),np.array([tx,rx])
    count=len(faces)
    if not count or not max_depth:return
    normals=np.array([f.normal for f in faces]);offsets=np.array([f.offset for f in faces])
    def batch(sequences):
        size,depth=sequences.shape;images=[np.tile(tx,(size,1))]
        for j in range(depth):
            nn=normals[sequences[:,j]];dd=offsets[sequences[:,j]];last=images[-1]
            images.append(last-2*(np.einsum('ij,ij->i',nn,last)-dd)[:,None]*nn)
        current=np.tile(rx,(size,1));alive=np.ones(size,bool);reverse=[]
        for j in range(depth-1,-1,-1):
            idx=sequences[:,j];nn=normals[idx];delta=images[j+1]-current;den=np.einsum('ij,ij->i',nn,delta)
            fraction=np.divide(offsets[idx]-np.einsum('ij,ij->i',nn,current),den,out=np.full(size,np.nan),where=abs(den)>=1e-14)
            alive&=(fraction>0)&(fraction<1);hit=current+fraction[:,None]*delta
            for k in np.unique(idx[alive]):
                selected=np.flatnonzero(alive&(idx==k));alive[selected]&=faces[k].contains(hit[selected])
            reverse.append(hit);current=hit
            if not alive.any():return
        for i in np.flatnonzero(alive):yield tuple(int(x) for x in sequences[i]),np.array([tx,*[p[i] for p in reverse[::-1]],rx])
    for first in range(count):
        yield from batch(np.array([[first]],int))
        if max_depth>=2:
            second=np.array([j for j in range(count) if j!=first]);yield from batch(np.column_stack((np.full(len(second),first),second)))
        if max_depth>=3:
            second,third=np.meshgrid(np.arange(count),np.arange(count),indexing='ij');valid=(second!=first)&(second!=third)
            yield from batch(np.column_stack((np.full(valid.sum(),first),second[valid],third[valid])))
