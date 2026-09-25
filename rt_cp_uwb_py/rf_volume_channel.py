"""Planar ray-tube spreading and reciprocal antenna coupling, opt-in only.

Real, positive-index traversed media are required. Lossy reflecting media are
allowed when the ray stays outside them. Lossy volume transmission, caustics,
diffraction, completeness and production/CIR admission are not established.
"""
import numpy as np
from .rf_junctions import C0, vector_interface
from .rf_volume_producer import _unit, _basis, _energy

Z0 = 376.730313668
STEPS = (1e-3, 5e-4, 2.5e-4)
CONVERGENCE_RTOL = 1e-5
GEOMETRY_ATOL_M = 1e-7
MIN_COSINE = 1e-4


def _same_interfaces(reference, actual):
    if len(reference) != len(actual):
        raise ValueError('RAY_TUBE_TOPOLOGY_CHANGED')
    for a,b in zip(reference,actual):
        if any(a[k] != b[k] for k in ('branch','from_material','to_material')):
            raise ValueError('RAY_TUBE_TOPOLOGY_CHANGED')
        n = np.asarray(a['normal'])
        if np.linalg.norm(n-b['normal']) > 1e-7 or abs(n@(a['point']-b['point'])) > GEOMETRY_ATOL_M:
            raise ValueError('RAY_TUBE_INTERFACE_PLANE_CHANGED')


def _real_segments(path, frequency_hz, epsilon):
    if not np.isfinite(frequency_hz) or frequency_hz <= 0:
        raise ValueError('POSITIVE_FREQUENCY_REQUIRED')
    media = ['air', *[e['from_material'] for e in path['events']], path['receiver_material']]
    for material in set(media):
        ep = complex(epsilon(material,frequency_hz))
        if not np.isfinite(ep) or ep.real <= 0 or abs(ep.imag) > 1e-12*max(1.,abs(ep)):
            raise ValueError('LOSSY_VOLUME_SPREADING_NOT_ESTABLISHED')
    if path['receiver_material'] != 'air' or abs(epsilon('air',frequency_hz)-1) > 1e-12:
        raise ValueError('AIR_ENDPOINT_CONTRACT')


def ray_tube_spreading(scene, path, frequency_hz, epsilon, *, angular_steps=STEPS):
    """A = sqrt(product(cos_out/cos_in) / |dA_rx/dOmega_tx|), in 1/m.

    The interface area jump cancels the compression already in plane-wave
    Fresnel fields. Nearby launches are NOT reconnected to the receiver.
    Three decreasing angular steps establish local numerical convergence.
    Defaults preserve the original stencil; callers may explicitly shrink it.
    """
    if len(angular_steps) != 3 or not all(np.isfinite(h) and h > 0 for h in angular_steps) or not all(a > b for a,b in zip(angular_steps,angular_steps[1:])):
        raise ValueError('THREE_DECREASING_POSITIVE_STEPS_REQUIRED')
    _real_segments(path,frequency_hz,epsilon)
    tx = np.asarray(path['points'][0],float); rx = np.asarray(path['points'][-1],float)
    launch = _unit(path['launch_direction']); arrival = _unit(path['arrival_energy_direction'])
    u,v = _basis(launch); ru,rv = _basis(arrival); receiver_basis = np.array([ru,rv])
    polarization = (u+1j*v)/np.sqrt(2)

    def shoot(a,b):
        direction = _unit(launch+a*u+b*v)
        field = polarization-direction*(direction@polarization)
        field /= np.linalg.norm(field)
        state = scene.evaluate_branch(tx,direction,field,'air',frequency_hz,epsilon,path['choices'])
        _same_interfaces(path['events'],state['events'])
        if state['material'] != 'air':
            raise ValueError('RAY_TUBE_RX_NOT_AIR')
        outgoing = _energy(state['wavevector'],state['electric_field'])
        cosine = float(outgoing@arrival)
        if cosine <= MIN_COSINE:
            raise ValueError('RAY_TUBE_GRAZING_RECEIVER_PLANE')
        distance = float((rx-state['position'])@arrival/cosine)
        if distance <= 0:
            raise ValueError('RAY_TUBE_BACKWARDS_RECEIVER')
        point = state['position']+distance*outgoing
        hit = scene.next_boundary(state['position'],outgoing,'air')
        if hit is not None and hit['distance_m'] <= distance+scene.tolerance:
            raise ValueError('RAY_TUBE_FINAL_SEGMENT_OCCLUDED')
        return point,state

    central,state = shoot(0.,0.)
    if np.linalg.norm(central-rx) > GEOMETRY_ATOL_M:
        raise ValueError('STALE_PATH_OR_FREQUENCY_GEOMETRY')
    area_jump = 1.
    for event in state['events']:
        ci = abs(_unit(np.real(event['incident_k']))@event['normal'])
        co = abs(_unit(np.real(event['outgoing_k']))@event['normal'])
        if min(ci,co) < MIN_COSINE:
            raise ValueError('RAY_TUBE_GRAZING_INTERFACE')
        area_jump *= co/ci
    matrices = []; gains = []
    parity = (-1)**path['choices'].count('R')
    for h in angular_steps:
        cols = [(shoot(h,0)[0]-shoot(-h,0)[0])/(2*h),
                (shoot(0,h)[0]-shoot(0,-h)[0])/(2*h)]
        jacobian = receiver_basis@np.column_stack(cols)
        det = float(np.linalg.det(jacobian)); singular = np.linalg.svd(jacobian,compute_uv=False)
        if det*parity <= 0 or singular[-1] < 1e-10 or singular[0]/singular[-1] > 1e6:
            raise ValueError('RAY_TUBE_CAUSTIC_OR_ILL_CONDITIONED')
        matrices.append(jacobian); gains.append(float(np.sqrt(area_jump/abs(det))))
    errors = [float(np.linalg.norm(b-a)/np.linalg.norm(b)) for a,b in zip(matrices,matrices[1:])]
    if max(errors) > CONVERGENCE_RTOL or not np.isfinite(gains).all():
        raise ValueError('RAY_TUBE_STEP_CONVERGENCE_FAILED')
    return {'amplitude_per_m':gains[-1], 'area_jacobian_m2_per_sr':abs(float(np.linalg.det(matrices[-1]))),
            'interface_area_jump':area_jump,'angular_steps_rad':list(angular_steps),
            'amplitude_by_step':gains,'jacobian_relative_changes':errors,
            'jacobian_m_per_rad':matrices[-1], 'maslov_phase_rad':0.,
            'scope':'noncaustic planar positive real traversed media; development validation',
            'production_admission':False}


def propagation_operator(path, frequency_hz, epsilon):
    """3x3 transverse field map including physical segment phases once.

    Use only after ray_tube_spreading has checked the path against the scene.
    Fixed verified geometry permits exact zero polarization components (e.g.
    Brewster) without trying to derive a direction from a zero Poynting vector.
    """
    _real_segments(path,frequency_hz,epsilon)
    k = np.asarray(path['launch_direction'],complex)
    operator = np.eye(3,dtype=complex)-np.outer(k,k)
    position = np.asarray(path['points'][0],float); material = 'air'
    for event in path['events']:
        if event['from_material'] != material:
            raise ValueError('PATH_MEDIUM_SEQUENCE_MISMATCH')
        operator *= np.exp(-1j*2*np.pi*frequency_hz/C0*(k@(event['point']-position)))
        n = np.asarray(event['normal'],float); branch = event['branch']
        if event.get('ideal') and event['ideal_epsilon'] is None:
            if branch != 'R' or material != 'air':
                raise ValueError('IDEAL_BOUNDARY_CONTRACT')
            operator = (-np.eye(3)+2*np.outer(n,n))@operator
            k = k-2*(k@n)*n
        else:
            ep_out = event['ideal_epsilon'] if event.get('ideal') else epsilon(event['to_material'],frequency_hz)
            if event.get('ideal') and branch != 'R':
                raise ValueError('IDEAL_BOUNDARY_CONTRACT')
            results = [vector_interface(k,operator[:,j],epsilon(material,frequency_hz),ep_out,n) for j in range(3)]
            key = 'reflected' if branch == 'R' else 'transmitted'
            operator = np.column_stack([r['e_'+key] for r in results]); k = results[0]['k_'+key]
        if branch == 'T':material = event['to_material']
        position = np.asarray(event['point'],float)
    delta = np.asarray(path['points'][-1])-position
    operator *= np.exp(-1j*2*np.pi*frequency_hz/C0*(k@delta))
    if not np.isfinite(operator).all():raise ValueError('NONFINITE_FIELD_OPERATOR')
    return operator


def incident_pattern(raw_rE, incident_power_w=1.):
    """C = rE sqrt(2 pi/(Z0 P_incident)); no efficiency or arm renormalization."""
    if not np.isfinite(incident_power_w) or incident_power_w <= 0:
        raise ValueError('POSITIVE_INCIDENT_REFERENCE_REQUIRED')
    raw = np.asarray(raw_rE,complex)
    if not np.isfinite(raw).all():raise ValueError('NONFINITE_PATTERN')
    return raw*np.sqrt(2*np.pi/(Z0*incident_power_w))


def couple_patterns(scene, path, frequency_hz, epsilon, tx_patterns, rx_emit_patterns):
    """H = lambda/(4 pi) A C_rx^T P C_tx (reciprocal emitted RX patterns).

    Columns are physical sequential port modes in world Cartesian coordinates.
    TX is evaluated along departure, RX along NEGATIVE arrival. RX uses a plain
    transpose: the historical Sionna wrapper's receive conjugation followed by
    its Hermitian contraction yields this same bilinear effective-length rule.
    """
    tx = np.asarray(tx_patterns,complex); rx = np.asarray(rx_emit_patterns,complex)
    if tx.ndim != 2 or rx.ndim != 2 or tx.shape[0] != 3 or rx.shape[0] != 3 or min(tx.shape[1],rx.shape[1]) < 1:
        raise ValueError('PATTERN_MATRIX_MUST_BE_3_BY_PORTS')
    if not np.isfinite(tx).all() or not np.isfinite(rx).all():raise ValueError('NONFINITE_PATTERN')
    for fields,direction in ((tx,path['launch_direction']),(rx,path['arrival_energy_direction'])):
        if np.linalg.norm(np.asarray(direction)@fields) > 1e-9*max(1.,np.linalg.norm(fields)):
            raise ValueError('PATTERN_NOT_TRANSVERSE')
    spreading = ray_tube_spreading(scene,path,frequency_hz,epsilon)
    operator = propagation_operator(path,frequency_hz,epsilon)
    h = (C0/frequency_hz)/(4*np.pi)*spreading['amplitude_per_m']*(rx.T@operator@tx)
    return {'H_rx_tx':h,'spreading':spreading,'field_operator':operator,
            'per_path_coefficient_available':True,'production_admission':False,
            'complete_channel_admission':False,'CIR_qualified':False,
            'power_reference':'P_rx = P_incident_tx * abs(H_rx_tx)**2 per sequential mode'}


def grid_pattern_world(theta_deg, phi_deg, e_theta, e_phi, outward_direction,
                       rotation=None, incident_power_w=1.):
    """Bilinear complex grid -> rotated Cartesian incident-referenced C.

    Caller selects an exact bank frequency. No nearest-frequency substitution,
    spectral interpolation or additional E_phi sign correction is performed.
    The pinned bank already contains its convention correction.
    """
    rotation = np.eye(3) if rotation is None else np.asarray(rotation,float)
    if rotation.shape != (3,3) or not np.isfinite(rotation).all() or not np.allclose(rotation.T@rotation,np.eye(3),atol=1e-10,rtol=0) or abs(np.linalg.det(rotation)-1)>1e-10:
        raise ValueError('INVALID_ANTENNA_ROTATION')
    direction = rotation.T@_unit(outward_direction)
    theta = np.degrees(np.arccos(np.clip(direction[2],-1,1))); phi = np.degrees(np.arctan2(direction[1],direction[0]))
    th = np.asarray(theta_deg,float); ph = np.asarray(phi_deg,float)
    if th.ndim != 1 or ph.ndim != 1 or min(len(th),len(ph))<2 or not np.isfinite(th).all() or not np.isfinite(ph).all() or np.any(np.diff(th)<=0) or np.any(np.diff(ph)<=0):
        raise ValueError('INVALID_PATTERN_GRID')
    if abs(th[0])>1e-8 or abs(th[-1]-180)>1e-8 or abs(ph[-1]-ph[0]-360)>1e-8:
        raise ValueError('FULL_SPHERE_PATTERN_REQUIRED')
    phi = (phi-ph[0])%360+ph[0]
    i = min(max(np.searchsorted(th,theta,side='right')-1,0),len(th)-2)
    j = min(max(np.searchsorted(ph,phi,side='right')-1,0),len(ph)-2)
    a = (theta-th[i])/(th[i+1]-th[i]); b = (phi-ph[j])/(ph[j+1]-ph[j])
    components = []
    for field in (e_theta,e_phi):
        field = np.asarray(field,complex)
        if field.shape != (len(th),len(ph)):raise ValueError('PATTERN_GRID_SHAPE')
        corners = field[i:i+2,j:j+2]
        if not np.isfinite(corners).all():raise ValueError('NONFINITE_PATTERN')
        components.append((1-a)*((1-b)*corners[0,0]+b*corners[0,1])+a*((1-b)*corners[1,0]+b*corners[1,1]))
    t,p = np.deg2rad([theta,phi])
    et = np.array([np.cos(t)*np.cos(p),np.cos(t)*np.sin(p),-np.sin(t)])
    ep = np.array([-np.sin(p),np.cos(p),0.])
    return rotation@incident_pattern(components[0]*et+components[1]*ep,incident_power_w)
