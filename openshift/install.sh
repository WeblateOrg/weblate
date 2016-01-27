#! /bin/bash
#
# Copyright © 2014 Daniel Tschan <tschan@puzzle.ch>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

# Log and execute given command, identing its output for easy filtering.
sh() {
  echo "Executing '$1'"
  /bin/sh -c "$1" 2>&1 | sed -u -e 's/^/  /'
}

# Find writable directory in PATH.
find_script_dir() {
  SCRIPT_DIR=""
  OLDIFS="$IFS"
  IFS=:
  for DIR in $PATH; do
    test -w "$DIR" && SCRIPT_DIR="$DIR" && break
  done
  IFS="$OLDIFS"
  test -n "$SCRIPT_DIR"
}

set -e
set -o errtrace
set -o pipefail
trap "rm $OPENSHIFT_DATA_DIR/.install" EXIT
trap 'echo -e "\nInstallation failed!"' ERR

test -e $OPENSHIFT_DATA_DIR/.install && exit 0

touch $OPENSHIFT_DATA_DIR/.install

export PYTHONUNBUFFERED=1
source $OPENSHIFT_HOMEDIR/python/virtenv/bin/activate

# Stop unneeded cartridges to save memory
gear stop --cart cron
gear stop --cart mysql

cd ${OPENSHIFT_REPO_DIR}

# Pin Django version to 1.8 to avoid surprises when 1.9 comes out.
# Prevent lxml 3.5 or later to be used on OpenShift because its compilation
# needs more memory than small gears can provide.
sed -e 's/Django[<>=]\+.*/Django>=1.8,<1.9/' \
  -e 's/lxml[<>=]\+.*/\0,<3.5/' \
  $OPENSHIFT_REPO_DIR/requirements.txt \
  >/tmp/requirements.txt

sh "pip install -U -r /tmp/requirements.txt"

# Install optional dependencies without failing if some can't be installed.
while read line; do
  if [[ $line != -r* ]] && [[ $line != \#* ]]; then
    sh "pip install $line" || true
  fi
done < $OPENSHIFT_REPO_DIR/requirements-optional.txt

# Start the database again as it is needed for setup scripts
gear start --cart mysql

sh "python ${OPENSHIFT_REPO_DIR}/setup_weblate.py develop"

sh "python ${OPENSHIFT_REPO_DIR}/openshift/manage.py migrate --noinput"

if [ ! -s $OPENSHIFT_DATA_DIR/.credentials ]; then
  sh "python ${OPENSHIFT_REPO_DIR}/openshift/manage.py changesite --set-name ${OPENSHIFT_APP_DNS}"
fi

if [ ! -s $OPENSHIFT_DATA_DIR/.credentials ]; then
  sh "python ${OPENSHIFT_REPO_DIR}/openshift/manage.py setupgroups --move"
else
  sh "python ${OPENSHIFT_REPO_DIR}/openshift/manage.py setupgroups --no-privs-update"
fi


sh "python ${OPENSHIFT_REPO_DIR}/openshift/manage.py setuplang"

sh "python ${OPENSHIFT_REPO_DIR}/openshift/manage.py compilemessages"

sh "python ${OPENSHIFT_REPO_DIR}/openshift/manage.py rebuild_index --all"

sh "python ${OPENSHIFT_REPO_DIR}/openshift/manage.py loaddata $OPENSHIFT_REPO_DIR/weblate/fixtures/site_data"

sh "python ${OPENSHIFT_REPO_DIR}/openshift/manage.py collectstatic --noinput"

if [ ! -s $OPENSHIFT_DATA_DIR/.credentials ]; then
  echo "Generating Weblate admin credentials and writing them to ${OPENSHIFT_DATA_DIR}/.credentials"
  sh "python ${OPENSHIFT_REPO_DIR}/openshift/manage.py createadmin" |  tee ${OPENSHIFT_DATA_DIR}/.credentials
fi

if find_script_dir; then
  ln -sf ${OPENSHIFT_REPO_DIR}/openshift/update.sh $SCRIPT_DIR/update
  ln -sf ${OPENSHIFT_REPO_DIR}/openshift/credentials.sh $SCRIPT_DIR/credentials
  ln -sf ${OPENSHIFT_REPO_DIR}/openshift/settings.sh $SCRIPT_DIR/settings
fi

gear stop --cart python

# Link sources below $OPENSHIFT_REPO_DIR must be relative or they will be invalid after restore/clone operations
ln -sf ../openshift/wsgi.py $OPENSHIFT_REPO_DIR/wsgi/application
touch $OPENSHIFT_DATA_DIR/.installed

ln -sf ../openshift/htaccess $OPENSHIFT_REPO_DIR/wsgi/.htaccess

gear start
