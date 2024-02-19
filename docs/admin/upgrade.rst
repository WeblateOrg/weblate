Upgrading Weblate
=================

Docker image upgrades
---------------------

The official Docker image (see :doc:`install/docker`) has all Weblate upgrade steps
integrated. There are typically no manual steps needed besides pulling latest version.

.. seealso::

   :ref:`upgrading-docker`

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

#. Stop wsgi and Celery processes. The upgrade can perform incompatible changes in the
   database, so it is always safer to avoid old processes running while upgrading.

#. Upgrade Weblate code.

   For pip installs it can be achieved by:

   .. code-block:: sh

      pip install -U "Weblate[all]==version"

   Or, if you just want to get the latest released version:

   .. code-block:: sh

      pip install -U "Weblate[all]"

   If you don't want to install all of the optional dependencies do:

   .. code-block:: sh

      pip install -U Weblate

   With Git checkout you need to fetch new source code and update your installation:

   .. code-block:: sh

        cd weblate-src
        git pull
        # Update Weblate inside your virtualenv
        . ~/weblate-env/bin/pip install -e '.[all]'
        # Install dependencies directly when not using virtualenv
        pip install --upgrade -r requirements.txt
        # Install optional dependencies directly when not using virtualenv
        pip install --upgrade -r requirements-optional.txt

#. New Weblate release might have new :ref:`python-deps`, please check if they cover
   features you want.

#. Upgrade configuration file, refer to :file:`settings_example.py` or
   :ref:`version-specific-instructions` for needed steps.

#. Upgrade database structure:

   .. code-block:: sh

        weblate migrate --noinput

#. Collect updated static files (see :ref:`server` and :ref:`static-files`):

   .. code-block:: sh

        weblate collectstatic --noinput --clear

#. Compress JavaScript and CSS files (optional, see :ref:`production-compress`):

   .. code-block:: sh

        weblate compress

#. If you are running version from Git, you should also regenerate locale files
   every time you are upgrading. You can do this by invoking:

   .. code-block:: sh

        weblate compilemessages

#. Verify that your setup is sane (see also :ref:`production`):

   .. code-block:: sh

        weblate check --deploy

#. Restart Celery worker (see :ref:`celery`).


.. _version-specific-instructions:

Version specific instructions
-----------------------------

.. versionchanged:: 5.0

   Version specific instructions are now included in the release notes, see :doc:`/changes`.

Upgrade from an older major version
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Upgrades across major versions are not supported. Always upgrade to the latest
patch level for the initial major release. Upgrades skipping this step are not
supported and will break.

* If you are upgrading from the 2.x release, always first upgrade to 3.0.1.
* If you are upgrading from the 3.x release, always first upgrade to 4.0.4.
* If you are upgrading from the 4.x release, always first upgrade to 5.0.2.

.. seealso::

   `Upgrade from 2.20 to 3.0 in Weblate 3.0 documentation <https://docs.weblate.org/en/weblate-3.0.1/admin/upgrade.html#upgrade-3>`_,
   `Upgrade from 3.11 to 4.0 in Weblate 4.0 documentation <https://docs.weblate.org/en/weblate-4.0.4/admin/upgrade.html#upgrade-from-3-11-to-4-0>`_,,
   `Upgrade from 4.x to 5.0.2 in Weblate 5.0 documentation <https://docs.weblate.org/en/weblate-5.0.2/changes.html>`_

.. _database-migration:

Migrating from other databases to PostgreSQL
--------------------------------------------

If you are running Weblate on other dabatase than PostgreSQL, you should
consider migrating to PostgreSQL as Weblate performs best with it. The following
steps will guide you in migrating your data between the databases. Please
remember to stop both web and Celery servers prior to the migration, otherwise
you might end up with inconsistent data.

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

As Weblate was originally written as replacement from Pootle, it is supported
to migrate user accounts from Pootle. You can dump the users from Pootle and
import them using :wladmin:`importusers`.
