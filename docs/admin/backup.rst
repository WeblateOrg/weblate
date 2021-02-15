.. _backup:

Backing up and moving Weblate
=============================

Automated backup using BorgBackup
---------------------------------

.. versionadded:: 3.9

Weblate has built-in support for creating service backups using `BorgBackup`_.
Borg creates space-effective encrypted backups which can be safely stored in
the cloud. The backups can be controlled in the management interface from the
:guilabel:`Backups` tab.

.. versionchanged:: 4.4.1

   Both PostgreSQL and MySQL/MariaDB databases are included in the automated backups.

The backups using Borg are incremental and Weblate is configured to keep following backups:

* Daily backups for 14 days back
* Weekly backups for 8 weeks back
* Monthly backups for 6 months back

.. image:: /images/backups.png

.. _borg-keys:

Borg encryption key
~~~~~~~~~~~~~~~~~~~

`BorgBackup`_ creates encrypted backups and you wouldn’t be able to restore them
without the passphrase. The passphrase is generated when adding a new
backup service and you should copy it and keep it in a secure place.

If you are using :ref:`cloudbackup`, please backup your private SSH key
too, as it’s used to access your backups.

.. seealso::

   :doc:`borg:usage/init`

.. _cloudbackup:

Weblate provisioned backup storage
----------------------------------

The easiest way of backing up your Weblate instance is purchasing the `backup
service at weblate.org <https://weblate.org/support/#backup>`_. This
is how you get it running:

1. Purchase the `Backup service` on https://weblate.org/support/#backup.
2. Enter the obtained key in the management interface, see :ref:`activate-support`.
3. Weblate connects to the cloud service and obtains access info for the backups.
4. Turn on the new backup configuration from the :guilabel:`Backups` tab.
5. Backup your Borg credentials to be able to restore the backups, see :ref:`borg-keys`.

.. hint::

   The manual step of turning everything on is there for your safety.
   Without your consent no data is sent to the backup repository obtained
   through the registration process.

.. _custombackup:

Using custom backup storage
---------------------------

You can also use your own storage for the backups. SSH can be used to store
backups in the remote destination, the target server needs to have
`BorgBackup`_ installed.

.. seealso::

   :doc:`borg:usage/general` in the Borg documentation

Local filesystem
~~~~~~~~~~~~~~~~

It is recommended to specify the absolute path for the local backup, for example
`/path/to/backup`. The directory has to be writable by the user running Weblate
(see :ref:`file-permissions`). If it doesn't exist, Weblate attempts
to create it but needs the appropriate permissions to do so.

.. hint::

    When running Weblate in Docker, please ensure the backup location
    is exposed as a volume from the Weblate container. Otherwise the backups
    will be discarded by Docker upon restarting the container it is in.

    One option is to place backups into an existing volume, for example
    :file:`/app/data/borgbackup`. This is an existing volume in the container.

    You can also add a new container for the backups in the Docker Compose file
    for example by using :file:`/borgbackup`:

    .. code-block:: yaml

        services:
          weblate:
            volumes:
              - /home/weblate/data:/app/data
              - /home/weblate/borgbackup:/borgbackup

    The directory where backups will be stored have to be owned by UID 1000,
    otherwise Weblate won’t be able to write the backups there.

Remote backups
~~~~~~~~~~~~~~

In order to create the remote backups, you will have to install `BorgBackup`_
onto another server that’s accessible via SSH. Make sure
that it accepts the Weblate's client SSH key, i.e. the one it uses to connect
to other servers.

.. hint::

    :ref:`cloudbackup` provides you automated remote backups.

.. seealso::

   :ref:`weblate-ssh-key`

Restoring from BorgBackup
-------------------------

1. Restore access to your backup repository and prepare your backup passphrase.

2. List all the backups on the server using ``borg list REPOSITORY``.

3. Restore the desired backup to the current directory using ``borg extract REPOSITORY::ARCHIVE``.

4. Restore the database from the SQL dump placed in the ``backup`` directory in the Weblate data dir (see :ref:`backup-dumps`).

5. Copy the Weblate configuration (:file:`backups/settings.py`, see :ref:`backup-dumps`) to the correct location, see :ref:`configuration`.

6. Copy the whole restored data dir to the location configured by :setting:`DATA_DIR`.

The Borg session might look like this:

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

Depending on what you want to save, back up the type of data Weblate stores in each respective place.

.. hint::

   If you are doing the manual backups, you might want to
   silence Weblate's warning about a lack of backups by adding ``weblate.I028`` to
   :setting:`django:SILENCED_SYSTEM_CHECKS` in :file:`settings.py` or
   :envvar:`WEBLATE_SILENCED_SYSTEM_CHECKS` for Docker.

   .. code-block:: python

      SILENCED_SYSTEM_CHECKS.append("weblate.I028")

Database
~~~~~~~~

The actual storage location depends on your database setup.

.. hint::

   The database is the most important storage. Set up regular backups of your
   database. Without the database, all the translations are gone.

Native database backup
++++++++++++++++++++++

The recommended approach is to save a dump of the database using database-native
tools such as :program:`pg_dump` or :program:`mysqldump`. It usually performs
better than Django backup, and it restores complete tables with all their data.

You can restore this backup in a newer Weblate release, it will perform all the
necessary migrations when running in :djadmin:`django:migrate`. Please consult
:doc:`upgrade` on more detailed info on how to upgrade between versions.

Django database backup
++++++++++++++++++++++

Alternatively, you can back up your database using Django's :djadmin:`django:dumpdata`
command. That way the backup is database agnostic and can be used in case you
want to change the database backend.

Prior to restoring the database you need to be running exactly the same Weblate
version the backup was made on. This is necessary as the database structure does
change between releases and you would end up corrupting the data in some way.
After installing the same version, run all database migrations using
:djadmin:`django:migrate`.

Afterwards some entries will already be created in the database and you
will have them in the database backup as well. The recommended approach is to
delete such entries manually using the management shell (see :ref:`invoke-manage`):

.. code-block:: console

   weblate shell
   >>> from weblate.auth.models import User
   >>> User.objects.get(username='anonymous').delete()

Files
~~~~~

If you have enough backup space, simply back up the whole :setting:`DATA_DIR`. This
is a safe bet even if it includes some files you don't want.
The following sections describe what you should back up and what you
can skip in detail.

.. _backup-dumps:

Dumped data for backups
+++++++++++++++++++++++

Stored in :setting:`DATA_DIR` ``/backups``.

Weblate dumps various data here, and you can include these files for more complete
backups. The files are updated daily (requires a running Celery beats server, see
:ref:`celery`). Currently, this includes:

* Weblate settings as :file:`settings.py` (there is also expanded version in :file:`settings-expanded.py`).
* PostgreSQL database backup as :file:`database.sql`.

The database backups are saved as plain text by default, but they can also be compressed
or entirely skipped using :setting:`DATABASE_BACKUP`.

Version control repositories
++++++++++++++++++++++++++++

Stored in :setting:`DATA_DIR` ``/vcs``.

The version control repositories contain a copy of your upstream repositories
with Weblate changes. If you have `Push on commit` enabled for all your
translation components, all Weblate changes are included upstream. No need to
back up the repositories on the Weblate side as they can be cloned
again from the upstream location(s) with no data loss.

SSH and GPG keys
++++++++++++++++

Stored in :setting:`DATA_DIR` ``/ssh`` and :setting:`DATA_DIR` ``/home``.

If you are using SSH or GPG keys generated by Weblate, you should back up these
locations. Otherwise you will lose the private keys and you will have to
regenerate new ones.

User uploaded files
+++++++++++++++++++

Stored in :setting:`DATA_DIR` ``/media``.

You should back up all user uploaded files (e.g. :ref:`screenshots`).

Celery tasks
++++++++++++

The Celery task queue might contain some info, but is usually not needed
for a backup. At most you will lose updates not yet been processed to translation
memory. It is recommended to perform the fulltext or repository update upon
restoration anyhow, so there is no problem in losing these.

.. seealso::

   :ref:`celery`

Command line for manual backup
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Using a cron job, you can set up a Bash command to be executed on a daily basis, for example:

.. code-block:: console

     $ XZ_OPT="-9" tar -Jcf ~/backup/weblate-backup-$(date -u +%Y-%m-%d_%H%M%S).xz backups vcs ssh home media fonts secret

The string between the quotes after `XZ_OPT` allows you to choose your xz options, for instance the amount of memory used for compression; see https://linux.die.net/man/1/xz

You can adjust the list of folders and files to your needs. To avoid saving the translation memory (in backups folder), you can use:

.. code-block:: console

     $ XZ_OPT="-9" tar -Jcf ~/backup/weblate-backup-$(date -u +%Y-%m-%d_%H%M%S).xz backups/database.sql backups/settings.py vcs ssh home media fonts secret

Restoring manual backup
-----------------------

1. Restore all data you have backed up.

2. Update all repositories using :djadmin:`updategit`.

   .. code-block:: sh

         weblate updategit --all

Moving a Weblate installation
------------------------------

Relocate your installation to a different system
by following the backing up and restoration instructions above.

.. seealso::

   :ref:`py3`,
   :ref:`database-migration`
