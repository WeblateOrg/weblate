.. _backup:

Backing up and moving Weblate
=============================

Automated backup
----------------

.. versionadded:: 3.9

Weblate has built-in support for creating service backups using `BorgBackup`_.
Borg creates space-effective encrypted backups which can be safely stored in
the cloud. The backups can be controlled in the management interface on the
:guilabel:`Backups` tab.

.. warning::

   Only PostgreSQL database is included in the automated backups. Other
   database engines have to be backed up manually. You are recommended to
   migrate to PostgreSQL, see :ref:`database-setup` and
   :ref:`database-migration`.

The backups using Borg are incremental and Weblate is configured to keep following backups:

* 14 daily backups
* 8 weekly backups
* 6 monthly backups

.. image:: /images/backups.png

.. _cloudbackup:

Using Weblate provisioned backup storage
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The easiest approach to backup your Weblate instance is to purchase `backup
service at weblate.org <https://weblate.org/support/#backup>`_. The process of
activating can be performed in few steps:

1. Purchase backup service on https://weblate.org/support/#backup.
2. Enter obtained key in the management interface, see :ref:`activate-support`.
3. Weblate will connect to the cloud service and obtain access information for the backups.
4. Turn on the new backup configuration on the :guilabel:`Backups` tab.
5. Backup Borg credentials in order to be able to restore the backups, see :ref:`borg-keys`.

.. hint::

   The manual step of turning on is there for your safety. Without your consent
   no data is sent to the backup repository obtained through the registration
   process.


Using custom backup storage
~~~~~~~~~~~~~~~~~~~~~~~~~~~

You can also use your own storage for the backups. SSH can be used to store backups
on the remote destination, the target server needs to have `BorgBackup`_
installed.

.. seealso::

   :doc:`borg:usage/general` in the Borg documentation

.. _borg-keys:

Borg encryption key
~~~~~~~~~~~~~~~~~~~

`BorgBackup`_ creates encrypted backups and without a passphrase you will not
be able to restore the backup. The passphrase is generated when adding new
backup service and you should copy it and keep it in a secure place.

In case you are using :ref:`cloudbackup`, please backup your private SSH key as
well — it is used to access your backups.

.. seealso::

   :doc:`borg:usage/init`

Restoring from BorgBackup
~~~~~~~~~~~~~~~~~~~~~~~~~

1. Restore access to your backup repository and prepare your backup passphrase.

2. List backup existing on the server using ``borg list REPOSITORY``.

3. Restore the desired backup to current directory using ``borg extract REPOSITORY::ARCHIVE``.

4. Restore the database from the SQL dump placed in the ``backup`` directory in the Weblate data dir (see :ref:`backup-dumps`).

5. Copy Weblate configuration (:file:`backups/settings.py`, see :ref:`backup-dumps`) to the correct location, see :ref:`configuration`.

6. Copy the whole restored data dir to location configured by :setting:`DATA_DIR`.

The Borg session might look like:

.. code-block:: console

   $ borg list /tmp/xxx
   Enter passphrase for key /tmp/xxx:
   2019-09-26T14:56:08                  Thu, 2019-09-26 14:56:08 [de0e0f13643635d5090e9896bdaceb92a023050749ad3f3350e788f1a65576a5]
   $ borg extract /tmp/xxx::2019-09-26T14:56:08
   Enter passphrase for key /tmp/xxx:

.. seealso::

   :doc:`borg:usage/list`,
   :doc:`borg:usage/extract`


.. _BorgBackup: https://www.borgbackup.org/


Manual backup
-------------

Depending on what you want to save, back up the type data Weblate stores in each respective place.

.. hint::

   In case you are doing manual backups, you might want to silent Weblate
   warning about lack of backups by adding ``weblate.I028`` to
   :setting:`django:SILENCED_SYSTEM_CHECKS` in :file:`settings.py` or
   :envvar:`WEBLATE_SILENCED_SYSTEM_CHECKS` for Docker.

   .. code-block:: python

      SILENCED_SYSTEM_CHECKS.append("weblate.I028")

Database
~~~~~~~~

The actual storage location depends on your database setup.

The database is the most important storage. Set up regular
backups of your database, without it all your translation setup will be gone.

Native database backup
++++++++++++++++++++++

The recommended approach is to do dump of the database using database native
tools such as :program:`pg_dump` or :program:`mysqldump`. It usually performs
better than Django backup and restores complete tables with all data.

You can restore this backup in newer Weblate release, it will perform any
necessary migrations when running in :djadmin:`django:migrate`. Please consult
:doc:`upgrade` on more detailed information how to perform upgrade between
versions.

Django database backup
++++++++++++++++++++++

Alternatively you can backup database using Django's :djadmin:`django:dumpdata`
command. That way the backup is database agnostic and can be used in case you
want to change database backend.

Prior to restoring you need to be running exactly same Weblate version as was
used when doing backups. This is necessary as the database structure does
change between releases and you would end up corrupting the data in some way.
After installing the same version, run all database migrations using
:djadmin:`django:migrate`.

Once this is done, some entries will be already created in the database and you
will have them in the database backup as well. The recommended approach is to
delete such entries manually using management shell (see :ref:`invoke-manage`):

.. code-block:: console

   weblate shell
   >>> from weblate.auth.models import User
   >>> User.objects.get(username='anonymous').delete()

Files
~~~~~

If you have enough backup space, simply backup the whole :setting:`DATA_DIR`. This
is safe bet even if it includes some files you don't want.
The following sections describe in detail what you should back up and what you
can skip.

.. _backup-dumps:

Dumped data for backups
+++++++++++++++++++++++

Stored in :setting:`DATA_DIR` ``/backups``.

Weblate dumps various data here, and you can include these files for more complete
backups. The files are updated daily (requires a running Celery beats server, see
:ref:`celery`). Currently, this includes:

* Weblate settings as :file:`settings.py` (there is also expanded version in :file:`settings-expanded.py`).
* PostgreSQL database backup as :file:`database.sql`.

The database backups are by default saved as plain text, but they can also be compressed
or entirely skipped by using :setting:`DATABASE_BACKUP`.

Version control repositories
++++++++++++++++++++++++++++

Stored in :setting:`DATA_DIR` ``/vcs``.

The version control repositories contain a copy of your upstream repositories
with Weblate changes. If you have push on commit enabled for all your
translation components, all Weblate changes are included upstream and you
do not have to backup the repositories on the Weblate side. They can be cloned
again from the upstream locations with no data loss.

SSH and GPG keys
++++++++++++++++

Stored in :setting:`DATA_DIR` ``/ssh`` and :setting:`DATA_DIR` ``/home``.

If you are using SSH or GPG keys generated by Weblate, you should back up these
locations, otherwise you will lose the private keys and you will have to
regenerate new ones.

User uploaded files
+++++++++++++++++++

Stored in :setting:`DATA_DIR` ``/media``.

You should back up user uploaded files (e.g. :ref:`screenshots`).

Command line for manual backup
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Using a cron job, you can set up a bash command to be executed on a daily basis, for instance:

.. code-block:: console

     $ XZ_OPT="-9" tar -Jcf ~/backup/weblate-backup-$(date -u +%Y-%m-%d_%H%M%S).xz backups vcs ssh home media fonts secret

The string between quotes after XZ_OPT allows you to choose your xz options, for instance the amount of memory used for compression; see https://linux.die.net/man/1/xz

You can adjust the list of folders and files to your needs. For instance, to avoid saving the translation memory (in backups folder), you could use:

.. code-block:: console

     $ XZ_OPT="-9" tar -Jcf ~/backup/weblate-backup-$(date -u +%Y-%m-%d_%H%M%S).xz backups/database.sql backups/settings.py vcs ssh home media fonts secret


Celery tasks
------------

The Celery tasks queue might contain some info, but is usually not needed
for a backup. At most you will lose updates that have not yet been processed to translation
memory. It is recommended to perform the fulltext or repository updates upon
restoring anyhow, so there is no problem in losing these.

.. seealso::

   :ref:`celery`

Restoring manual backup
-----------------------

1. Restore all data you have backed up.

2. Update all repositories using :djadmin:`updategit`.

   .. code-block:: sh

         weblate updategit --all

Moving a Weblate installation
------------------------------

Relocate your installation to a different system
by following the backup and restore instructions above.

.. seealso::

   :ref:`py3`,
   :ref:`database-migration`
