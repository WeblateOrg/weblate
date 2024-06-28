Upgrading Weblate
=================

Docker image upgrades
---------------------

The official Weblate Docker image (see :doc:`install/docker`) integrates all upgrade steps.
Typically, no manual interaction is needed beyond pulling the latest
(or at least newer) version.

.. seealso::

   :ref:`upgrading-docker`

.. _generic-upgrade-instructions:

Generic upgrade instructions
----------------------------

Always look for new changes to :ref:`requirements` before upgrading.
Once all requirements are installed or upgraded, ensure your
:file:`settings.py` matches the changes in the configuration (consult
:file:`settings_example.py` for correct values).

Always check :ref:`version-specific-instructions` before upgrading. If you are
skipping any version(s), be sure to follow instructions for all versions you are
skipping during such upgrade. It's sometimes better to upgrade gradually to
an intermediate version to ensure a smooth migration. Upgrading across multiple
releases should work, but is not as well tested as single version upgrades!

.. note::

    Always back up the full database before upgrading, so that you
    can roll back the database if the upgrade fails, see :doc:`backup`.

#. Stop the WSGI and Celery processes to avoid old processes running while upgrading.
   Otherwise incompatible changes in the database might occur.

#. Upgrade Weblate

   For pip installs it can be achieved by:

   .. code-block:: sh

      pip install -U "Weblate[all]==version"

   Or, if you just want to get the latest released version:

   .. code-block:: sh

      pip install -U "Weblate[all]"

   If you don't want to install all of the optional dependencies do:

   .. code-block:: sh

      pip install -U Weblate

   Using Git checkout, you need to fetch new source code and update your installation:

   .. code-block:: sh

        cd weblate-src
        git pull
        # Update Weblate inside your virtualenv
        . ~/weblate-env/bin/pip install -e '.[all]'
        # Install dependencies directly when not using virtualenv
        pip install --upgrade -e .
        # Install optional dependencies directly when not using virtualenv
        pip install --upgrade -e '.[all]'

#. New Weblate releases might have new :ref:`python-deps`, check if they cover
   the features you want.

#. Upgrade the configuration file by following either :file:`settings_example.py`, or
   :ref:`version-specific-instructions`.

#. Upgrade the database:

   .. code-block:: sh

        weblate migrate --noinput

#. Collect updated static files (see :ref:`server` and :ref:`static-files`):

   .. code-block:: sh

        weblate collectstatic --noinput --clear

#. Compress JavaScript and CSS files (optional, see :ref:`production-compress`):

   .. code-block:: sh

        weblate compress

#. If you are running an installation from Git, you should also regenerate locale
   files every time you upgrade. You can do this by invoking:

   .. code-block:: sh

        weblate compilemessages

#. Verify that your setup is sane (see also :ref:`production`):

   .. code-block:: sh

        weblate check --deploy

#. Restart the Celery worker (see :ref:`celery`).

.. _version-specific-instructions:

Version-specific instructions
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

If you are not running Weblate with a different database than PostgreSQL,
consider migrating to PostgreSQL for better performance by doing the following steps.
Remember to stop both, the web and Celery servers beforehand,
otherwise you might end up with inconsistent data.

Creating a database in PostgreSQL
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

It is usually a good idea to run Weblate in a separate database, and a separate user account:

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

The `pgloader`_ is a generic migration tool to migrate data to PostgreSQL.
You can use it to migrate your Weblate database.

1. Adjust your :file:`settings.py` to use PostgreSQL as database.

2. Migrate the schema in the PostgreSQL database:

   .. code-block:: sh

       weblate migrate
       weblate sqlflush | weblate dbshell

3. Run the pgloader to transfer the data.
The following script can be used to migrate the database, but you might
want to learn more about `pgloader`_ to better understand what it does,
and tweak it to match your setup:

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

As Weblate was originally written as a replacement for Pootle, it is supported
to migrate the user accounts from it. You can dump the users from Pootle and
import them using :wladmin:`importusers`.
