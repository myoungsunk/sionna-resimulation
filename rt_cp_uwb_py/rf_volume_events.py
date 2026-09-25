"""Finite-volume boundary events and a specified plane-wave branch evaluator.

No candidate search, receiver connection, spreading factor or CIR is provided.
Physical volumes use a union of same-material convex triangle prisms. Different
materials may touch but cannot have positive-volume overlap along the query.
"""
from dataclasses import dataclass
import numpy as np
from .rf_junctions import prism_ray_interval,merge_medium_intervals,vector_interface,C0

@dataclass(frozen=True)
class VolumePrism:
    triangle: np.ndarray
    normal: np.ndarray
    thickness: float
    material: str
    owner: str

    def planes(self):
        tri=np.asarray(self.triangle,float);n=np.asarray(self.normal,float);n=n/np.linalg.norm(n)
        result=[(n,float(n@tri[0])),(-n,float(-n@(tri[0]-n*self.thickness)))]
        for a,b in zip(tri,np.roll(tri,-1,axis=0)):
            q=np.cross(b-a,n);q/=np.linalg.norm(q)
            if q@(tri.mean(0)-a)>0:q=-q
            result.append((q,float(q@a)))
        return result

@dataclass(frozen=True)
class IdealTriangle:
    triangle: np.ndarray
    material: str
    owner: str
    epsilon: complex | None = None  # None means PEC; otherwise reflection-only halfspace.


class VolumeScene:
    def __init__(self,prisms,tolerance=1e-9,ideal_surfaces=()):
        self.prisms=list(prisms);self.tolerance=tolerance
        self.ideal_surfaces=list(ideal_surfaces)

    def _union_boundary_normal(self, point, direction, prior, medium):
        """Classify local open face sectors of the material union.

        Active prism inequalities define tangent cones at the hit. On each
        candidate plane, their intersection lines partition its tangent plane
        into open angular sectors. Compare material occupancy on both sides
        in every sector, using lexicographic (tangent, normal) directions.
        This removes internal triangulation faces without nudging the hit or
        selecting an arbitrary normal; genuine edges remain ambiguous.
        """
        cones=[];candidates=[];owners=set();angular_tol=1e-10
        for prism in self.prisms:
            planes=prism.planes()
            residual=np.array([n@point-d for n,d in planes])
            if np.any(residual>self.tolerance):continue
            active=np.array([n for (n,_),r in zip(planes,residual) if abs(r)<=self.tolerance]).reshape(-1,3)
            cones.append((prism.material,active))
            if prism.material in (prior,medium):owners.add(prism.owner)
            for normal in active:
                if not any(abs(normal@old)>1-1e-12 for old in candidates):candidates.append(normal)
        all_active=[n for _,active in cones for n in active]

        def material_on_side(tangent, normal):
            occupied=set()
            for material,active in cones:
                first=active@tangent;second=active@normal
                inside=np.all((first < -angular_tol) | ((abs(first)<=angular_tol) & (second<=angular_tol)))
                if inside:occupied.add(material)
            if len(occupied)>1:raise ValueError('OVERLAPPING_DISTINCT_MEDIA')
            return next(iter(occupied)) if occupied else 'air'

        normals=[]
        for normal in candidates:
            axis=np.eye(3)[np.argmin(abs(normal))]
            u=np.cross(normal,axis);u/=np.linalg.norm(u);v=np.cross(normal,u)
            angles=[]
            for plane in all_active:
                x,y=plane@u,plane@v
                if np.hypot(x,y)>angular_tol:
                    angle=np.arctan2(-x,y)%(2*np.pi)
                    angles.extend([angle,(angle+np.pi)%(2*np.pi)])
            angles=sorted(set(angles)) if angles else [0.]
            exposed=False
            for left,right in zip(angles,angles[1:]+[angles[0]+2*np.pi]):
                if right-left<=angular_tol:continue
                angle=(left+right)/2;tangent=np.cos(angle)*u+np.sin(angle)*v
                pair={material_on_side(tangent,normal),material_on_side(tangent,-normal)}
                if len(pair)==1:continue  # Same material on both sides: internal partition.
                if pair!={prior,medium}:raise ValueError('AMBIGUOUS_EDGE_OR_CORNER_NORMAL')
                exposed=True
            if exposed:normals.append(normal if normal@direction>0 else -normal)
        if len(normals)!=1 or abs(normals[0]@direction)<=angular_tol:
            raise ValueError('AMBIGUOUS_EDGE_OR_CORNER_NORMAL')
        return normals[0],sorted(owners)

    def next_boundary(self,origin,direction,current_material):
        hit=self._next_volume_boundary(origin,direction,current_material)
        origin=np.asarray(origin,float);direction=np.asarray(direction,float)
        direction=direction/np.linalg.norm(direction)
        for surface in self.ideal_surfaces:
            tri=np.asarray(surface.triangle,float)
            n=np.cross(tri[1]-tri[0],tri[2]-tri[0]);n/=np.linalg.norm(n)
            denom=n@direction
            if abs(denom)<1e-12:continue
            distance=float(n@(tri[0]-origin)/denom)
            if distance<=self.tolerance:continue
            point=origin+distance*direction
            uv=np.linalg.lstsq(np.column_stack((tri[1]-tri[0],tri[2]-tri[0])),point-tri[0],rcond=None)[0]
            if min(uv)<-self.tolerance or sum(uv)>1+self.tolerance:continue
            if hit is not None and abs(distance-hit['distance_m'])<=self.tolerance:
                if hit.get('ideal') and hit['to_material']==surface.material and abs(abs(n@hit['normal'])-1)<1e-7:
                    hit['owners']=sorted(set(hit['owners']+[surface.owner]));continue
                raise ValueError('AMBIGUOUS_COINCIDENT_IDEAL_BOUNDARY')
            if hit is None or distance<hit['distance_m']:
                hit={'distance_m':distance,'point':point,'normal':n if denom>0 else -n,
                     'from_material':current_material,'to_material':surface.material,
                     'owners':[surface.owner],'ideal':True,'ideal_epsilon':surface.epsilon}
        return hit

    def _next_volume_boundary(self,origin,direction,current_material):
        origin=np.asarray(origin,float);direction=np.asarray(direction,float)
        if not np.isfinite([*origin,*direction]).all() or np.linalg.norm(direction)==0:raise ValueError('INVALID_RAY')
        direction=direction/np.linalg.norm(direction);intervals=[];tol=self.tolerance
        for p in self.prisms:
            hit=prism_ray_interval(p.triangle,p.normal,p.thickness,origin,direction)
            if hit and hit[1]>tol:
                intervals.append((max(0.,hit[0]),hit[1],p.material,p.owner))
        if not intervals:
            if current_material!='air':raise ValueError('MEDIUM_STATE_NOT_IN_VOLUME')
            return None
        far=max(x[1] for x in intervals);ticks=sorted({0.,far+1.,*[float(x) for r in intervals for x in r[:2]]})
        # Use the existing union validator for explicit material-overlap rejection.
        merge_medium_intervals(intervals,tolerance=tol)
        prior=current_material
        first=True
        for lo,hi in zip(ticks,ticks[1:]):
            if hi-lo<=tol:continue
            mid=(lo+hi)/2;materials={r[2] for r in intervals if r[0]<mid<r[1]}
            if len(materials)>1:raise ValueError('OVERLAPPING_DISTINCT_MEDIA')
            medium=next(iter(materials)) if materials else 'air'
            if first:
                first=False
                if medium!=current_material:raise ValueError('MEDIUM_STATE_MISMATCH')
            if medium!=prior:
                pos=origin+lo*direction
                normal,owners=self._union_boundary_normal(pos,direction,prior,medium)
                return {'distance_m':lo,'point':pos,'normal':normal,'from_material':prior,'to_material':medium,'owners':owners}
            prior=medium
        return None

    def evaluate_branch(self,origin,k_dimensionless,electric_field,material,frequency_hz,epsilon_at_frequency,choices):
        """Follow a specified R/T branch through real bounded volumes.

        A complex wave vector and vector E are carried between events. Energy
        direction is the local time-averaged Poynting vector of that plane wave.
        Edge hits and unsupported root branches raise an error. These local
        geometric-optics events do not qualify complete finite-body wave fields.
        """
        pos=np.asarray(origin,float);k=np.asarray(k_dimensionless,complex);e=np.asarray(electric_field,complex);events=[]
        if frequency_hz<=0:raise ValueError('FREQUENCY')
        for choice in choices:
            if choice not in ['R','T']:raise ValueError('BRANCH_MUST_BE_R_OR_T')
            h=np.cross(k,e);energy=np.real(np.cross(e,np.conj(h)));norm=np.linalg.norm(energy)
            if norm<1e-25:raise ValueError('VANISHING_PLANE_WAVE_ENERGY')
            direction=energy/norm;hit=self.next_boundary(pos,direction,material)
            if hit is None:break
            delta=hit['point']-pos;factor=np.exp(-1j*2*np.pi*frequency_hz/C0*(k@delta))
            if abs(factor)>1+1e-8:raise ValueError('GROWING_PROPAGATION_BRANCH')
            incident=e*factor;eps_in=epsilon_at_frequency(material,frequency_hz)
            if hit.get('ideal'):
                if choice!='R':raise ValueError('IDEAL_BOUNDARY_REFLECTION_ONLY')
                if material!='air':raise ValueError('IDEAL_BOUNDARY_IN_NONAIR_UNSUPPORTED')
                if hit['ideal_epsilon'] is None:
                    n=hit['normal'];kr=k-2*(k@n)*n;er=-incident+2*(incident@n)*n
                    result={'k_reflected':kr,'e_reflected':er,'boundary_residual':float(np.linalg.norm(np.cross(n,incident+er))),
                            'tangential_k_residual':float(np.linalg.norm(np.cross(n,k-kr)))}
                else:
                    result=vector_interface(k,incident,eps_in,hit['ideal_epsilon'],hit['normal'])
            else:
                eps_out=epsilon_at_frequency(hit['to_material'],frequency_hz)
                result=vector_interface(k,incident,eps_in,eps_out,hit['normal'])
            if choice=='T' and result['normal_flux_transmitted']<=1e-12*max(1e-25,float(np.linalg.norm(incident)**2)):
                raise ValueError('EVANESCENT_TRANSMISSION_IS_NOT_A_PROPAGATING_RAY')
            k_next=result['k_transmitted'] if choice=='T' else result['k_reflected'];e_next=result['e_transmitted'] if choice=='T' else result['e_reflected']
            events.append({**hit,'branch':choice,'propagation_factor':factor,'incident_k':k.copy(),'outgoing_k':k_next.copy(),
                'incident_field':incident,'outgoing_field':e_next.copy(),'boundary_residual':result['boundary_residual'],
                'tangential_k_residual':result['tangential_k_residual']})
            material=hit['to_material'] if choice=='T' else material;pos=hit['point'];k=k_next;e=e_next
        return {'events':events,'position':pos,'wavevector':k,'electric_field':e,'material':material,
            'scope':'specified local plane-wave branch; no receiver linkage or path completeness'}
