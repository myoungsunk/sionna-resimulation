from __future__ import annotations

from .core import Material


def materials_library() -> dict[str, Material]:
    return {
        "air": Material(name="air", eps_r=1.0, tan_delta=0.0),
        "vacuum": Material(name="vacuum", eps_r=1.0, tan_delta=0.0, xpol_coupling_db=60.0),
        "drywall": Material(name="drywall", eps_r=2.5, tan_delta=0.02, xpol_coupling_db=28.0),
        "concrete": Material(name="concrete", eps_r=5.5, tan_delta=0.05, xpol_coupling_db=25.0),
        "brick": Material(name="brick", eps_r=4.0, tan_delta=0.02, xpol_coupling_db=27.0),
        "glass": Material(name="glass", eps_r=6.0, tan_delta=0.001, xpol_coupling_db=40.0),
        "wood": Material(name="wood", eps_r=2.0, tan_delta=0.02, xpol_coupling_db=30.0),
        "ceramic_tile": Material(name="ceramic_tile", eps_r=10.0, tan_delta=0.005, xpol_coupling_db=38.0),
        "metal_pec": Material(name="metal_pec", kind="PEC", pec_tm_sign=-1.0, xpol_coupling_db=45.0),
        "pec": Material(name="pec", kind="PEC", pec_tm_sign=-1.0, xpol_coupling_db=45.0),
    }
