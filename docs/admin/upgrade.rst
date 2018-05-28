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
    can roll back the database in case upgrade fails.

1. Upgrade configuration file, refer to :file:`settings_example.py` or
   :ref:`version-specific-instructions` for needed steps.

2. Upgrade database structure:

   .. code-block:: sh

        ./manage.py migrate --noinput

3. Collect updated static files (mostly javacript and CSS):

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

.. versionchanged:: 1.2

    Since version 1.2 the migration is done using South module, to upgrade to 1.2,
    please see :ref:`version-specific-instructions`.

.. versionchanged:: 1.9

    Since version 1.9, Weblate also supports Django 1.7 migrations, please check
    :ref:`django-17` for more information.

.. versionchanged:: 2.3

    Since version 2.3, Weblate supports only Django native migrations, South is
    no longer supported, please check :ref:`django-17` for more information.

.. versionchanged:: 2.11

    Since version 2.11, there is reduced support for migrating from
    older non-released versions. In case you hit problem in this, please
    upgrade first to the closest release version and then continue in
    upgrading to latest one.

.. versionchanged:: 2.12

    Since version 2.12, upgrade is not supported for versions prior to 2.2. In
    case you are upgrading from such old version, please upgrade to 2.2 first
    and then continue in upgrading to current release.

.. versionchanged:: 3.0

    If you are upgrading from 2.x release, always first upgrade to 3.0 (see
    :ref:`upgrade_3`) and the continue ugprading in the 3.x series. Upgrades
    skipping this step are not supported.

.. _version-specific-instructions:

Version specific instructions
-----------------------------

Upgrade from 0.5 to 0.6
~~~~~~~~~~~~~~~~~~~~~~~

On upgrade to version 0.6, you should run :samp:`./manage.py syncdb` and
:samp:`./manage.py setupgroups --move` to setup access control as described
in the installation section.

Upgrade from 0.6 to 0.7
~~~~~~~~~~~~~~~~~~~~~~~

On upgrade to version 0.7, you should run :samp:`./manage.py syncdb` to
setup new tables and :samp:`./manage.py rebuild_index` to build the index for
fulltext search.

Upgrade from 0.7 to 0.8
~~~~~~~~~~~~~~~~~~~~~~~

On upgrade to version 0.8, you should run :samp:`./manage.py syncdb` to set up
new tables, :samp:`./manage.py setupgroups` to update privileges setup and
:samp:`./manage.py rebuild_index` to rebuild index for fulltext search.

Upgrade from 0.8 to 0.9
~~~~~~~~~~~~~~~~~~~~~~~

On upgrade to version 0.9, file structure has changed. You need to move
:file:`repos` and :file:`whoosh-index` to :file:`weblate` folder. Also running
:samp:`./manage.py syncdb`, :samp:`./manage.py setupgroups` and
:samp:`./manage.py setuplang` is recommended to get latest updates of
privileges and language definitions.

Upgrade from 0.9 to 1.0
~~~~~~~~~~~~~~~~~~~~~~~

On upgrade to version 1.0, one field has been added to database, you need to
invoke the following SQL command to adjust it:

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
settings as :file:`settings_example.py`; it is recommended to use it as new base
for your setup.

Upgrade from 1.4 to 1.5
~~~~~~~~~~~~~~~~~~~~~~~

Several internal modules and paths have been renamed and changed, please adjust
your :file:`settings.py` to match (consult :file:`settings_example.py` for
correct values).

* Many modules lost their ``weblate.`` prefix.
* Checks were moved to submodules.
* Locales were moved to top level directory.

The migration of database structure to 1.5 might take quite long; it is
recommended to put your site offline while the migration is going on.

.. note::

    If you have update in same directory, stale :file:`*.pyc` files might be
    left around and cause various import errors. To recover from this, delete
    all of them in Weblate's directory, for example by
    ``find . -name '*.pyc' -delete``.

Upgrade from 1.6 to 1.7
~~~~~~~~~~~~~~~~~~~~~~~

The migration of database structure to 1.7 might take quite long, it is
recommended to put your site offline while the migration is going on.

If you are translating monolingual files, it is recommended to rerun quality
checks as they might have been wrongly linked to units in previous versions.

Upgrade from 1.7 to 1.8
~~~~~~~~~~~~~~~~~~~~~~~

The migration of database structure to 1.8 might take quite long, it is
recommended to put your site offline while the migration is going on.

Authentication setup has been changed and some internal modules have changed
name, please adjust your :file:`settings.py` to match (consult
:file:`settings_example.py` for correct values).

Also please note that there are several new requirements, see
:ref:`requirements` for more details.

Upgrade from 1.8 to 1.9
~~~~~~~~~~~~~~~~~~~~~~~

Several internal modules and paths have been renamed and changed, please adjust
your :file:`settings.py` to match (consult :file:`settings_example.py` for
correct values).

.. seealso::

    If you are upgrading to Django 1.7 at the same time, please consult
    :ref:`django-17`.

Upgrade from 1.9 to 2.0
~~~~~~~~~~~~~~~~~~~~~~~

Several internal modules and paths have been renamed and changed, please adjust
your :file:`settings.py` to match (consult :file:`settings_example.py` for
correct values).

This upgrade also requires you to upgrade python-social-auth from 0.1.x to
0.2.x series, which will most likely need to fake one of their migrations
(see :doc:`Upgrading PSA with South <psa:configuration/django>` for more information):

.. code-block:: sh

    ./manage.py migrate --fake default

.. seealso::

    If you are upgrading to Django 1.7 at the same time, please consult
    :ref:`django-17`.

Upgrade from 2.0 to 2.1
~~~~~~~~~~~~~~~~~~~~~~~

The filesystem paths configuration has changed, the :setting:`GIT_ROOT` and
:setting:`WHOOSH_INDEX` are gone and now all data resides in
:setting:`DATA_DIR`. The existing data should be automatically migrated by the
supplied migration, but in case of non standard setup, you might need to move
these manually.

.. seealso::

    If you are upgrading to Django 1.7 at the same time, please consult
    :ref:`django-17`.

Upgrade from 2.1 to 2.2
~~~~~~~~~~~~~~~~~~~~~~~

Weblate now supports fulltext search on additional fields. In order to make it
work on existing data you need to update fulltext index by:

.. code-block:: sh

    ./manage.py rebuild_index --clean --all

If you have some monolingual translations, Weblate now allows editing of template
(source) strings as well. To see them, you need to reload translations, which
will either happen automatically on te next repository update or you can force it
manually:

.. code-block:: sh

    ./manage.py loadpo --all

.. seealso::

    If you are upgrading to Django 1.7 at the same time, please consult
    :ref:`django-17`.

Upgrade from 2.2 to 2.3
~~~~~~~~~~~~~~~~~~~~~~~

If you have not yet performed upgrade to Django 1.7 and newer, first upgrade to
2.2 following the instructions above. Weblate 2.3 no longer supports migration from
Django 1.6.

If you were using Weblate 2.2 with Django 1.6, you will now need to fake some
migrations:

.. code-block:: sh

    ./manage.py migrate --fake accounts 0004_auto_20150108_1424
    ./manage.py migrate --fake lang 0001_initial
    ./manage.py migrate --fake trans 0018_auto_20150213_1447

Previous Weblate releases contained a bug which made some monolingual
translations behave inconsistently for fuzzy and untranslated strings, if you
have such, it is recommended to run:

.. code-block:: sh

    ./manage.py fixup_flags --all

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 2.3 to 2.4
~~~~~~~~~~~~~~~~~~~~~~~

Handling of static content has been rewritten, please adjust configuration of
your webserver accordingly (see :ref:`static-files` for more details). Most
importantly:

* ``/media/`` path is no longer used
* ``/static/`` path now holds both admin and Weblate static files

There is now also additional dependency - ``django_compressor``, please install
it prior to upgrading.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 2.4 to 2.5
~~~~~~~~~~~~~~~~~~~~~~~

The fulltext index has been changed, so unless you rebuild it, the fulltext
search will not work. To rebuild it, execute:

.. code-block:: sh

    ./manage.py rebuild_index --clean --all

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 2.5 to 2.6
~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

Notable configuration or dependencies changes:

* new dependecy on Django REST Framework, see :ref:`requirements`
* example configuration now configures Django REST Framework, please adjust
  your settings accordingly
* the USE_TZ settings is now enabled by default

.. note::

    Weblate now relies much more on having the correct site name in the database, please
    see :ref:`production-site` for instructions how to set it up.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 2.6 to 2.7
~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

Notable configuration or dependencies changes:

* new optional dependency on python-bidi, see :ref:`requirements`
* Google Web Translation was removed, remove it from your configuration

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 2.7 to 2.8
~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

Notable configuration or dependencies changes:

* new dependency on defusedxml, see :ref:`requirements`
* there is new quality check: :ref:`check-xml-invalid`

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 2.8 to 2.9
~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

Notable configuration or dependencies changes:

* The addition of media storage to :setting:`DATA_DIR`.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 2.9 to 2.10
~~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

Notable configuration or dependencies changes:

* The ``INSTALLED_APPS`` now should include ``weblate.utils``.
* There is new check in default set (``SamePluralsCheck``).
* There is change in ``SOCIAL_AUTH_PIPELINE`` default settings.
* You might want to enable optional :ref:`git-exporter`.
* There is new ``RemoveControlChars`` in default :setting:`AUTOFIX_LIST`.
* If you are using Microsoft Translator, please replace
  :ref:`ms-translate` with :ref:`ms-cognitive-translate`;
  Microsoft has changed authentication scheme.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 2.10 to 2.11
~~~~~~~~~~~~~~~~~~~~~~~~~

In case you have been using python-social-auth 0.2.21 with Weblate 2.10 you can
follow generic upgrade instructions, otherwise please read warning below.

Notable configuration or dependencies changes:

* There is new recommended value for ``SOCIAL_AUTH_SLUGIFY_FUNCTION``.
* There is change in ``MIDDLEWARE_CLASSES`` setting.
* The ``python-social-auth`` module has been deprecated upstream, Weblate
  now uses ``social-auth-core`` and ``social-auth-app-django`` instead. You also
  have to adjust :file:`settings.py` as several modules have been moved from
  ``social`` to either ``social_core`` or ``social_django``. Please consult
  :file:`settings_example.py` for correct values.

.. warning::

    If you were using python-social-auth 0.2.19 or older with Weblate 2.10, you
    should first upgrade Weblate 2.10 to python-social-auth 0.2.21 and then
    perform upgrade to Weblate 2.11. Otherwise you end up with non applicable
    database migrations.

    See `Migrating from python-social-auth to split social <https://github.com/omab/python-social-auth/blob/master/MIGRATING_TO_SOCIAL.md#migrations>`_
    for more information.

    If you are upgrading from older version, you should first upgrade to
    Weblate 2.10 and python-social-auth 0.2.21 and then continue in upgrading.


.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 2.11 to 2.12
~~~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

Notable configuration or dependencies changes:

* The database migration will take quite long on this update as all
  translation units stored in database have to be updated. Expect about 1 hour
  of migration for 500000 translation units (depends on hardware and database).
* There is new dependency on ``django-appconf`` and ``siphashc3``.
* The setting for ``UNAUTHENTICATED_USER`` for ``REST_FRAMEWORK`` has been
  changed to properly handle anonymous user permissions in REST API.
* The ``INSTALLED_APPS`` now should include ``weblate.screenshots``.
* There is new optional dependency on tesserocr, see :ref:`requirements`.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 2.12 to 2.13
~~~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

Notable configuration or dependencies changes:

* There is new quality check: :ref:`check-translated`.
* The ``INSTALLED_APPS`` now should include ``weblate.permissions``.
* The per project ALCs are now implemented using Group ACL, you might need to
  adjust your setup if you were using Group ACLs before.
* There are several new permissions which should be assigned to default groups,
  you should run ``./manage.py setupgroups`` to update them. Alternatively, you
  might want to add the following permissions where applicable:
  * Can access VCS repository
  * Can access project

.. note::

    If you have update in same directory, stale :file:`*.pyc` files might be
    left around and cause various import errors. To recover from this, delete
    all of them in Weblate's directory, for example by
    ``find . -name '*.pyc' -delete``.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 2.13 to 2.14
~~~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

Notable configuration or dependencies changes:

* There is new middleware ``weblate.middleware.SecurityMiddleware`` in the
  default configuration, see :ref:`csp` for more details.
* Weblate now uses Django password validation, it's controlled by
  ``AUTH_PASSWORD_VALIDATORS`` setting.
* Weblate now customizes disconnect pipeline for Python Social Auth,
  the ``SOCIAL_AUTH_DISCONNECT_PIPELINE`` setting is now needed.
* There is change in ``SOCIAL_AUTH_PIPELINE`` default settings.
* All pending email verifications will be invalid due to validation change.
* The authentication attempts are now rate limited, see :ref:`rate-limit` for
  more details.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 2.14 to 2.15
~~~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

Notable configuration or dependencies changes:

* The ``AUTHENTICATION_BACKENDS`` setting should be changed to include
  ``social_core.backends.email.EmailAuth`` as shipped by Python Social Auth.
  Weblate no longer uses own email auth backend.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 2.15 to 2.16
~~~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

Notable configuration or dependencies changes:

* There is change in ``SOCIAL_AUTH_PIPELINE`` default settings.
* The ``weblate.wladmin`` should now be first in the ``INSTALLED_APPS`` settings.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 2.16 to 2.17
~~~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

Notable configuration or dependencies changes:

* There is new validator included in default ``AUTH_PASSWORD_VALIDATORS`` setting.
* The ``siphashc3`` dependency has been replaced by ``siphashc``.
* The default value for :setting:`BASE_DIR` setting has been changed to match Django
  default value. You might have to adjust some paths in the configuration as
  several default values are based on this (eg. :setting:`DATA_DIR` or
  :setting:`TTF_PATH`).
* There is change in ``SOCIAL_AUTH_PIPELINE`` default settings.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 2.17 to 2.18
~~~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

Notable configuration or dependencies changes:

* Django 1.11 is now required.
* The `MIDDLEWARE_CLASSES` is now :setting:`django:MIDDLEWARE` with several changes.
* The :setting:`SPECIAL_CHARS` now lists actual chars now.
* There is change in default value for :setting:`django:TEMPLATES` setting.
* There are several new permissions which should be assigned to default groups,
  you should run ``./manage.py setupgroups`` to update them. Alternatively, you
  might want to add the following permissions where applicable:
  * Can review translation
* Weblate now needs database to be configured with :setting:`ATOMIC_REQUESTS <django:DATABASE-ATOMIC_REQUESTS>` enabled.

.. seealso:: :ref:`generic-upgrade-instructions`

Upgrade from 2.18 to 2.19
~~~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

Notable configuration or dependencies changes:

* There is new dependency on the ``user_agents`` module.
* There is change in the :setting:`django:MIDDLEWARE` setting (added ``weblate.wladmin.middleware.ConfigurationErrorsMiddleware``).
* There is change in the :setting:`django:INSTALLED_APPS` setting (added ``weblate.langdata`` and ``weblate.addons``).
* Several shipped hook scripts are replaced by addons. The migration will happen automatically.

There has been change in default plural rules for some languages to closer
follow CLDR specification. You might want to reimort those to avoid possible
consistency problems:

.. code-block:: sh

    ./manage.py loadpo --all --lang dsb
    ./manage.py loadpo --all --lang he
    ./manage.py loadpo --all --lang hsb
    ./manage.py loadpo --all --lang kw
    ./manage.py loadpo --all --lang lt
    ./manage.py loadpo --all --lang lv

.. seealso:: :ref:`generic-upgrade-instructions`

.. _upgrade_2_20:

Upgrade from 2.19 to 2.20
~~~~~~~~~~~~~~~~~~~~~~~~~

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

Notable configuration or dependencies changes:

* There is new dependency on the ``filelock`` module.
* The two internal machine translation services are now merged, please adjust
  :setting:`MACHINE_TRANSLATION_SERVICES` to no longer include
  ``weblate.machinery.weblatetm.WeblateSimilarTranslation``.
* There is a change in ``REST_FRAMEWORK`` setting to support ``Bearer``
  authentication.
* The translate-toolkit 2.3.0 is now required.
* There is change in the :setting:`django:INSTALLED_APPS` setting (added ``weblate.memory``).
* There is new built in translation memory machine translation, the
  :setting:`MACHINE_TRANSLATION_SERVICES` should now include
  ``weblate.memory.machine.WeblateMemory``.

.. seealso:: :ref:`generic-upgrade-instructions`

.. _upgrade_3:

Upgrade from 2.20 to 3.0
~~~~~~~~~~~~~~~~~~~~~~~~

.. warning::

    Please follow carefully following instructions. It is extremely recommended to
    backup your database prior to this upgrade.

Notable configuration or dependencies changes:

* Several modules have been renamed and this lead to changes in many settings,
  please consult :file:`settings_example.py` for current values.
* Several dependencies have raised minimal version.
* The setting :setting:`MACHINE_TRANSLATION_SERVICES` was renamed to
  :setting:`MT_SERVICES`.
* The :ref:`privileges` is completely rewritten, you might have to adjust
  privileges you have manually assigned.
* The per component scripts are no longer supported, please use addons instead,
  see :ref:`addon-script` for more details.
* Users now need to have unique emails. This was assumed before, but the check
  was not enforced in all places (eg. in the admin interface in older version).
  You will get a migration error if there are more users using same email.

Upgrading steps:

1. It is recommended to upgrade to 2.20 first, see :ref:`upgrade_2_20`.
2. Backup your database and Weblate.
3. Stop web server and any background jobs using Weblate.
4. Update the configuration file to match :file:`settings_example.py`.
5. Comment out :setting:`django:AUTH_USER_MODEL` in the configuration.
6. Run first authentication migration: ``./manage.py migrate weblate_auth 0001``
7. Bring back setting for :setting:`django:AUTH_USER_MODEL`.
8. Run rest of migrations: ``./manage.py migrate``

After upgrading:

* All existing users and groups have been migrated to new model.
* Any per user permissions are removed, please assign users to appropriate
  groups and roles to grant them permissions.
* Any custom groups will not have any permissions after upgrade, please grant
  the permissions again.

.. seealso:: :ref:`generic-upgrade-instructions`, :ref:`privileges`

.. _django-17:

Upgrading to Django 1.7
-----------------------

.. versionchanged:: 2.3

    This migration is supported only in Weblate 2.2, in case you are 
    upgrading from some older version, you will have to do intermediate update
    to 2.2.

Django 1.7 has a new feature to handle database schema upgrade called
"migrations" which is incompatible with South (used before by Weblate).

Before migrating to Django 1.7, you first need to apply all migrations from
South. If you already have upgraded Django to 1.7, you can do this using
virtualenv and :file:`examples/migrate-south` script:

.. code-block:: sh

    examples/migrate-south --settings weblate.settings

Once you have done that, you can run Django migrations and work as usual. For
the initial setup, you might need to fake some of the migrations though:

.. code-block:: sh

    ./manage.py migrate --fake-initial

Upgrading from Python 2.x to 3.x
--------------------------------

The upgrade from Python 2.x to 3.x, should work without major problems. Take
care about some changed module names when installing dependencies (eg. pydns
vs. py3dns).

The Whoosh index has to be rebuilt as it's encoding depends on Python version,
you can do that using following command:

.. code-block:: sh

    ./manage.py rebuild_index --clean --all

.. _pootle-migration:

Migrating from Pootle
---------------------

As Weblate was originally written as replacement from Pootle, it is supported
to migrate user accounts from Pootle. All you need to do is to copy
``auth_user`` table from Pootle, user profiles will be automatically created
for users as they log in and they will be asked to update their settings.
Alternatively you can use :djadmin:`importusers` to import dumped user
credentials.
