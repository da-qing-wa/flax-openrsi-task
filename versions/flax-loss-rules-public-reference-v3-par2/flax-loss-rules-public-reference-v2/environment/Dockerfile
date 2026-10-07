FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake git ca-certificates curl xz-utils pkg-config \
    libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev \
    libffi-dev liblzma-dev libncursesw5-dev uuid-dev tk-dev \
    flex bison libgl1 libsdl2-2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN test "$(uname -m)" = x86_64 \
    && curl --fail --location --retry 3 https://www.python.org/ftp/python/3.10.12/Python-3.10.12.tar.xz -o /tmp/python.tar.xz \
    && echo 'afb74bf19130e7a47d10312c8f5e784f24e0527981eab68e20546cfb865830b8  /tmp/python.tar.xz' | sha256sum -c - \
    && tar -xJf /tmp/python.tar.xz -C /tmp \
    && cd /tmp/Python-3.10.12 && ./configure --prefix=/opt/python --with-ensurepip=install \
    && sed -i 's/-j0 /-j4 /g' Makefile \
    && make -j4 && make install \
    && rm -rf /tmp/Python-3.10.12 /tmp/python.tar.xz

ENV PATH=/opt/python/bin:/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin \
    PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1

COPY flax-source.tar.gz work-inputs.tar.gz development-pddl.tar.gz reference.tar.gz build_assets.py /opt/build-assets/
RUN python3.10 /opt/build-assets/build_assets.py \
    && cd /opt/flax && git apply --check /opt/flax-assets/changes.patch && git apply /opt/flax-assets/changes.patch \
    && git clone https://github.com/ronuchit/downward.git /opt/build-assets/downward \
    && cd /opt/build-assets/downward && git checkout 83dfcd7d7f6d9478373b3255047f39d371ff0b63 \
    && test "$(git rev-parse HEAD)" = 83dfcd7d7f6d9478373b3255047f39d371ff0b63 \
    && git archive --format=tar --output=/opt/build-assets/downward.tar HEAD \
    && mkdir -p /opt/flax/planning/FD \
    && tar -xf /opt/build-assets/downward.tar -C /opt/flax/planning/FD \
    && cd /opt/flax/planning/FD && python3.10 build.py release -j4 \
    && rm -rf /opt/build-assets/downward /opt/build-assets/downward.tar \
    && git clone https://github.com/KCL-Planning/VAL.git /opt/flax/VAL \
    && cd /opt/flax/VAL && git checkout 3c7a1f330bdab0ba28a4762bb45c3f06c27fb6d4 \
    && test "$(git rev-parse HEAD)" = 3c7a1f330bdab0ba28a4762bb45c3f06c27fb6d4 \
    && bash scripts/linux/build_linux64.sh all Release && rm -rf .git \
    && git clone https://github.com/Farama-Foundation/Minigrid.git /opt/minigrid \
    && cd /opt/minigrid && git checkout 8ea099e114b7d6465afabc76957e3d689663534c \
    && test "$(git rev-parse HEAD)" = 8ea099e114b7d6465afabc76957e3d689663534c \
    && git apply --check /opt/flax-assets/dependencies/minigrid.patch \
    && git apply /opt/flax-assets/dependencies/minigrid.patch \
    && cp /opt/flax/minigrid_mazenamo_env_patch/grid_3d.py minigrid/core/grid_3d.py \
    && cp /opt/flax/minigrid_mazenamo_env_patch/mazenamo.py minigrid/envs/mazenamo.py \
    && rm -rf .git

RUN python3.10 -m pip install --no-cache-dir pip==26.2.1 setuptools==84.0.0 \
    && python3.10 -m pip install --no-cache-dir --extra-index-url=https://download.pytorch.org/whl/cpu -r /opt/build-assets/install-requirements.txt \
    && python3.10 -m pip install --no-cache-dir --no-deps --no-build-isolation /opt/minigrid \
    && test -x /opt/flax/planning/FD/builds/release/bin/downward \
    && test -x /opt/flax/VAL/build/linux64/Release/bin/Validate

COPY tools/ /opt/flax-tools/
COPY validate-candidate flax-dev /usr/local/bin/
COPY close_workspace.py /opt/build-assets/close_workspace.py
RUN chmod 755 /usr/local/bin/validate-candidate /usr/local/bin/flax-dev \
    && python3.10 -S -B /opt/build-assets/close_workspace.py \
    && rm -rf /opt/build-assets /root/.cache

WORKDIR /workspace
