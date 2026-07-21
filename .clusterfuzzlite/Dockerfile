# Copyright © Weblate contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
FROM ghcr.io/weblateorg/dev:2026.30.0@sha256:2b076ba94e91559101dddb447d443aea7e2a2c589234c05060ec7b854fb1bc56

ENV UV_CACHE_DIR=/tmp/uv-cache
ENV UV_PYTHON_INSTALL_DIR=/opt/uv-python
ENV UV_PYTHON_INSTALL_BIN=0
ENV UV_MANAGED_PYTHON=1
ENV UV_PYTHON=3.12.13
ENV DEBIAN_FRONTEND=noninteractive
ENV SRC=/src
ENV OUT=/out
ENV WORK=/work
ENV CC=clang
ENV CXX=clang++
ENV CCC=clang++
ENV CFLAGS="-O1 -fno-omit-frame-pointer -gline-tables-only -Wno-error=incompatible-function-pointer-types -Wno-error=int-conversion -Wno-error=deprecated-declarations -Wno-error=implicit-function-declaration -Wno-error=implicit-int -Wno-error=unknown-warning-option -Wno-error=vla-cxx-extension -DFUZZING_BUILD_MODE_UNSAFE_FOR_PRODUCTION"
ENV CXXFLAGS="$CFLAGS"
ENV SANITIZER=address
ENV FUZZING_ENGINE=libfuzzer
ENV FUZZING_LANGUAGE=python
ENV ARCHITECTURE=x86_64

RUN apt-get update && apt-get install -y --no-install-recommends \
    cargo \
    clang \
    libclang-rt-dev \
    libicu-dev \
    llvm \
    rustc \
    zip \
    && install -d "$SRC" "$OUT" "$WORK" \
    && install -d /rust/bin \
    && ln -sf /usr/bin/cargo /rust/bin/cargo \
    && ln -sf /usr/bin/rustc /rust/bin/rustc \
    && rm -rf /var/lib/apt/lists/*
RUN uv python install ${UV_PYTHON}

COPY --chmod=0755 .clusterfuzzlite/compile.sh /usr/local/bin/compile

WORKDIR $SRC/weblate
COPY . $SRC/weblate
COPY .clusterfuzzlite/build.sh $SRC/build.sh

RUN ./ci/pip-install latest
#
# Reinstall selected native wheels for the oldest runtime ABI used by
# ClusterFuzzLite. Keep the platform override scoped to these packages; using it
# with uv sync makes uv validate unrelated build-only packages for that target.
RUN python3 - <<'PY' > /tmp/cflite-native-wheels.txt
import tomllib

with open("uv.lock", "rb") as handle:
    versions = {
        package["name"]: package["version"]
        for package in tomllib.load(handle)["package"]
    }

for package in ("cryptography", "lxml", "xmlsec"):
    print(f"{package}=={versions[package]}")
PY
RUN uv pip install \
    --python .venv/bin/python \
    --python-platform x86_64-manylinux_2_28 \
    --reinstall \
    --no-deps \
    --only-binary :all: \
    -r /tmp/cflite-native-wheels.txt
RUN uv sync --frozen --group fuzzing --inexact

CMD ["compile"]
