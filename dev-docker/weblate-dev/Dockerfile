FROM weblate/weblate:bleeding

##########
# WARNING!
# This dockerfile is meant to be used in the development process
# and WILL perform very poorly in production.
#
# For production-ready dockerfile see:
# https://github.com/WeblateOrg/docker
#########

#WORKDIR /srv

# TODO: put some new dependencies here

ARG USER_ID=1000
ARG GROUP_ID=1000

USER root
# Make sure user exists in the container
RUN if ! getent group "${GROUP_ID}"; then \
            groupadd --gid "${GROUP_ID}" developer; \
        fi \
    &&  if ! getent passwd "${USER_ID}"; then \
            useradd --gid "${GROUP_ID}" --uid "${USER_ID}" --shell /bin/bash developer; \
        fi
# Following are removed during cleanup of weblate/weblate
RUN apt-get update && apt-get install -y \
    python3-dev \
    pkg-config \
    libleptonica-dev \
    libtesseract-dev \
    libmariadb-dev \
    libxml2-dev \
    libffi-dev \
    libxmlsec1-dev \
    libpq-dev \
    gcc \
    g++ \
    file \
    make \
    libsasl2-dev \
    libacl1-dev \
    libldap2-dev \
    libssl-dev \
    libz-dev   \
    libjpeg62-turbo-dev

COPY requirements.txt /tmp/
RUN pip3 install -r /tmp/requirements.txt
# List should match weblate/weblate
RUN chmod -R 777 /etc/nginx/sites-available/ /var/log/nginx/ /var/lib/nginx /app/data /run /home /home/weblate /etc/timezone /etc/localtime
