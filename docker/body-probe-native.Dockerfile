# Linux amd64 CPU runtime; no RF solver is invoked by this image build.
FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends libllvm14 \
    && rm -rf /var/lib/apt/lists/*
ENV DRJIT_LIBLLVM_PATH=/usr/lib/x86_64-linux-gnu/libLLVM-14.so \
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 MPLBACKEND=Agg
WORKDIR /workspace
COPY configs/body_probe/requirements-native-cloud.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements.txt
COPY src /workspace/src
COPY scripts /workspace/scripts
COPY configs /workspace/configs
RUN python -c "import mitsuba as mi; mi.set_variant('llvm_ad_mono_polarized'); import drjit as dr; import sionna.rt; assert dr.has_backend(dr.JitBackend.LLVM), 'LLVM backend unavailable'"
ENTRYPOINT ["python", "scripts/drive_sim/run_body_probe_v2_cloud.py"]
