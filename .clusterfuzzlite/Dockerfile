# Copyright © Weblate contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
FROM gcr.io/oss-fuzz-base/base-builder-python:ubuntu-24-04@sha256:1f20728dd1fe96e5e39c33abf153cf1e82aa4915336f5962423fc3e3e21c1198

ENV UV_CACHE_DIR=/tmp/uv-cache
ENV UV_PYTHON_INSTALL_DIR=/opt/uv-python
ENV UV_PYTHON_INSTALL_BIN=0
ENV UV_MANAGED_PYTHON=1
ENV UV_PYTHON=3.12.13
ENV DEBIAN_FRONTEND=noninteractive
# renovate: datasource=github-releases depName=astral-sh/uv versioning=pep440
ENV UV_VERSION=0.11.7

RUN curl -fsSL -o /tmp/uv.tar.gz \
    "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-x86_64-unknown-linux-gnu.tar.gz" \
    && tar -xzf /tmp/uv.tar.gz -C /tmp \
    && install /tmp/uv-x86_64-unknown-linux-gnu/uv /usr/local/bin/uv \
    && rm -rf /tmp/uv.tar.gz /tmp/uv-x86_64-unknown-linux-gnu
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    cargo \
    gnupg \
    lsb-release \
    python3-dev \
    rustc \
    && install -d /rust/bin \
    && ln -sf /usr/bin/cargo /rust/bin/cargo \
    && ln -sf /usr/bin/rustc /rust/bin/rustc \
    && install -d /etc/apt/keyrings \
    && rm -rf /var/lib/apt/lists/*
RUN uv python install ${UV_PYTHON}

WORKDIR $SRC/weblate
COPY . $SRC/weblate
COPY .clusterfuzzlite/build.sh $SRC/build.sh

RUN ./ci/apt-install
RUN ./ci/pip-install latest
#
# Reinstall lxml and xmlsec from the locked manylinux wheels. The shared
# installer builds them from source against Ubuntu 24.04 system libraries,
# which are not available in ClusterFuzzLite's bad-build runtime.
RUN uv sync --frozen --all-extras --dev \
    --reinstall-package lxml \
    --reinstall-package xmlsec
RUN uv sync --frozen --group fuzzing --inexact
