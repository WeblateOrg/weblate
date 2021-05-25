Upgrading Weblate
=================

Docker image upgrades
---------------------

The official Docker image (see :doc:`install/docker`) has all reqiored upgrade
steps integrated. No manual interaction is needed besides pulling the latest version.

.. _generic-upgrade-instructions:

Generic upgrade instructions
----------------------------

Before upgrading, please check the current :ref:`requirements`, as they might have
changed. Once all requirements are installed or upgraded, please adjust your
:file:`settings.py` to match changes in the configuration (consult
:file:`settings_example.py` for correct values).

Always check :ref:`version-specific-instructions` before upgrading. In case you
are skipping some versions, please follow instructions for all versions you are
skipping in the upgrade. Sometimes it is better to upgrade to some intermediate
version to ensure a smooth migration. Upgrading across multiple releases should
work, but is not as extensively tested as single version upgrades.

.. note::

    It is recommended to perform a full database backup prior to upgrading so that you
    can roll back the database in case the upgrade fails, see :doc:`backup`.

#. Stop the WSGI and Celery processes. The upgrade can perform incompatible changes in
   the database, so it is always safer to avoid having old processes running while
   upgrading.

#. Upgrade the Weblate source code.

   For pip installs it can be achieved by:

   .. code-block:: sh

      pip install -U Weblate

   With Git checkout you need to fetch the new source code and update your installation:

   .. code-block:: sh

        cd weblate-src
        git pull
        # Update Weblate inside your virtualenv
        . ~/weblate-env/bin/pip install -e .
        # Install dependencies directly when not using virtualenv
        pip install --upgrade -r requirements.txt

#. Upgrade the configuration file, by referring to :file:`settings_example.py` or
   :ref:`version-specific-instructions` for needed steps.

#. Upgrade the Weblate database structure:

   .. code-block:: sh

        weblate migrate --noinput

#. Collect updated static files (see :ref:`server` and :ref:`static-files`):

   .. code-block:: sh

        weblate collectstatic --noinput

#. Compress JavaScript and CSS files (optional, see :ref:`production-compress`):

   .. code-block:: sh

        weblate compress

#. If you are running a Weblate version from Git, you should also regenerate locale
   files every time you upgrade. You can do this by invoking:

   .. code-block:: sh

        weblate compilemessages

#. Verify that your setup is sane (see also :ref:`production`):

   .. code-block:: sh

        weblate check --deploy

#. Restart the Celery worker (see :ref:`celery`).


.. _version-specific-instructions:

Version specific instructions
-----------------------------

Upgrade from 2.x
~~~~~~~~~~~~~~~~

If you are upgrading from a 2.x release, always first upgrade to 3.0.1 and then
continue upgrading in the 3.x series. Upgrades skipping this step are not
supported and will break.

.. seealso::

   `Upgrade from 2.20 to 3.0 in the Weblate 3.0 documentation <https://docs.weblate.org/en/weblate-3.0.1/admin/upgrade.html#upgrade-3>`_

Upgrade from 3.x
~~~~~~~~~~~~~~~~

If you are upgrading from 3.x release, always first upgrade to 4.0.4 or 4.1.1
and then continue upgrading in the 4.x series. Upgrades skipping this step are
not supported and will break.

.. seealso::

   `Upgrade from 3.11 to 4.0 in Weblate 4.0 documentation <https://docs.weblate.org/en/weblate-4.0.4/admin/upgrade.html#upgrade-from-3-11-to-4-0>`_

Upgrade from 4.0 to 4.1
~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` to perform the upgrade.

Notable configuration or dependencies changes:

* There are several changes in :file:`settings_example.py`, most notable middleware changes, please adjust your settings accordingly.
* There are new file formats, you might want to include them in case you modified the :setting:`WEBLATE_FORMATS`.
* There are new quality checks, you might want to include them in case you modified the :setting:`CHECK_LIST`.
* There is a change in ``DEFAULT_THROTTLE_CLASSES`` setting to allow reporting of rate limiting in the API.
* There are some new and updated requirements.
* There is a change in :setting:`django:INSTALLED_APPS`.
* The ``MT_DEEPL_API_VERSION`` setting has been removed in version 4.7. The :ref:`deepl` machine translation now uses the new :setting:`MT_DEEPL_API_URL` instead. You might need to adjust :setting:`MT_DEEPL_API_URL` to match your subscription.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 4.1 to 4.2
~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` to perform the upgrade.

Notable configuration or dependencies changes:

* Upgrading from 3.x releases is not longer supported, please upgrade to 4.0 or 4.1 first.
* There are some new and updated requirements.
* There are several changes in :file:`settings_example.py`, most notable new middleware and changed application ordering.
* The keys for JSON based formats no longer include a leading dot. The strings are adjusted during the database migration, but external components may need to be adjusted in case you rely on keys in exports or API.
* The Celery configuration was changed to no longer use a ``memory`` queue. Please adjust your startup scripts and ``CELERY_TASK_ROUTES`` setting to reflect this.
* The Weblate domain is now configured in the settings, see :setting:`SITE_DOMAIN` (or :envvar:`WEBLATE_SITE_DOMAIN`). You will have to configure it before running Weblate.
* The username and e-mail fields on user database now should be unique regardless of case. It was mistakenly not enforced with PostgreSQL.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 4.2 to 4.3
~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

Notable configuration or dependency changes:

* There are some changes in quality checks, you might want to include them in case you modified the :setting:`CHECK_LIST`.
* The source language attribute was moved from project to a component exposed in the API. You will need to update :ref:`wlc` if you are using it.
* The database migration to 4.3 might take a long time depending on the number of strings you are translating (expect around one hour of migration time per 100,000 source strings).
* There is a change in :setting:`django:INSTALLED_APPS`.
* There is a new setting :setting:`SESSION_COOKIE_AGE_AUTHENTICATED` which complements :setting:`django:SESSION_COOKIE_AGE`.
* If you were using :command:`hub` or :command:`lab` to integrate with GitHub or GitLab, you will need to reconfigure this using :setting:`GITHUB_CREDENTIALS` and :setting:`GITLAB_CREDENTIALS`.

.. versionchanged:: 4.3.1

   * The Celery configuration was changed to add a ``memory`` queue. Please adjust your startup scripts and ``CELERY_TASK_ROUTES`` setting.

.. versionchanged:: 4.3.2

   * The ``post_update`` method of addons now takes an extra ``skip_push`` parameter.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 4.3 to 4.4
~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` in order to perform the upgrade.

Notable configuration or dependencies changes:

* A change in :setting:`django:INSTALLED_APPS`, requires ``weblate.configuration`` to be added there.
* Django 3.1 is now required.
* If you are using MySQL or MariaDB, the minimal required versions have increased, see :ref:`mysql`.

.. versionchanged:: 4.4.1

   * :ref:`mono_gettext` now uses both ``msgid`` and ``msgctxt`` when present. This changes identification of translation strings in such files, breaking links to Weblate extended data such as screenshots or review states. Please ensure you commit pending changes in such files prior to upgrading. It is recommeded to force load affected components using :djadmin:`loadpo`.
   * The increased minimal required version of translate-toolkit addresses several file-format issues.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 4.4 to 4.5
~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

Notable configuration or dependencies changes:

* The migration might take considerable time if you had big glossaries.
* Glossaries are now stored as regular components.
* The glossary API is removed, use regular translation API to access glossaries.
* There is a change in :setting:`django:INSTALLED_APPS` - ``weblate.metrics`` should be added.

.. versionchanged:: 4.5.1

   * There is a new dependency on the `pyahocorasick` module.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 4.5 to 4.6
~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` to perform the upgrade.

Notable configuration or dependencies changes:

* There are new file formats, you might want to include them in case you modified the :setting:`WEBLATE_FORMATS`.
* The API for creating components now automatically uses :ref:`internal-urls`, see :http:post:`/api/projects/(string:project)/components/`.
* There is a change in dependencies and :setting:`django:PASSWORD_HASHERS` to prefer Argon2 for password hashing.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 4.6 to 4.7
~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` to perform the upgrade.

Notable configuration or dependency changes:

* There are several changes in :file:`settings_example.py`, most notable middleware changes (:setting:`django:MIDDLEWARE`), please adjust your settings accordingly.
* The :ref:`deepl` machine translation now has a generic :setting:`MT_DEEPL_API_URL` setting to adapt to different subscription models more flexibly.
  The ``MT_DEEPL_API_VERSION`` setting is no longer used.

.. seealso:: :ref:`generic-upgrade-instructions`

.. _py3:

Upgrading from Python 2 to Python 3
-----------------------------------

Weblate no longer supports Python older than 3.5. In case you are still running
on older version, please perform a migration to Python 3 first on the existing
version and upgrade it later. See `Upgrading from Python 2 to Python 3 in the Weblate
3.11.1 documentation
<https://docs.weblate.org/en/weblate-3.11.1/admin/upgrade.html#upgrading-from-python-2-to-python-3>`_.

.. _database-migration:

Migrating from other databases to PostgreSQL
--------------------------------------------

If you are running Weblate on other dabatase than PostgreSQL, you should
migrate to PostgreSQL as that will be the only supported database back-end in
the 4.0 release. The following steps will guide you in migrating your data
between the databases. Please remember to stop both web and Celery servers
prior to the migration, otherwise you might end up with inconsistent data.

Creating a database in PostgreSQL
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

It is usually a good idea to run Weblate in a separate database, and separate user account:

.. code-block:: sh

    # If PostgreSQL was not installed before, set the main password
    sudo -u postgres psql postgres -c "\password postgres"

    # Create a database user called "weblate"
    sudo -u postgres createuser -D -P weblate

    # Create the database "weblate" owned by "weblate"
    sudo -u postgres createdb -E UTF8 -O weblate weblate

Migrating using Django JSON dumps
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The simplest migration approach is to utilize Django JSON dumps. This works well for smaller installations. On bigger sites you might want to use pgloader instead, see :ref:`pgloader-migration`.

1. Add PostgreSQL as additional database connection to the :file:`settings.py`:

.. code-block:: python

    DATABASES = {
        "default": {
            # Database engine
            "ENGINE": "django.db.backends.mysql",
            # Database name
            "NAME": "weblate",
            # Database user
            "USER": "weblate",
            # Database password
            "PASSWORD": "password",
            # Set to empty string for localhost
            "HOST": "database.example.com",
            # Set to empty string for default
            "PORT": "",
            # Additional database options
            "OPTIONS": {
                # In case of using an older MySQL server, which has MyISAM as a default storage
                # 'init_command': 'SET storage_engine=INNODB',
                # Uncomment for MySQL older than 5.7:
                # 'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
                # If your server supports it, see the Unicode issues above
                "charset": "utf8mb4",
                # Change connection timeout in case you get MySQL gone away error:
                "connect_timeout": 28800,
            },
        },
        "postgresql": {
            # Database engine
            "ENGINE": "django.db.backends.postgresql",
            # Database name
            "NAME": "weblate",
            # Database user
            "USER": "weblate",
            # Database password
            "PASSWORD": "password",
            # Set to empty string for localhost
            "HOST": "database.example.com",
            # Set to empty string for default
            "PORT": "",
        },
    }

2. Run migrations and drop any data inserted into the tables:

.. code-block:: sh

   weblate migrate --database=postgresql
   weblate sqlflush --database=postgresql | weblate dbshell --database=postgresql

3. Dump legacy database and import to PostgreSQL

.. code-block:: sh

   weblate dumpdata --all --output weblate.json
   weblate loaddata weblate.json --database=postgresql

4. Adjust :setting:`django:DATABASES` to use a PostgreSQL database exclusively by default,
   remove legacy connection.

Weblate should be now ready to run from the PostgreSQL database.

.. _pgloader-migration:

Migrating to PostgreSQL using pgloader
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The `pgloader`_ is a generic migration tool to migrate data to PostgreSQL. You can use it to migrate Weblate database.

1. Adjust your :file:`settings.py` to use PostgreSQL as a database.

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

Migrate user accounts by dumping the list of users from Pootle and
import them using :djadmin:`importusers`.
