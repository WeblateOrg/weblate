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

CMD sh -c "./manage.py migrate \
    && ./manage.py createadmin --update --password admin \
    && ./manage.py runserver 0.0.0.0:8080"
