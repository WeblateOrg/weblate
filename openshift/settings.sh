#!/bin/sh

source $OPENSHIFT_HOMEDIR/python/virtenv/bin/activate
${OPENSHIFT_REPO_DIR}/openshift/manage.py diffsettings
