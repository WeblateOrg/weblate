#! /bin/sh
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

set -e

if [ "$1" = "--force" ]; then
  FORCE="--force"
  shift
else
  FORCE=""
fi

if [ $# -ne 1 ]; then
  echo ""
  echo "usage:"
  echo "  update [--force] <git_url>"
  echo ""
  echo "  --force:   Force update that could overwrite changes you made to the OpenShift repository. Also necessary when downgrading or switching branches."
  echo "  <git_url>: URL of git repository to update from. A branch can be specified by appending '#<branch>'"
  echo "             Example: https://github.com/nijel/weblate.git#master"
  echo ""

  exit 1
fi

# Split first argument with delimiter '#'
OLDIFS=$IFS
IFS='#'
set -- $1
IFS=$OLDIFS

URL="$1"
BRANCH="${2:-master}"

cd ${OPENSHIFT_HOMEDIR}/git/${OPENSHIFT_APP_NAME}.git
OLD_HEAD=`git rev-parse master`
git fetch $FORCE "$URL" "$BRANCH":master
HEAD=`git rev-parse master`

if [ "$HEAD" == "$OLD_HEAD" ]; then
	echo "Already up-to-date."
  exit 0
fi

if ! git cat-file -e master:.openshift 2>/dev/null; then
  echo "Fatal error: Branch $BRANCH of repository at $URL doesn't contain an OpenShift configuration!" >&2
  exit 1
fi

gear deploy --hot-deploy master
