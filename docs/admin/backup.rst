Backing up and moving Weblate
=============================

Backing up
----------

Weblate stores data in several locations and you should consider how to backup
each of them properly. You might not need to backup some of the data depending
on the configuration.

Database
~~~~~~~~

Location depends on your database setup.

Database is the most important storage for Weblate. Always configure regular
backups of your database, without it all your translations setup will be gone.

Files
~~~~~

If you have enough backup space, simply backup whole :setting:`DATA_DIR`. This
is safe bet even if you will include some files which do not have to be backed
up. Following sections in detail describe what you should backup and what you
can skip.

.. _backup-dumps:

Dumped data for backups
+++++++++++++++++++++++

Stored in :setting:`DATA_DIR` ``/backups``.

Weblate dumps various data here and you can use the files here for better
backups. The files are updated daily (requires running Celery beats server, see
:ref:`celery`).  Currently this includes:

* Translation memory dump in JSON format.

Version control repositories
++++++++++++++++++++++++++++

Stored in :setting:`DATA_DIR` ``/vcs``.

The version control repositories contain copy of your upstream repositories
with Weblate changes. If you have push on commit enabled on all your
translation components, then all Weblate changes are included upstream and you
do not have to backup the repositories on Weblate side. They can be cloned
again from upstream locations with no data loss.

SSH and GPG keys
++++++++++++++++

Stored in :setting:`DATA_DIR` ``/ssh`` and :setting:`DATA_DIR` ``/home``.

If you are using Weblate generated SSH or GPG keys, you should backup these
locations, otherwise you will loose to private keys and you will have to
regenerate new ones.

User uploaded files
+++++++++++++++++++

Stored in :setting:`DATA_DIR` ``/media``.

You should backup user uploaded files (eg. :ref:`screenshots`).

Translation memory
++++++++++++++++++

Stored in :setting:`DATA_DIR` ``/memory``.

The translation memory content. It is recommended to back it up using
:djadmin:`dump_memory` in JSON format instead of using binary format as that
might eventually change (and it is incompatible between Python 2 and Python 3).
Weblate prepares this dump daily, see :ref:`backup-dumps`.

Fulltext index
++++++++++++++

Stored in :setting:`DATA_DIR` ``/whoosh``.

It is recommended to not backup this and regenerate it from scratch on restore.

Celery tasks
------------

The Celery tasks queue might contain some information, but usually it's not
needed to backup. At most your will loose not processed updates to translation
memory. The fulltext or repository updates are anyway recommeded to perform on
restore, so there is no problem in losing these.

.. seealso::

   :ref:`celery`

Restoring
---------

1. Restore all data you have backed up.

2. Recreate fulltext index using :djadmin:`rebuild_index`:

   .. code-block:: sh

      ./manage.py rebuild_index --clean --all

3. Restore your :ref:`translation-memory` using :djadmin:`import_memory`.

   .. code-block:: sh

         ./manage.py import_memory memory.json

4. Update all repositories using :djadmin:`updategit`.

   .. code-block:: sh

         ./manage.py updategit --all

Moving Weblate installation
---------------------------

Weblate installation should be relocatable, to move to different systems just
follow backup and restore instructions above.

.. seealso::

   :ref:`py3`
