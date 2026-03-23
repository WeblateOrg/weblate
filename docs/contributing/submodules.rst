Subprojects and embedded code
=============================

Weblate would not be possible without other projects it depends on. This
document describes how other code is used in Weblate.

Vendored frontend code
----------------------

Weblate vendors several JavaScript libraries. The process is described in
:doc:`frontend` and licensing of each vendored library is documented via REUSE
as described in :doc:`license`. The up-to-date list of dependencies can be
reviewed in :ref:`sbom`.

SPDX license data
-----------------

The SPDX license data is included as a Git submodule in the source code and
:file:`weblate/utils/licensedata.py` is generated using
:file:`scripts/generate-license-data.py`.

Test data
---------

The test repositories in :file:`weblate/trans/tests/data/test-base-repo.*.tar`
are generated from https://github.com/WeblateOrg/test, see :ref:`test-data`.

Python dependencies
-------------------

Weblate would not be possible without many third-party dependencies. The
current dependencies are in :file:`pyproject.toml` and can be reviewed in
:ref:`sbom`. The most important dependencies are also described in
:ref:`python-deps`.
