Upgrading Weblate
=================

.. _generic-upgrade-instructions:

Generic upgrade instructions
----------------------------

Before upgrading, please check the current :ref:`requirements` as they might have
changed. Once all requirements are installed or updated, please adjust your
:file:`settings.py` to match changes in the configuration (consult
:file:`settings_example.py` for correct values).

Always check :ref:`version-specific-instructions` before upgrade. In case you
are skipping some versions, please follow instructions for all versions you are
skipping in the upgrade. Sometimes it's better to upgrade to some intermediate
version to ensure a smooth migration. Upgrading across multiple releases should
work, but is not as well tested as single version upgrades.

.. note::

    It is recommended to perform a full database backup prior to upgrade so that you
    can roll back the database in case upgrade fails.

1. Upgrade configuration file, refer to :file:`settings_example.py` or
   :ref:`version-specific-instructions` for needed steps.

2. Upgrade database structure:

   .. code-block:: sh

        ./manage.py migrate --noinput

3. Collect updated static files (mostly javacript and CSS):

   .. code-block:: sh

        ./manage.py collectstatic --noinput

4. Update language definitions (this is not necessary, but heavily recommended):

   .. code-block:: sh

        ./manage.py setuplang

5. Optionally upgrade default set of privileges definitions (you might want to
   add new permissions manually if you have heavily tweaked access control):

   .. code-block:: sh

        ./manage.py setupgroups

6. If you are running version from Git, you should also regenerate locale files
   every time you are upgrading. You can do this by invoking:

   .. code-block:: sh

        ./manage.py compilemessages

7. Verify that your setup is sane (see also :ref:`production`):

   .. code-block:: sh

        ./manage.py check --deploy

.. versionchanged:: 3.0.1

    If you are upgrading from 2.x release, always first upgrade to 3.0.1 (see
    :ref:`weblate3:upgrade_3`) and the continue ugprading in the 3.x series.
    Upgrades skipping this step are not supported and will break.

.. _version-specific-instructions:

Version specific instructions
-----------------------------

Upgrade from 3.0.1 to 3.1
~~~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

Notable configuration or dependencies changes:

* Several no longer needed applications have been removed from :setting:`django:INSTALLED_APPS`.
* The settings now recommend using several Django security features, see :ref:`django:security-recommendation-ssl`.

.. seealso:: :ref:`generic-upgrade-instructions`

.. _py3:

Upgrading from Python 2.x to 3.x
--------------------------------

The upgrade from Python 2.x to 3.x, should work without major problems. Take
care about some changed module names when installing dependencies (eg. pydns
vs. py3dns).

The Whoosh index has to be rebuilt as it's encoding depends on Python version,
you can do that using following command:

.. code-block:: sh

    ./manage.py rebuild_index --clean --all

The caches might be incompatible (depending on cache backend you are using), so
it might be good idea to purge caches.

.. _pootle-migration:

Migrating from Pootle
---------------------

As Weblate was originally written as replacement from Pootle, it is supported
to migrate user accounts from Pootle. You can dump the users from Poootle and
import them using :djadmin:`importusers`.
