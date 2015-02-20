#! /bin/bash
#
# Copyright © 2014 Daniel Tschan <tschan@puzzle.ch>
#
# This file is part of Weblate <http://weblate.org/>
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

cd ${OPENSHIFT_REPO_DIR}

sh "python ${OPENSHIFT_REPO_DIR}/setup_weblate.py develop"

# Pin Django version to 1.7 to avoid surprises when 1.8 comes out.
sed -e 's/Django[<>=]\+.*/Django>1.7,<1.8/' $OPENSHIFT_REPO_DIR/requirements-mandatory.txt >/tmp/requirements.txt

sh "pip install -r /tmp/requirements.txt"

# Install optional dependencies without failing if some can't be installed.
while read line; do
  if [[ $line != -r* ]]; then
    sh "pip install $line" || true
  fi
done < $OPENSHIFT_REPO_DIR/requirements-optional.txt

if [ ! -s $OPENSHIFT_DATA_DIR/weblate.db ]; then
  rm -f ${OPENSHIFT_DATA_DIR}/.credentials
fi

if [ ! -s $OPENSHIFT_REPO_DIR/weblate/fixtures/site_data.json ]; then
  mkdir -p $OPENSHIFT_REPO_DIR/weblate/fixtures
  cat <<-EOF >$OPENSHIFT_REPO_DIR/weblate/fixtures/site_data.json
    [{
        "pk": 1,
        "model": "sites.site",
        "fields": {
            "name": "${OPENSHIFT_APP_DNS}",
            "domain":"${OPENSHIFT_APP_DNS}"
        }
    }]
	EOF
fi

sh "python ${OPENSHIFT_REPO_DIR}/openshift/manage.py migrate --noinput"

sh "python ${OPENSHIFT_REPO_DIR}/openshift/manage.py setupgroups --move"

sh "python ${OPENSHIFT_REPO_DIR}/openshift/manage.py setuplang"

sh "python ${OPENSHIFT_REPO_DIR}/openshift/manage.py compilemessages"

sh "python ${OPENSHIFT_REPO_DIR}/openshift/manage.py rebuild_index --all"

sh "python ${OPENSHIFT_REPO_DIR}/openshift/manage.py loaddata $OPENSHIFT_REPO_DIR/weblate/fixtures/site_data"

sh "python ${OPENSHIFT_REPO_DIR}/openshift/manage.py collectstatic --noinput"

if [ ! -s $OPENSHIFT_DATA_DIR/.credentials ]; then
  echo "Generating Weblate admin credentials and writing them to ${OPENSHIFT_DATA_DIR}/.credentials"
  sh "python ${OPENSHIFT_REPO_DIR}/openshift/manage.py createadmin"
  sh "python ${OPENSHIFT_REPO_DIR}/openshift/secure_db.py | tee ${OPENSHIFT_DATA_DIR}/.credentials"
fi

if find_script_dir; then
  ln -sf ${OPENSHIFT_REPO_DIR}/openshift/update.sh $SCRIPT_DIR/update
  ln -sf ${OPENSHIFT_REPO_DIR}/openshift/credentials.sh $SCRIPT_DIR/credentials
  ln -sf ${OPENSHIFT_REPO_DIR}/openshift/settings.sh $SCRIPT_DIR/settings
fi

gear stop

# Link sources below $OPENSHIFT_REPO_DIR must be relative or they will be invalid after restore/clone operations
ln -sf ../openshift/wsgi.py $OPENSHIFT_REPO_DIR/wsgi/application
touch $OPENSHIFT_DATA_DIR/.installed

gear start
