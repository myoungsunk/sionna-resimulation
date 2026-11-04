set -e
cd /mnt/d/codex/MBVAR_PRR_001_20261103/research/MBVAR_PRR_001_20261103/POST_S3_PROPOSER_20261104/R2_EXTENSION/native_inputs
export LD_LIBRARY_PATH="$HOME/.local/share/prr31117/lib"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
"$HOME/.local/share/prr31117/bin/python3.11" reproduce.py lock
"$HOME/.local/share/prr31117/bin/python3.11" reproduce.py fit
