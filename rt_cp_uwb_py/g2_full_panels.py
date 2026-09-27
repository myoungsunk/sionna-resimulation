"""Condition-panel material contract for the full native Sionna campaign.

Decision 2026-09-27 (SIONNA_FULL_RESIM_20260925_01a0d86d):
- PEC condition panels (side_reflector_present, metal_near_intervention):
  native ITU metal, 0.001 m, unchanged from the 41-row contract.
- Dielectric occluder (occluder_present, 'blockage_panel'): eps_r=12,
  tan_delta=0.35 held constant over the band, thickness 0.020 m, applied to
  the existing single reference sheet (0.8 x 1.7 m, same pose).
  sigma(f) = 2*pi*f*eps0*eps_r*tan_delta is re-evaluated whenever
  scene.frequency is set, i.e. before every PathSolver call.

The 0.020 m thickness is a new synthetic design value. It does not reproduce
a measured thickness or a specific building material, and the historical
model (reflection-only thin surface) never defined transmission; the
transmitted power is an outcome of the new native model, not a preserved
property.

Pure functions only; the Sionna module is passed in so this file imports
without Sionna/Mitsuba.
"""
import math

EPS0 = 8.8541878128e-12
CONTRACT_ID = 'CONDITION_PANEL_MATERIAL_V1_20260927'

METAL_PANEL = dict(kind='PEC', native='ITURadioMaterial', itu_type='metal', thickness_m=0.001)
OCCLUDER_PANEL = dict(kind='dielectric', source_name='blockage_panel', native='RadioMaterial',
                      relative_permittivity=12.0, tan_delta=0.35, thickness_m=0.020,
                      conductivity_rule='sigma(f)=2*pi*f*eps0*eps_r*tan_delta',
                      thickness_basis='SYNTHETIC_DESIGN_VALUE_NOT_MEASURED')


def occluder_conductivity(frequency_hz, eps_r=OCCLUDER_PANEL['relative_permittivity'],
                          tan_delta=OCCLUDER_PANEL['tan_delta']):
    """Conductivity [S/m] that keeps tan_delta constant at frequency_hz."""
    if not frequency_hz > 0:
        raise ValueError('FREQUENCY_MUST_BE_POSITIVE')
    return 2*math.pi*frequency_hz*EPS0*eps_r*tan_delta


def panel_material_spec(obj):
    """Map a FRAMES.jsonl physical.object to its native material contract.

    Raises on anything outside the two known panel materials so an unknown
    object can never fall back silently to metal.
    """
    m = obj['material']
    if m['kind'] == 'PEC':
        return dict(METAL_PANEL, object_id=obj['object_id'], source_material=m['name'])
    if (m['kind'] == 'dielectric' and m['name'] == OCCLUDER_PANEL['source_name']
            and m['eps_r'] == OCCLUDER_PANEL['relative_permittivity']
            and m['tan_delta'] == OCCLUDER_PANEL['tan_delta']
            and float(m.get('conductivity_s_m') or 0.) == 0.):
        return dict(OCCLUDER_PANEL, object_id=obj['object_id'], source_material=m['name'])
    raise ValueError('UNSUPPORTED_CONDITION_PANEL_MATERIAL:' + repr((m['kind'], m['name'], m['eps_r'], m['tan_delta'])))


# Corner order (a, b) = (-1,-1), (-1,+1), (+1,-1), (+1,+1) as in c1_c3_geometry.panel_corners.
# The diagonal is 0-3; both triangles wind so their normal equals u x v.
PANEL_FACES = ((0, 2, 3), (0, 3, 1))


def panel_triangles(panel):
    """Four corners and two non-overlapping triangles covering the whole panel.

    Raises if the declared panel normal is not u x v (unit, orthogonal axes),
    so the mesh orientation always matches the source record.
    """
    u, v, n = panel['u'], panel['v'], panel['normal']
    cross = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
    dot = lambda a, b: sum(x*y for x, y in zip(a, b))
    if (abs(dot(u, u)-1) > 1e-9 or abs(dot(v, v)-1) > 1e-9 or abs(dot(u, v)) > 1e-9
            or max(abs(c-m) for c, m in zip(cross, n)) > 1e-9):
        raise ValueError('PANEL_AXES_NOT_RIGHT_HANDED_ORTHONORMAL')
    corners = []
    for a, b in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
        corners.append([panel['center'][i] + a*panel['half'][0]*u[i] + b*panel['half'][1]*v[i]
                        for i in range(3)])
    return corners, PANEL_FACES


def panel_ply(panel):
    """ASCII PLY for the single reference sheet (4 vertices, 2 triangles)."""
    corners, faces = panel_triangles(panel)
    header = ['ply', 'format ascii 1.0', 'element vertex 4', 'property float x', 'property float y',
              'property float z', 'element face 2', 'property list uchar int vertex_indices', 'end_header']
    return '\n'.join(header + [' '.join(format(x, '.17g') for x in c) for c in corners]
                     + ['3 ' + ' '.join(map(str, f)) for f in faces]) + '\n'


def make_panel_material(rt, spec, name='rm_dynamic_panel'):
    """Build the native Sionna radio material for a panel spec."""
    if spec['kind'] == 'PEC':
        return rt.ITURadioMaterial(name=name, itu_type=spec['itu_type'], thickness=spec['thickness_m'])
    if spec['kind'] == 'dielectric':
        eps_r, tan_delta = spec['relative_permittivity'], spec['tan_delta']

        def update(frequency):
            return eps_r, 2*math.pi*frequency*EPS0*eps_r*tan_delta

        return rt.RadioMaterial(name=name, thickness=spec['thickness_m'], relative_permittivity=eps_r,
                                conductivity=occluder_conductivity(6.5e9, eps_r, tan_delta),
                                frequency_update_callback=update)
    raise ValueError('UNSUPPORTED_PANEL_SPEC')


def material_readback(material):
    """Values actually bound in the scene (after the latest frequency update)."""
    scalar = lambda v: float(v[0]) if hasattr(v, '__len__') else float(v)
    return dict(name=material.name, type=type(material).__name__,
                relative_permittivity=scalar(material.relative_permittivity),
                conductivity_s_m=scalar(material.conductivity), thickness_m=scalar(material.thickness))
