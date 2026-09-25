"""Finite panels, antenna spheres, and certified continuous yaw sweeps.

SAT separation plus a Lipschitz displacement bound certifies entire intervals.
Unresolved intervals reject; endpoint sampling alone never grants clearance.
"""
import math


EPS=1e-8
CLEARANCE=1e-4
MAX_SWEEP_DEPTH=20


def dot(a,b):return sum(x*y for x,y in zip(a,b))
def sub(a,b):return [x-y for x,y in zip(a,b)]
def norm(a):return math.sqrt(dot(a,a))
def rotate(v,yaw):
    c,s=math.cos(yaw),math.sin(yaw)
    return [c*v[0]-s*v[1],s*v[0]+c*v[1],v[2]]


def transform(local, position, yaw):
    r={k:rotate(local[k],yaw) for k in ('center','normal','u','v')}
    r['center']=[x+y for x,y in zip(r['center'],position)]
    r['half']=list(local['half'])
    return r


def panel_basis(p):
    for key in ('center','u','v','normal'):
        if len(p[key])!=3 or not all(math.isfinite(x) for x in p[key]):raise ValueError('PANEL_VECTOR')
    axes=[p[x] for x in ('u','v','normal')]
    if any(abs(dot(a,b)-(1. if i==j else 0.))>1e-10 for i,a in enumerate(axes) for j,b in enumerate(axes)):
        raise ValueError('PANEL_BASIS')
    if len(p['half'])!=2 or min(p['half'])<=0:raise ValueError('PANEL_SIZE')


def corners(p):
    return [[p['center'][i]+a*p['half'][0]*p['u'][i]+b*p['half'][1]*p['v'][i] for i in range(3)]
            for a,b in ((-1,-1),(-1,1),(1,-1),(1,1))]


def surface_distance(q,p):
    d=sub(q,p['center'])
    return math.sqrt(dot(d,p['normal'])**2+sum(max(0.,abs(dot(d,a))-h)**2 for a,h in zip((p['u'],p['v']),p['half'])))


def separated(p,box,margin):
    """Vertical rectangle versus AABB, conservatively dilated by margin."""
    c=[(a+b)/2 for a,b in zip(*box)];h=[(b-a)/2+margin for a,b in zip(*box)]
    for axis in ([1,0,0],[0,1,0],[0,0,1],p['u'],p['normal']):
        rp=sum(abs(dot(axis,d))*v for d,v in zip((p['u'],p['v']),p['half']))
        rb=sum(abs(x)*v for x,v in zip(axis,h))
        if abs(dot(sub(p['center'],c),axis))>rp+rb+EPS:return True
    return False


def panel_clear(p,size,solids,anchors,radius,uncertainty=0.):
    margin=CLEARANCE+uncertainty
    if any(not all(margin<x<s-margin for x,s in zip(q,size)) for q in corners(p)):return False
    if any(not separated(p,b,margin) for b in solids):return False
    if any(surface_distance(a,p)<=radius+margin for a in anchors):return False
    return True


def continuous_panel_clear(local,a,b,ya,yb,size,solids,anchors,radius,depth=0):
    """Each local point moves at most |b-a|/2 + R*|yb-ya|/2 from midpoint."""
    m=[(x+y)/2 for x,y in zip(a,b)]; ym=(ya+yb)/2
    panel=transform(local,m,ym)
    # Max over vertices bounds every point of this convex finite panel.
    R=max(norm(q) for q in corners(local))
    movement=.5*norm(sub(b,a))+.5*R*abs(yb-ya)
    if panel_clear(panel,size,solids,anchors,radius,movement):return True
    if not panel_clear(panel,size,solids,anchors,radius):return False
    if depth>=MAX_SWEEP_DEPTH:return False
    return continuous_panel_clear(local,a,m,ya,ym,size,solids,anchors,radius,depth+1) and continuous_panel_clear(local,m,b,ym,yb,size,solids,anchors,radius,depth+1)


def segment_box(a,b,lo,hi):
    t0,t1=0.,1.
    for x,d,l,h in zip(a,sub(b,a),lo,hi):
        if abs(d)<1e-15:
            if x<l or x>h:return False
        else:
            r,s=sorted(((l-x)/d,(h-x)/d));t0=max(t0,r);t1=min(t1,s)
            if t0>t1:return False
    return True


def antenna_clear(points,anchors,size,solids,radius):
    if radius<=0 or not math.isfinite(radius):raise ValueError('ANTENNA_BOUND_REQUIRED')
    d=radius+CLEARANCE
    for q in points+anchors:
        if len(q)!=3 or not all(math.isfinite(x) and d<x<s-d for x,s in zip(q,size)):
            raise ValueError('ANTENNA_ROOM_COLLISION')
    expanded=[([x-d for x in lo],[x+d for x in hi]) for lo,hi in solids]
    for q in anchors:
        if any(segment_box(q,q,*b) for b in expanded):raise ValueError('ANCHOR_SOLID_COLLISION')
    segments=list(zip(points,points[1:])) or [(points[0],points[0])]
    if any(segment_box(a,b,*box) for a,b in segments for box in expanded):raise ValueError('ANTENNA_SWEPT_COLLISION')
    if any(segment_box(a,b,[x-2*d for x in anchor],[x+2*d for x in anchor]) for a,b in segments for anchor in anchors):
        raise ValueError('TX_RX_ENVELOPE_COLLISION')


def fixed_panel_clear(p,points,anchors,size,solids,radius):
    panel_basis(p)
    if not panel_clear(p,size,solids,anchors,radius):raise ValueError('FIXED_PANEL_COLLISION')
    def local(q):return [dot(sub(q,p['center']),p[k]) for k in ('u','v','normal')]
    d=radius+CLEARANCE
    lo=[-p['half'][0]-d,-p['half'][1]-d,-d];hi=[p['half'][0]+d,p['half'][1]+d,d]
    segments=list(zip(points,points[1:])) or [(points[0],points[0])]
    if any(segment_box(local(a),local(b),lo,hi) for a,b in segments):raise ValueError('TAG_PANEL_SWEPT_COLLISION')


def metal_candidates(minimum):
    # Fixed before RF; preserve 1.2 x 1.5 m. Distance is to the finite surface.
    for distance in (minimum+.02,minimum+.12,minimum+.27,minimum+.47):
        for i in range(8):
            t=i*math.pi/4;n=[math.cos(t),math.sin(t),0.]
            yield dict(center=[distance*n[0],distance*n[1],0.],normal=n,
                       u=[-n[1],n[0],0.],v=[0.,0.,1.],half=[.6,.75])


def check_metal(local,points,yaw,anchors,size,solids,radius,minimum):
    panel_basis(local)
    distance=surface_distance([0.,0.,0.],local)
    if distance<minimum-EPS:raise ValueError('D5_FAR_FIELD_DISTANCE')
    # Fixed anchors also use the FFD outside their prescribed far-field bound.
    anchor_bound=max(radius,minimum)
    for q,y in zip(points,yaw):
        if not panel_clear(transform(local,q,y),size,solids,anchors,anchor_bound):raise ValueError('D5_FRAME_COLLISION')
    for i in range(len(points)-1):
        if not continuous_panel_clear(local,points[i],points[i+1],yaw[i],yaw[i+1],size,solids,anchors,anchor_bound):
            raise ValueError('D5_CONTINUOUS_SWEEP')
    return distance
