import sys, json, numpy as np, pandas as pd, importlib.util
FZ="/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/MOUNT45_VALIDATION_20261116/frozen_inputs"
def mod(name,path):
    s=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
FE=mod("features",f"{FZ}/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/c2913abc9347_features.py")
SD_src=open(f"{FZ}/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/d108122613e5_series_dump.py").read()
ns={}; exec("import math\nimport numpy as np\nOFFS = [-8, -4, -2, -1, 1, 2, 4, 8]\ndef taps"+SD_src.split("\ndef taps")[1].split("\n\n\n")[0],ns)
taps=ns["taps"]
FREQ=np.load(f"{FZ}/DRIVE_SIM_POST_A23_UPLOAD_20261010/fe0bcfeb1426_freqs_hz.npy")
EXIST=['log_fp_power','abs_s_fp','early4','early8','early16','delay_rms_ns','peak_diff_ns','eta_fp_win80','s_diff4','s_diff8','s_diff16','tap_pol_var80','jones_diversity','freq_s_var','detector_s_span','detector_delay_span_ns']
DS=[f'ds_{o:+d}' for o in [-8,-4,-2,-1,1,2,4,8]]
B_OLD=-0.5315983906250129; A=np.array([10.,0.,2.65]); ZR=0.45
def features(H):
    out=[]
    for k in range(0,len(H),128):
        h=np.asarray(H[k:k+128])[...,0]; f=FE.extract(h,FREQ); t=taps(h)
        d={**{c:f[c] for c in FE.FEATURES+["s_fp","range_m","tap","valid"]},**{c:t[c] for c in DS},"s_fp_chk":t["s_fp_chk"]}
        out.append(pd.DataFrame(d))
    return pd.concat(out,ignore_index=True)
