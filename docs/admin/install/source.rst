Installing from sources
=======================

#. Please follow the installation instructions for your system first up to installing Weblate:

   * :doc:`venv-debian`
   * :doc:`venv-suse`
   * :doc:`venv-redhat`


#. Grab the latest Weblate sources using Git (or download a tarball and unpack that):

   .. code-block:: sh

      git clone https://github.com/WeblateOrg/weblate.git weblate-src

   Alternatively you can use released archives. You can download them from our
   website <https://weblate.org/>. Those downloads are cryptographically
   signed, please see :ref:`verify`.

#. Install current Weblate code into the Python environment:

   .. code-block:: sh

        . ~/weblate-env/bin/activate
        uv pip install -e 'weblate-src[all]'

   If you intend to run the testsuite from the source checkout, install the
   development dependencies as described in :ref:`local-tests`.

#. Copy :file:`weblate/settings_example.py` to :file:`weblate/settings.py`.

#.
   .. include:: steps/adjust-config.rst

#. Create the database used by Weblate, see :ref:`database-setup`.

#. Build Django tables, static files and initial data (see
   :ref:`tables-setup` and :ref:`static-files`):

   .. code-block:: sh

        weblate migrate
        weblate collectstatic

   .. note::

         This step should be repeated whenever you update the repository.

.. _distribution-packaging:

Packaging Weblate for distributions
-----------------------------------

The dependency versions in :file:`pyproject.toml` describe the runtime
environment tested by the Weblate project. They are intentionally strict for
installs from PyPI and for the Weblate release process, because Weblate cannot
validate every dependency-version combination covered by wider version ranges.

Distribution packages can replace those Python packages with versions from the
distribution package set. When doing so, run Weblate's test suite against the
packaged dependency set and treat passing tests as the compatibility signal for
the distribution package.

Keep Weblate's tightly coupled companion packages in sync with the Weblate
release:

* :pypi:`weblate-fonts`
* :pypi:`weblate_schemas`
* :pypi:`weblate-language-data`
* :pypi:`translation-finder`
* :pypi:`translate-toolkit`

Mismatched versions of these packages are more likely to break at runtime or
during tests than other Python dependency substitutions.

.. seealso::

   See :ref:`local-tests` for test setup and :ref:`release-cycle` for Weblate's
   release cadence.
