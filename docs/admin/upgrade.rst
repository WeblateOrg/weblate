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
    can roll back the database in case upgrade fails, see :doc:`backup`.

1. Upgrade configuration file, refer to :file:`settings_example.py` or
   :ref:`version-specific-instructions` for needed steps.

2. Upgrade database structure:

   .. code-block:: sh

        ./manage.py migrate --noinput

3. Collect updated static files (mostly javascript and CSS):

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

8. Restart celery worker (see :ref:`celery`).


.. _version-specific-instructions:

Version specific instructions
-----------------------------

Upgrade from 2.x
~~~~~~~~~~~~~~~~

If you are upgrading from 2.x release, always first upgrade to 3.0.1 (see
:ref:`weblate3:upgrade_3`) and the continue upgrading in the 3.x series.
Upgrades skipping this step are not supported and will break.

.. _up-3-1:

Upgrade from 3.0.1 to 3.1
~~~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

Notable configuration or dependencies changes:

* Several no longer needed applications have been removed from :setting:`django:INSTALLED_APPS`.
* The settings now recommend using several Django security features, see :ref:`django:security-recommendation-ssl`.
* There is new dependency on the ``jellyfish`` module.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 3.1 to 3.2
~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

Notable configuration or dependencies changes:

* Rate limiting configuration has been changed, please see :ref:`rate-limit`.
* Microsoft Terminology machine translation was moved to separate module and now requires ``zeep`` module.
* Weblate now uses Celery for several background tasks. There are new dependencies and settings because of this. You should also run Celery worker as standalone process. See :ref:`celery` for more information.
* There are several changes in :file:`settings_example.py`, most notable Celery configuration and middleware changes, please adjust your settings accordingly.

.. seealso:: :ref:`generic-upgrade-instructions`


Upgrade from 3.2 to 3.3
~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

Notable configuration or dependencies changes:

* The DEFAULT_CUSTOM_ACL settings was replaced by :setting:`DEFAULT_ACCESS_CONTROL`. If you were using that please update your :file:`settings.py`.
* Increase required translate-toolkit version to 2.3.1.
* Increase required social auth module versions (2.0.0 for social-auth-core and 3.0.0 for social-auth-app-django).
* The CELERY_RESULT_BACKEND should be now configured unless you are using eager mode, see :doc:`celery:userguide/configuration`.
* There is new ``weblate.middleware.ProxyMiddleware`` middleware needed if you use :setting:`IP_BEHIND_REVERSE_PROXY`.

.. seealso:: :ref:`generic-upgrade-instructions`


Upgrade from 3.3 to 3.4
~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

Notable configuration or dependencies changes:

* The Celery now uses multiple queues, it is recommended to update to new worker setup which utilizes this, see :ref:`celery`.
* There is new depedency on diff-match-patch and translation-finder.

.. seealso:: :ref:`generic-upgrade-instructions`


Upgrade from 3.4 to 3.5
~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

Notable configuration or dependencies changes:

* There are several new checks included in the :setting:`CHECK_LIST`.

.. seealso:: :ref:`generic-upgrade-instructions`

.. _py3:

Upgrading from Python 2 to Python 3
-----------------------------------

Weblate currently supports both Python 2.7 and 3.x. Upgrading existing
installations is supported, but you should pay attention to some data stored on
the disk as it might be incompatible between these two.

Things which might be problematic include Whoosh indices and file based caches.
Fortunately these are easy to handle. Recommended upgrade steps:

1. Backup your :ref:`translation-memory` using :djadmin:`dump_memory`:

   .. code-block:: sh

         ./manage.py dump_memory > memory.json

2. Upgrade your installation to Python 3.
3. Delete :ref:`translation-memory` database :djadmin:`delete_memory`:

   .. code-block:: sh

         ./manage.py delete_memory --all

4. Restore your :ref:`translation-memory` using :djadmin:`import_memory`.

   .. code-block:: sh

         ./manage.py import_memory memory.json

5. Recreate fulltext index using :djadmin:`rebuild_index`:

   .. code-block:: sh

      ./manage.py rebuild_index --clean --all

6. Cleanup avatar cache (if using file based) using :djadmin:`cleanup_avatar_cache`.

   .. code-block:: sh

      ./manage.py cleanup_avatar_cache

7. It is recommended to throw away your caches.

.. _pootle-migration:

Migrating from Pootle
---------------------

As Weblate was originally written as replacement from Pootle, it is supported
to migrate user accounts from Pootle. You can dump the users from Pootle and
import them using :djadmin:`importusers`.
