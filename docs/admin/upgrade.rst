Upgrading Weblate
=================

Docker image upgrades
---------------------

The official Docker image (see :ref:`quick-docker`) has all upgrade steps
integrated. There are no manual step besides pulling latest version.

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

1. Stop wsgi and Celery processes. The upgrade can perform incompatible changes in the
   database, so it is always safer to avoid old processes running while upgrading.

2. Upgrade Weblate code.

   For pip installs it can be achieved by:

   .. code-block:: sh

      pip install -U Weblate

   With Git checkout you need to fetch new source code and update your installation:

   .. code-block:: sh

        cd weblate-src
        git pull
        # Update Weblate inside your virtualenv
        . ~/weblate-env/bin/pip install -e .
        # Install dependecies directly when not using virtualenv
        pip install --upgrade -r requirements.txt

3. Upgrade configuration file, refer to :file:`settings_example.py` or
   :ref:`version-specific-instructions` for needed steps.

4. Upgrade database structure:

   .. code-block:: sh

        weblate migrate --noinput

5. Collect updated static files (mostly javascript and CSS):

   .. code-block:: sh

        weblate collectstatic --noinput

6. If you are running version from Git, you should also regenerate locale files
   every time you are upgrading. You can do this by invoking:

   .. code-block:: sh

        weblate compilemessages

7. Verify that your setup is sane (see also :ref:`production`):

   .. code-block:: sh

        weblate check --deploy

8. Restart celery worker (see :ref:`celery`).


.. _version-specific-instructions:

Version specific instructions
-----------------------------

Upgrade from 2.x
~~~~~~~~~~~~~~~~

If you are upgrading from 2.x release, always first upgrade to 3.0.1 and the
continue upgrading in the 3.x series.  Upgrades skipping this step are not
supported and will break.

.. seealso::

   `Upgrade from 2.20 to 3.0 in Weblate 3.0 documentation <https://docs.weblate.org/en/weblate-3.0.1/admin/upgrade.html#upgrade-3>`_

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



Upgrade from 3.5 to 3.6
~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

Notable configuration or dependencies changes:

* The automatic detection of file format has been removed. Please adjust your
  translation components configuration prior to upgrade. The upgrade should be
  able to gracefully handle most of situations, but can fail in some corner
  cases.
* If you have manually changed :setting:`WEBLATE_FORMATS`, you will have to remove
  ``AutoFormat`` from it.
* During the upgrade, the notifications settings need to be converted. This can
  be lengthty operation in case you have lot of users.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 3.6 to 3.7
~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

Notable configuration or dependencies changes:

* The Celery now uses separate queue for notifications, it is recommended to update to new worker setup which utilizes this, see :ref:`celery`.
* There are new (``bleach``, ``gobject``, ``pycairo``) and updated (``translation-finder``) dependencies, you will now need Pango and Cairo system libraries as well, see :ref:`pangocairo`.
* There are new addons, you might want to include them in case you modified the :setting:`WEBLATE_ADDONS`.
* There are new file formats, you might want to include them in case you modified the :setting:`WEBLATE_FORMATS`.
* There is change in the :setting:`django:CSRF_FAILURE_VIEW`.
* There is new app ``weblate.fonts`` to be included in :setting:`django:INSTALLED_APPS`.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 3.7 to 3.8
~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

Notable configuration or dependencies changes:

* There is new app ``django.contrib.humanize`` to be included in :setting:`django:INSTALLED_APPS`.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 3.8 to 3.9
~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

Notable configuration or dependencies changes:

* There are several new checks included in the :setting:`CHECK_LIST`.
* There are several updated and new dependencies.
* Sentry is now supported through modern Sentry SDK instead of Raven, please adjust your configuration to use new :setting:`SENTRY_DSN`.
* There are new addons, you might want to include them in case you modified the :setting:`WEBLATE_ADDONS`.
* The Celery now uses separate queue for backups, it is recommended to update to new worker setup which utilizes this, see :ref:`celery`.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 3.9 to 3.10
~~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

Notable configuration or dependencies changes:

* The database migration can take long on bigger installations.
* There is new dependency on the ``misaka`` and ``GitPython`` modules.
* The Celery now uses separate queue for translating, it is recommended to update to new worker setup which utilizes this, see :ref:`celery`.
* There is new addon in the 3.10.2 release, you might want to include them in case you modified the :setting:`WEBLATE_ADDONS`.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 3.10 to 3.11
~~~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

Notable configuration or dependencies changes:

* The Matomo integration settings were changed, please see :setting:`MATOMO_SITE_ID` and :setting:`MATOMO_URL`.
* The Celery configuration has changed (Celery app name is different), see :ref:`celery`.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 3.11 to 4.0
~~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

Notable configuration or dependencies changes:

* Python versions older than 3.6 are no longer supported, see :ref:`py3`
* The only database backends supported by Weblate are now PostgreSQL, MySQL and MariaDB.
* There are several new checks included in the :setting:`CHECK_LIST`.
* There are several removed, updated and new dependencies.
* The migration will take some time if you have big translation memory.
* The translation memory and fulltext search now resides in the database, you can remove the :file:`memory` and :file:`whoosh` folders in the :setting:`DATA_DIR` after the upgrade.
* The database migration now creates PostgreSQL extensions, Weblate user now has to be superuser or the extensions created manuall, see :ref:`dbsetup-postgres`.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 4.0 to 4.1
~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

Notable configuration or dependencies changes:

* There are several changes in :file:`settings_example.py`, most notable middleware changes, please adjust your settings accordingly.
* There are new file formats, you might want to include them in case you modified the :setting:`WEBLATE_FORMATS`.
* There are new quality checks, you might want to include them in case you modified the :setting:`CHECK_LIST`.
* There is change in ``DEFAULT_THROTTLE_CLASSES`` setting to allow reporting of rate limiting the in API.

.. seealso:: :ref:`generic-upgrade-instructions`

.. _py3:

Upgrading from Python 2 to Python 3
-----------------------------------

Weblate no longer supports Python older than 3.5. In case you are still running
on older version, please perform migration to Python 3 first on existing
version and upgrade later. See `Upgrading from Python 2 to Python 3 in the Weblate
3.11.1 documentation
<https://docs.weblate.org/en/weblate-3.11.1/admin/upgrade.html#upgrading-from-python-2-to-python-3>`_.

.. _database-migration:

Migrating from other databases to PostgreSQL
--------------------------------------------

If you are running Weblate on other dabatase than PostgreSQL, you should
migrate to PostgreSQL as that will be the only supported database backend in
the 4.0 release. The following steps will guide you in migrating your data
between the databases. Please remember to stop both web and Celery servers
prior to the migration, otherwise you might end up with inconsistent data.

Creating a database in PostgreSQL
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

It is usually a good idea to run Weblate in a separate database, and separate user account:

.. code-block:: sh

    # If PostgreSQL was not installed before, set the master password
    sudo -u postgres psql postgres -c "\password postgres"

    # Create a database user called "weblate"
    sudo -u postgres createuser -D -P weblate

    # Create the database "weblate" owned by "weblate"
    sudo -u postgres createdb -O weblate weblate

Migrating using Django JSON dumps
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The simplest approach for migration is to utilize Django JSON dumps. This works well for smaller installations. On bigger sites you might want to use pgloader instead, see :ref:`pgloader-migration`.

1. Add PostgeSQL as additional database connection to the :file:`settings.py`:

.. code-block:: python

    DATABASES = {
        'default': {
            # Database engine
            'ENGINE': 'django.db.backends.mysql',
            # Database name
            'NAME': 'weblate',
            # Database user
            'USER': 'weblate',
            # Database password
            'PASSWORD': 'password',
            # Set to empty string for localhost
            'HOST': 'database.example.com',
            # Set to empty string for default
            'PORT': '',
            # Additional database options
            'OPTIONS': {
                # In case of using an older MySQL server, which has MyISAM as a default storage
                # 'init_command': 'SET storage_engine=INNODB',
                # Uncomment for MySQL older than 5.7:
                # 'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
                # If your server supports it, see the Unicode issues above
               'charset': 'utf8mb4',
               # Change connection timeout in case you get MySQL gone away error:
               'connect_timeout': 28800,
            }
        },
        'postgresql': {
            # Database engine
            'ENGINE': 'django.db.backends.postgresql',
            # Database name
            'NAME': 'weblate',
            # Database user
            'USER': 'weblate',
            # Database password
            'PASSWORD': 'password',
            # Set to empty string for localhost
            'HOST': 'database.example.com',
            # Set to empty string for default
            'PORT': '',
        }
    }

2. Run migrations and drop any data inserted into the tables:

.. code-block:: sh

   weblate migrate --database=postgresql
   weblate sqlflush --database=postgresql | weblate dbshell --database=postgresql

3. Dump legacy database and import to PostgreSQL

.. code-block:: sh

   weblate dumpdata --all --output weblate.json
   weblate loaddata weblate.json --database=postgresql

4. Adjust :setting:`django:DATABASES` to use just PostgreSQL database as default,
   remove legacy connection.

Weblate should be now ready to run from the PostgreSQL database.

.. _pgloader-migration:

Migrating to PotsgreSQL using pgloader
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The `pgloader`_ is a generic migration tool to migrate data to PostgreSQL. You can use it to migrate Weblate database.

1. Adjust your :file:`settings.py` to use PostgeSQL as a database.

2. Migrate the schema in the PostgreSQL database:

   .. code-block:: sh

       weblate migrate
       weblate sqlflush | weblate dbshell

3. Run the pgloader to transfer the data. The following script can be used to migrate the database, but you might want to learn more about `pgloader`_ to understand what it does and tweak it to match your setup:

   .. code-block:: postgresql

       LOAD DATABASE
            FROM      mysql://weblate:password@localhost/weblate
            INTO postgresql://weblate:password@localhost/weblate

       WITH include no drop, truncate, create no tables, create no indexes, no foreign keys, disable triggers, reset sequences, data only

       ALTER SCHEMA 'weblate' RENAME TO 'public'
       ;


.. _pgloader: https://pgloader.io/

.. _pootle-migration:

Migrating from Pootle
---------------------

As Weblate was originally written as replacement from Pootle, it is supported
to migrate user accounts from Pootle. You can dump the users from Pootle and
import them using :djadmin:`importusers`.
