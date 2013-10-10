Upgrading Weblate
=================

Upgrading
---------

.. _generic-upgrade-instructions:

Generic upgrade instructions
++++++++++++++++++++++++++++

.. versionchanged:: 1.2
    Since version 1.2 the migration is done using South module, to upgrade to 1.2, 
    please see :ref:`version-specific-instructions`.

Before upgrading, please check current :ref:`requirements` as they might have
changed.

To upgrade database structure, you should run following commands:

.. code-block:: sh

    ./manage.py syncdb
    ./manage.py migrate

To upgrade default set of privileges definitions (optional), run:

.. code-block:: sh

    ./manage.py setupgroups

To upgrade default set of language definitions (optional), run:

.. code-block:: sh

    ./manage.py setuplang

.. _version-specific-instructions:

Version specific instructions
+++++++++++++++++++++++++++++

Upgrade from 0.5 to 0.6
~~~~~~~~~~~~~~~~~~~~~~~

On upgrade to version 0.6 you should run :samp:`./manage.py syncdb` and
:samp:`./manage.py setupgroups --move` to setup access control as described
in installation section.

Upgrade from 0.6 to 0.7
~~~~~~~~~~~~~~~~~~~~~~~

On upgrade to version 0.7 you should run :samp:`./manage.py syncdb` to
setup new tables and :samp:`./manage.py rebuild_index` to build index for
fulltext search.

Upgrade from 0.7 to 0.8
~~~~~~~~~~~~~~~~~~~~~~~

On upgrade to version 0.8 you should run :samp:`./manage.py syncdb` to setup
new tables, :samp:`./manage.py setupgroups` to update privileges setup and
:samp:`./manage.py rebuild_index` to rebuild index for fulltext search.

Upgrade from 0.8 to 0.9
~~~~~~~~~~~~~~~~~~~~~~~

On upgrade to version 0.9 file structure has changed. You need to move
:file:`repos` and :file:`whoosh-index` to :file:`weblate` folder. Also running
:samp:`./manage.py syncdb`, :samp:`./manage.py setupgroups` and
:samp:`./manage.py setuplang` is recommended to get latest updates of 
privileges and language definitions.

Upgrade from 0.9 to 1.0
~~~~~~~~~~~~~~~~~~~~~~~

On upgrade to version 1.0 one field has been added to database, you need to
invoke following SQL command to adjust it:

.. code-block:: sql

    ALTER TABLE `trans_subproject` ADD `template` VARCHAR(200);

Upgrade from 1.0 (1.1) to 1.2
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

On upgrade to version 1.2, the migration procedure has changed. It now uses
South for migrating database. To switch to this new migration schema, you need
to run following commands:

.. code-block:: sh

    ./manage.py syncdb
    ./manage.py migrate trans 0001 --fake
    ./manage.py migrate accounts 0001 --fake
    ./manage.py migrate lang 0001 --fake

Also please note that there are several new requirements and version 0.8 of
django-registration is now being required, see :ref:`requirements` for more
details.

Once you have done this, you can use :ref:`generic-upgrade-instructions`.

Upgrade from 1.2 to 1.3
~~~~~~~~~~~~~~~~~~~~~~~

Since 1.3, :file:`settings.py` is not shipped with Weblate, but only example
settings as :file:`settings_example.py` it is recommended to use it as new base
for your setup.

Upgrade from 1.4 to 1.5
~~~~~~~~~~~~~~~~~~~~~~~

Several internal modules and paths have been renamed and changed, please adjust
your :file:`settings.py` to match that (consult :file:`settings_example.py` for
correct values).

* Many modules lost their ``weblate.`` prefix.
* Checks were moved to submodules.
* Locales were moved to top level directory.

The migration of database structure to 1.5 might take quite long, it is
recommended to put your site offline, while the migration is going on.


.. note::

    If you have update in same directory, stale :file:`*.pyc` files might be
    left around and cause various import errors. To recover from this, delete
    all of them in Weblate's directory, for example by 
    ``find . -name '*.pyc' - delete``.

Upgrade from 1.6 to 1.7
~~~~~~~~~~~~~~~~~~~~~~~

The migration of database structure to 1.7 might take quite long, it is
recommended to put your site offline, while the migration is going on.

If you are translating monolingual files, it is recommended to rerun quality
checks as they might have been wrongly linked to units in previous versions.

Upgrade from 1.7 to 1.8
~~~~~~~~~~~~~~~~~~~~~~~

The migration of database structure to 1.8 might take quite long, it is
recommended to put your site offline, while the migration is going on.

Authentication setup has been changed and some internal modules have changed
name, please adjust your :file:`settings.py` to match that (consult
:file:`settings_example.py` for correct values).

Also please note that there are several new requirements, see
:ref:`requirements` for more details.

.. _pootle-migration:

Migrating from Pootle
---------------------

As Weblate was originally written as replacement from Pootle, it is supported
to migrate user accounts from Pootle. All you need to do is to copy
``auth_user`` table from Pootle, user profiles will be automatically created
for users as they log in and they will be asked to update their settings.
Alternatively you can use :djadmin:`importusers` to import dumped user
credentials.
