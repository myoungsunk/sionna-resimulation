"""Station heading zero error (plan Stage C1, DIAGNOSTIC). The sweep stores s at the robot-reported yaw psi_k while the true yaw is
psi_k + d_st: stored curve s_err(psi) = s_true(psi + d_st) (exact Fourier shift of the 36-yaw sweep). Only the block construction sees it.
  Z1: d_st ~ N(0, 1 deg^2) independent per station;  Z2: N(0, 2 deg^2);  G2: common d = +2 deg (sweep-vs-operation reference offset)
Realisations: numpy default_rng(20261123); Z1 and Z2 share the same standard normal draw scaled by sigma."""
import sys, json, numpy as np
sys.path.insert(0, "/home/claude/lut5"); import sw_block as SB
F0 = SB.F.copy(); k2 = np.fft.rfftfreq(36, 1 / 36)
Zn = np.random.default_rng(20261123).standard_normal((len(SB.XS), len(SB.YS)))
def delta(kind):
    return {"Z1": np.radians(1.0) * Zn, "Z2": np.radians(2.0) * Zn, "G2": np.full(Zn.shape, np.radians(2.0))}[kind]
def F_err(kind):
    D = delta(kind); out = np.empty_like(F0)
    for i in range(F0.shape[0]):
        for j in range(F0.shape[1]):
            out[i, j] = np.fft.irfft(np.fft.rfft(F0[i, j]) * np.exp(1j * k2 * D[i, j]), n=36)   # s(psi + d)
    return out
def build(kind):
    """returns (block, table) built from the erroneous sweep; restores the module state afterwards."""
    SB.F = F_err(kind) if kind else F0
    try:
        B = SB.SWB(); T, _, _ = SB.column_out_table()
    finally:
        SB.F = F0
    return B, T
def build_block_only(kind):
    SB.F = F_err(kind) if kind else F0
    try: return SB.SWB()
    finally: SB.F = F0
if __name__ == "__main__":
    out = {}
    for kind in ("Z1", "Z2", "G2"):
        B, T = build(kind); out[kind] = T; d = np.degrees(delta(kind)); print(kind, "d mean %.2f sd %.2f" % (d.mean(), d.std()), json.dumps(T))
    json.dump(out, open("TABLES_ZERR.json", "w"), indent=1)
