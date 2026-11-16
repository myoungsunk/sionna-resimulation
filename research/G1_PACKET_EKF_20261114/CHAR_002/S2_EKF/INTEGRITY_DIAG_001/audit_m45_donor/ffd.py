import sys, types, numpy as np
from pathlib import Path
R45 = Path('/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001/continuation_ks/replay_inputs/R45_sources')
sys.path[:0] = [str(R45/'src'), str(R45/'research/FFD_P0P3_20261016'), str(R45/'research/EKF4_RANGE_S_STAGED_20261014')]
from qclean_uwb.drivesim import pattern_apply as P
import source_model as SM
def load():
    banks = []
    for name in ('LP_plus45_bank.npz', 'LP_minus45_bank.npz'):
        with np.load(f'/home/claude/rel/{name}', allow_pickle=False) as z:
            banks.append(P.Bank(dict(z)))
    return SM.SourceFFD(banks=banks)
