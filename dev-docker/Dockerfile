FROM weblate/weblate:edge

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

USER root
# Following are removed during cleanup of weblate/weblate
RUN apt-get update && apt-get install -y \
    python3-dev \
    pkg-config \
    libleptonica-dev \
    libtesseract-dev \
    libxml2-dev \
    libxmlsec1-dev \
    cython \
    gcc \
    g++ \
    libsasl2-dev \
    libldap2-dev \
    libssl-dev
COPY requirements.txt /tmp/
RUN pip3 install -r /tmp/requirements.txt
# List should match weblate/weblate
RUN chmod -R 777 /etc/nginx/sites-available/ /var/log/nginx/ /var/lib/nginx /app/data /run /home /home/weblate /etc/timezone /etc/localtime
