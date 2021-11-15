Upgrading Weblate
=================

Docker-image upgrades
---------------------

The official Docker image (see :doc:`install/docker`) integrates all steps.
No manual interaction is needed beyond pulling the latest version.

.. _generic-upgrade-instructions:

Generic upgrade instructions
----------------------------

Always look for new changes to :ref:`requirements` before upgrading.
Once all requirements are installed or upgraded, ensure your
:file:`settings.py` matches :file:`settings_example.py`.

Always check :ref:`version-specific-instructions` before upgrading.
Either follow the instructions for each new version, or go with the less
tested option of upgrading across multiple releases by following all the
instructions for them at once.

.. note::

    Always back up the full database before upgrading so that you
    can revert your changes if the upgrade fails, see :doc:`backup`.

#. Stop the WSGI and Celery processes to avoid old processes running while upgrading.
   Otherwise incompatible changes in the database might occur.

#. Upgrade the Weblate source code.

   For pip installs it can be achieved by:

   .. code-block:: sh

      pip install -U "Weblate[all]"

   If you don't want to install all of the optional dependencies do:

   .. code-block:: sh

      pip install -U Weblate

   Git checkout can also fetch the new source code and upgrades your installation:

   .. code-block:: sh

        cd weblate-src
        git pull
        # Update Weblate inside your virtualenv
        . ~/weblate-env/bin/pip install -e .
        # Install dependencies directly when not using virtualenv
        pip install --upgrade -r requirements.txt
        # Install optional dependencies directly when not using virtualenv
        pip install --upgrade -r requirements-optional.txt

#. New Weblate releases might have new :ref:`optional-deps`, please check if they cover
   the features you want.

#. Upgrade the configuration file by following :file:`settings_example.py` or
   :ref:`version-specific-instructions`.

#. Upgrade the Weblate database-structure:

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

#. Verify your setup is sane (see also :ref:`production`):

   .. code-block:: sh

        weblate check --deploy

#. Restart the Celery worker (see :ref:`celery`).

.. _version-specific-instructions:

Version-specific instructions
-----------------------------

Upgrading from 2.x
~~~~~~~~~~~~~~~~~~

If you are upgrading from a 2.x release, always first upgrade to 3.0.1
and then continue upgrading in the 3.x series.
Upgrades skipping this step are not supported and *will break*.

.. seealso::

   `Upgrading from 2.20 to 3.0 in the Weblate 3.0 documentation <https://docs.weblate.org/en/weblate-3.0.1/admin/upgrade.html#upgrade-3>`_

Upgrading from 3.x
~~~~~~~~~~~~~~~~~~

If you are upgrading from 3.x release, always first upgrade to 4.0.4 or 4.1.1
and then continue upgrading in the 4.x series.
Upgrades skipping this step are not supported and *will break*.

.. seealso::

   `Upgrading from 3.11 to 4.0 in the Weblate 4.0 documentation <https://docs.weblate.org/en/weblate-4.0.4/admin/upgrade.html#upgrade-from-3-11-to-4-0>`_

Upgrading from 4.0 to 4.1
~~~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` to upgrade.

Notable configuration- and dependency changes:

* Several changes in :file:`settings_example.py`, most notable middleware changes.
  Please adjust your settings accordingly.
* New file formats, you might want to include them in case you modified the :setting:`WEBLATE_FORMATS`.
* New quality checks, you might want to include them in case you modified the :setting:`CHECK_LIST`.
* A change in the ``DEFAULT_THROTTLE_CLASSES`` setting allowing reporting rate limiting in the API.
* Some new and updated requirements.
* A change in :setting:`django:INSTALLED_APPS`.
* The ``MT_DEEPL_API_VERSION`` setting has been removed in Version 4.7.
  The :ref:`deepl` machine translation now uses the new :setting:`MT_DEEPL_API_URL` instead.
  You might need to adjust :setting:`MT_DEEPL_API_URL` to match your subscription.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 4.1 to 4.2
~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` to upgrade.

Notable configuration- and dependencies changes:

* Upgrading from 3.x releases is not longer supported, please upgrade to 4.0 or 4.1 first.
* Some new and updated requirements.
* Several changes in :file:`settings_example.py`, most notable new middleware and changed application ordering.
* The keys for JSON-based formats no longer include a leading dot.
  Strings are adjusted during the database migration, but external components may need adjusting if you rely on keys in exports or API.
* The Celery configuration no longer uses a ``memory`` queue.
  Please adjust your startup scripts and ``CELERY_TASK_ROUTES`` setting to reflect this.
* The Weblate domain is now configured in the settings, see :setting:`SITE_DOMAIN` (or :envvar:`WEBLATE_SITE_DOMAIN`).
  You will have to configure it before running Weblate.
* The username and e-mail fields in the user database should now be unique regardless of case.
  It was mistakenly not enforced with PostgreSQL.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 4.2 to 4.3
~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` to upgrade.

Notable configuration- and dependency changes:

* Some changes in quality checks, you might want to include them in case you modified the :setting:`CHECK_LIST`.
* The source language attribute was moved from project to a component exposed in the API. Upgrade :ref:`wlc` if you are using it.
* The database migration to 4.3 might take a long time depending on the number of strings you are translating.
  (Expect around one hour of migration time per 100,000 source strings.)
* One change in :setting:`django:INSTALLED_APPS`.
* A new setting :setting:`SESSION_COOKIE_AGE_AUTHENTICATED` complements :setting:`django:SESSION_COOKIE_AGE`.
* If you were using :command:`hub` or :command:`lab` to integrate with GitLab or GitHub,
  you must reconfigure this using :setting:`GITHUB_CREDENTIALS` and :setting:`GITLAB_CREDENTIALS`.

.. versionchanged:: 4.3.1

   * The Celery configuration was changed to add a ``memory`` queue. Please adjust your startup scripts and ``CELERY_TASK_ROUTES`` setting.

.. versionchanged:: 4.3.2

   * The ``post_update`` method of addons now takes an extra ``skip_push`` parameter.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 4.3 to 4.4
~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` to upgrade.

Notable configuration- and dependencies changes:

* A change in :setting:`django:INSTALLED_APPS`, requires ``weblate.configuration`` to be added there.
* Django 3.1 is now required.
* If you are using MySQL or MariaDB, the minimal required versions have increased, see :ref:`mysql`.

.. versionchanged:: 4.4.1

   * :ref:`mono_gettext` now uses both ``msgid`` and ``msgctxt`` when present.
   This changes identification of translation strings in such files, breaking links to Weblate extended data such as screenshots or review states.
   Please ensure you commit pending changes in such files before upgrading.
   It is recommeded to force-load affected components using :djadmin:`loadpo`.
   * Increasing the required version of translate-toolkit addresses several file-format issues.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 4.4 to 4.5
~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` to upgrade.

Notable configuration- and dependencies changes:

* The migration might take considerable time to process big glossaries.
* Glossaries are now stored as regular components.
* The glossary API is removed, use the regular translation API to access glossaries.
* A change in :setting:`django:INSTALLED_APPS` - ``weblate.metrics`` should be added.

.. versionchanged:: 4.5.1

   * The `pyahocorasick` module is a new dependency.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 4.5 to 4.6
~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` to upgrade.

Notable configuration- and dependencies changes:

* New file formats, you might want to include them in case you modified the :setting:`WEBLATE_FORMATS`.
* The API for creating components now automatically uses :ref:`internal-urls`, see :http:post:`/api/projects/(string:project)/components/`.
* A change in dependencies and :setting:`django:PASSWORD_HASHERS` to prefer Argon2 for password hashing.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 4.6 to 4.7
~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` to upgrade.

Notable configuration- and dependency changes:

* Several changes in :file:`settings_example.py`, most notably middleware changes (:setting:`django:MIDDLEWARE`).
  Please adjust your settings accordingly.
* The :ref:`deepl` machine translation now has a generic :setting:`MT_DEEPL_API_URL` setting to adapt to different subscription models more flexibly.
  The ``MT_DEEPL_API_VERSION`` setting is no longer used.
* Django 3.2 is now required.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 4.7 to 4.8
~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` to upgrade.

There are no additional upgrade steps needed in this release.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 4.8 to 4.9
~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` to upgrade.

* There is a change in storing metrics. The upgrade can take a while on larger sites.

.. seealso:: :ref:`generic-upgrade-instructions`

.. _py3:

Upgrading from Python 2 to Python 3
-----------------------------------

Weblate no longer supports Python older than 3.5.
If you are still running an older version, please migrate to Python 3 first
on the existing version and upgrade it later.
See `Upgrading from Python 2 to Python 3 in the Weblate 3.11.1 documentation
<https://docs.weblate.org/en/weblate-3.11.1/admin/upgrade.html#upgrading-from-python-2-to-python-3>`_.

.. _database-migration:

Migrating from other databases to PostgreSQL
--------------------------------------------

If you are not running Weblate with a different databse,
you should migrate your data to PostgreSQL for better performance by doing the following steps.
Stop both the web- and Celery servers beforehand, otherwise you might end up with inconsistent data.

Creating a database in PostgreSQL
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

It is usually a good idea to run Weblate in a separate database and -user account:

.. code-block:: sh

    # If PostgreSQL was not installed before, set the main password
    sudo -u postgres psql postgres -c "\password postgres"

    # Create a database user called "weblate"
    sudo -u postgres createuser -D -P weblate

    # Create the database "weblate" owned by "weblate"
    sudo -u postgres createdb -E UTF8 -O weblate weblate

Migrating using Django JSON-dumps
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The simplest migration approach is to utilize Django JSON-dumps.
This works well for smaller installations.
On bigger sites you might want to use pgloader instead, see :ref:`pgloader-migration`.

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
            "PASSWORD": "yourpassword",
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
                # Change connection timeout in case you get an "MySQL gone away" error:
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
            "PASSWORD": "yourpassword",
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

3. Dump the legacy database and import it to PostgreSQL

.. code-block:: sh

   weblate dumpdata --all --output weblate.json
   weblate loaddata weblate.json --database=postgresql

4. Adjust :setting:`django:DATABASES` to only use a PostgreSQL database by default
   and remove legacy connections.

Weblate should now be ready to run from the PostgreSQL database.

.. _pgloader-migration:

Migrating to PostgreSQL using pgloader
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The `pgloader`_ is a generic migration tool to migrate data to PostgreSQL.
You can use it to migrate your Weblate database.

1. Adjust your :file:`settings.py` to use PostgreSQL as your database.

2. Migrate the schema in the PostgreSQL database:

   .. code-block:: sh

       weblate migrate
       weblate sqlflush | weblate dbshell

3. Run the pgloader to transfer the data.
The following script can be used to migrate the database, but there is more to learn about `pgloader`_
so you can tweak it to match your setup:

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

Migrate user accounts by dumping the list of users from Pootle and import them using :djadmin:`importusers`.
