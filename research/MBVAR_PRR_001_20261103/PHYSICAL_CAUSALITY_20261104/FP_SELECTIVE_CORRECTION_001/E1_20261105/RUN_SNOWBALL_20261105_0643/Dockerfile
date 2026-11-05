FROM python:3.12.14-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
RUN python -m pip install --no-cache-dir numpy==2.3.5 scipy==1.17.0 pandas==2.2.3 joblib==1.5.3 threadpoolctl==3.6.0
ENV OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=/work/src
WORKDIR /work
