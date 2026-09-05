# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

FROM weblate/weblate:2026.9.0.0@sha256:24b99c51a53d2edbb06db41a384c683fc599d95420ff0c1a4cba03f5b970458c

##########
# WARNING!
# This dockerfile is meant to be used in the development process
# and WILL perform very poorly in production.
#
# For production-ready dockerfile see:
# https://github.com/WeblateOrg/docker
#########

#WORKDIR /srv

ARG USER_ID=1000
ARG GROUP_ID=1000

USER root
ENV PATH=/app/venv/bin:/usr/local/bin:/usr/bin:/bin:/sbin:/usr/sbin
ENV UV_CACHE_DIR=/app/data/uv-cache
ENV UV_LINK_MODE=copy
# Make sure user exists in the container
RUN if ! getent group "${GROUP_ID}"; then \
            groupadd --gid "${GROUP_ID}" developer; \
        fi \
    &&  if ! getent passwd "${USER_ID}"; then \
            useradd --gid "${GROUP_ID}" --uid "${USER_ID}" --groups root,tty,weblate --shell /bin/bash developer; \
        fi
# Following should match what dev container in docker-base repo includes
RUN apt-get update && apt-get install -y \
    pkg-config \
    make \
    gcc \
    g++ \
    libicu-dev \
    libxml2-dev \
    libacl1-dev \
    liblz4-dev \
    libzstd-dev \
    libxxhash-dev \
    libmariadb-dev \
    libxmlsec1-dev \
    libsasl2-dev \
    libldap2-dev \
    libssl-dev \
    libffi-dev \
    libpq-dev \
    zlib1g-dev \
    libjpeg62-dev

# List should match weblate/weblate
RUN chown -R "${USER_ID}:${GROUP_ID}" /etc/nginx/sites-available/ /var/log/nginx/ /var/lib/nginx /app/data /app/cache /run /home/weblate /etc/localtime /etc/supervisor/conf.d /tmp /home

# Start with fresh venv
# Using the original would work, but chown on it is super slow, see https://github.com/docker/for-linux/issues/388
RUN rm -rf /app/venv && mkdir /app/venv && chown "${USER_ID}:${GROUP_ID}" /app/venv

# uv stores Python in a version- and architecture-specific directory. Keep it
# available on PATH even before the application virtual environment is created.
# Do not create root-owned files in the runtime user's uv cache.
RUN ln -sf "$(uv --no-cache python find --system --managed-python --no-python-downloads "${PYVERSION}")" /usr/local/bin/python3 \
    && /usr/bin/env python3 --version


COPY --link --chmod=0755 start-dev /app/bin/

ENTRYPOINT ["/app/bin/start-dev"]
CMD ["runserver"]
