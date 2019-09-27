FROM weblate/weblate:edge

##########
# WARNING!
# This dockerfile is meant to be used in the development process
# and WILL perform very poorly in production.
#
# For production-ready dockerfile see:
# https://github.com/WeblateOrg/docker
#########

WORKDIR /srv

# TODO: put some new dependencies here

COPY requirements.txt .
USER root
RUN apt update && apt install -y \
      libxml2-dev libxslt-dev libfreetype6-dev libjpeg-dev libz-dev libyaml-dev \
      libcairo-dev gir1.2-pango-1.0 libgirepository1.0-dev libacl1-dev libssl-dev \
      build-essential python3-gdbm python3-dev python3-pip python3-virtualenv virtualenv git
RUN pip3 install -r requirements.txt

ENTRYPOINT

# Container "FROM" debian:stretch and includes python2.7. Explicitly picking python3 as weblate:edge installs pip3
CMD sh -c "python3 manage.py migrate \
    && python3 manage.py createadmin --update --password admin \
    && python3 manage.py runserver 0.0.0.0:8080"
