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
RUN pip3 install -r requirements.txt

ENTRYPOINT

# Container "FROM" debian:stretch and includes python2.7. Explicitly picking python3 as weblate:edge installs pip3
CMD sh -c "python3 manage.py migrate \
    && python3 manage.py createadmin --update --password admin \
    && python3 manage.py runserver 0.0.0.0:8080"
