#!/bin/sh

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Packs test data for Weblate
set -e

# Output directory
OUT="$(pwd)/weblate/trans/tests/data/"

# Working directory
WD=$(mktemp -d)
cd "$WD"

# Close bare Git repo
git clone --bare https://github.com/WeblateOrg/test.git test-base-repo.git
cd test-base-repo.git
# Preserve the general test dataset when refreshing the screenshot fixture.
TEST_REVISION=22fd7964344214293271d5137eba3bc3654a98ac
git update-ref refs/heads/main "$TEST_REVISION"
# Keep screenshot/demo data separate from the general test trees. Pin its
# revision so regenerating fixtures does not silently change documentation.
DEMO_REVISION=70013c5596e95ce3a898fa929f060b0c71962ff3
git fetch --no-tags https://github.com/WeblateOrg/demo.git "$DEMO_REVISION"
git update-ref refs/fixtures/screenshot-demo FETCH_HEAD
# Remove origin
git remote remove origin
# Delete all tags
# shellcheck disable=SC2046
git tag -d $(git tag)
# Recompress everything and remove stale references
git gc --aggressive --prune=now
# Remove hook examples
rm hooks/*
cd ..

# Create test data without VCS metadata
mkdir test-data
cd test-base-repo.git
git archive main | tar -x -v -f - -C ../test-data
cd ..

#  Create Mercurial repo with same content as Git
cp -r test-data test-base-repo.hg
cd test-base-repo.hg
hg init .
hg add .
hg commit --date 2019-01-01 -m 'Import git files

Zkouška'
hg branch translations
hg mv po translations
hg commit --date 2019-02-02 -m 'Rename'
hg update default
echo "Mercurial copy" >> README.md
hg commit --date 2019-02-02 -m 'Update'
hg update null
cd ..

# Create SVN repo with same content as Git
svnadmin create --compatible-version 1.6 test-base-repo.svn
# Hardcode UUID to make this reproducible
echo "24fccd88-22b4-439e-bb17-3cda778ca655" > test-base-repo.svn/db/uuid
# Allow propset to change timestamps
cat > test-base-repo.svn/hooks/pre-revprop-change << EOT
#!/bin/sh
exit 0
EOT
chmod +x test-base-repo.svn/hooks/pre-revprop-change
# Import
cd test-data
svn import -m 'Import git files

Zkouška' . "file://$WD/test-base-repo.svn/trunk"
cd ..
# Reset timestamps
svn propset -r0 --revprop svn:date "2019-01-01T00:44:04.921324Z" "file://$WD/test-base-repo.svn/trunk"
svn propset -rHEAD --revprop svn:date "2019-02-02T00:44:04.921324Z" "file://$WD/test-base-repo.svn/trunk"

# Pack them
reproducible_tar() {
    tar --sort=name \
        --mtime="2019-01-01" \
        --owner=0 --group=0 --numeric-owner \
        -cf "$@"
}
reproducible_tar "$OUT/test-base-repo.hg.tar" test-base-repo.hg
reproducible_tar "$OUT/test-base-repo.git.tar" test-base-repo.git
reproducible_tar "$OUT/test-base-repo.svn.tar" test-base-repo.svn

# Remove working dir
rm -rf "$WD"
