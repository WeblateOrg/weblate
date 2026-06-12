# Copyright © Weblate contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
FROM ghcr.io/weblateorg/dev:2026.24.0@sha256:b5b667b61c45783add66ca6d498e2fa70abe6ce4506899afbb6dacfa3bc2833e

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
# Reinstall lxml and xmlsec from the locked manylinux wheels. The shared
# installer builds them from source against system libraries, which are not
# available in ClusterFuzzLite's bad-build runtime.
RUN uv sync --frozen --all-extras --dev \
    --reinstall-package lxml \
    --reinstall-package xmlsec
RUN uv sync --frozen --group fuzzing --inexact

CMD ["compile"]
