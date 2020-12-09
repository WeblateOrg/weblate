Installing from sources
=======================

#. Please follow the installation instructions for your system first:

   * :doc:`venv-debian`
   * :doc:`venv-suse`
   * :doc:`venv-redhat`


#. Grab the latest Weblate sources using Git (or download a tarball and unpack that):

   .. code-block:: sh

      git clone https://github.com/WeblateOrg/weblate.git weblate-src

   Alternatively you can use released archives. You can download them from our
   website <https://weblate.org/>. Those downloads are cryptographically
   signed, please see :ref:`verify`.

#. Install current Weblate code into the virtualenv:

   .. code-block:: sh

        . ~/weblate-env/bin/activate
        pip install -e weblate-src

#. Copy :file:`weblate/settings_example.py` to :file:`weblate/settings.py`.

#.
   .. include:: steps/adjust-config.rst

#. Create the database used by Weblate, see :ref:`database-setup`.

#. Build Django tables, static files and initial data (see
   :ref:`tables-setup` and :ref:`static-files`):

   .. code-block:: sh

        weblate migrate
        weblate collectstatic
        weblate compress
        weblate compilemessages

   .. note::

         This step should be repeated whenever you update the repository.
