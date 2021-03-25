.. _install:

Configuration instructions
==========================

Installing Weblate
------------------

.. toctree::
    :caption: Quick setup guide
    :maxdepth: 1
    :hidden:

    install/docker
    install/venv-debian
    install/venv-suse
    install/venv-redhat
    install/venv-macos
    install/source
    install/openshift
    install/kubernetes

Choose a installation method that suits your setup and experience:

* :doc:`install/docker`, recommended for production setups.

* Virtualenv installation, recommended for production setups:

   * :doc:`install/venv-debian`
   * :doc:`install/venv-suse`
   * :doc:`install/venv-redhat`
   * :doc:`install/venv-macos`

* :doc:`install/source`, recommended for development.

* :doc:`install/openshift`
* :doc:`install/kubernetes`

.. _requirements:

Software requirements
---------------------

Operating system
++++++++++++++++

Weblate works on Linux, FreeBSD and macOS.
Other Unix-like systems most likely work too.

Weblate is not supported, but may work on Windows.
Patches are happily accepted.

Other services
++++++++++++++

Weblate uses other services for its operation.
At least the following services must be running:

* PostgreSQL database server, see :ref:`database-setup`.
* Redis server for cache and tasks queue, see :ref:`celery`.
* SMTP server for outgoing e-mail, see :ref:`out-mail`.

.. _python-deps:

Python dependencies
+++++++++++++++++++

Weblate is written in `Python <https://www.python.org/>`_ and supports Python
3.6 or newer. You can install dependencies using pip or from your
distribution packages. The full list is available in :file:`requirements.txt`.

Most notable dependencies:

Django
    https://www.djangoproject.com/
Celery
    https://docs.celeryproject.org/
Translate Toolkit
    https://toolkit.translatehouse.org/
translation-finder
    https://github.com/WeblateOrg/translation-finder
Python Social Auth
    https://python-social-auth.readthedocs.io/
Django REST Framework
    https://www.django-rest-framework.org/

.. _optional-deps:

Optional dependencies
+++++++++++++++++++++

The following optional modules are used for some Weblate features.
You can find all of them in :file:`requirements-optional.txt`.

``Mercurial`` for Mercurial repositoriy support.
    https://www.mercurial-scm.org/
``phply`` for PHP support.
    https://github.com/viraptor/phply
``tesserocr`` for OCR screenshots.
    https://github.com/sirfz/tesserocr
``akismet`` for suggestion spam protection.
    https://github.com/ubernostrum/akismet
``ruamel.yaml`` for :ref:`yaml`.
    https://pypi.org/project/ruamel.yaml/
``Zeep`` for :ref:`ms-terminology`.
    https://docs.python-zeep.org/
``aeidon`` for :ref:`subtitles`.
    https://pypi.org/project/aeidon/

Database back-end dependencies
++++++++++++++++++++++++++++++

Weblate supports PostgreSQL, MariaDB, and MySQL. Read the :ref:`database-setup` and
back-end documentation for more details.

Other system requirements
+++++++++++++++++++++++++

The following dependencies must be installed on the system:

``Git``
    https://git-scm.com/
Pango, Cairo and related header files and GIR introspection data
    https://cairographics.org/, https://pango.gnome.org/, see :ref:`pangocairo`

The following dependencies are optional:

``git-review`` for Gerrit support.
    https://pypi.org/project/git-review/
``git-svn`` for Subversion support.
    https://git-scm.com/docs/git-svn
``tesseract`` and its data for OCR screenshots.
    https://github.com/tesseract-ocr/tesseract
``licensee`` for detecting license when creating components.
    https://github.com/licensee/licensee

Build-time dependencies
+++++++++++++++++++++++

To build some of the :ref:`python-deps` you might need to install their
dependencies. This depends on how you install them, so please read
the documentation for individual packages.
You won't need those if using the prebuilt ``Wheels`` while installing using
``pip``, or when you use distribution packages.

.. _pangocairo:

Pango and Cairo
+++++++++++++++

.. versionchanged:: 3.7

Weblate uses Pango and Cairo to render bitmap widgets (see
:ref:`promotion`) and checks (see :ref:`fonts`).
To properly install Python bindings for those you need to install its system
libraries first. You need both Cairo and Pango, which in turn need GLib.
All those should be installed with corresponding development files
and GObject introspection data.

.. _verify:

Verifying release signatures
----------------------------

Weblate releases are cryptographically signed by the release developer.
Currently this is Michal Čihař. The fingerprint of his PGP key is:

.. code-block:: console

    63CB 1DF1 EF12 CF2A C0EE 5A32 9C27 B313 42B7 511D

and you can get more identification info from <https://keybase.io/nijel>.

Verify that the signature matches the archive you have downloaded.
This way you are sure you are using the same code that was released.
You should also verify the date of the signature to make sure that you
downloaded the latest version.

Each archive is accompanied with an ``.asc`` files (containing the PGP signature
for it). Once you have both of them in the same folder, you can verify the signature:

.. code-block:: console

   $ gpg --verify Weblate-3.5.tar.xz.asc
   gpg: assuming signed data in 'Weblate-3.5.tar.xz'
   gpg: Signature made Ne 3. března 2019, 16:43:15 CET
   gpg:                using RSA key 87E673AF83F6C3A0C344C8C3F4AA229D4D58C245
   gpg: Can't check signature: public key not found

As you can tell, GPG complains that it does not know the public key.
At this point you should perform one of the following steps:

* Use `wkd` to download the key:

.. code-block:: console

   $ gpg --auto-key-locate wkd --locate-keys michal@cihar.com
   pub   rsa4096 2009-06-17 [SC]
         63CB1DF1EF12CF2AC0EE5A329C27B31342B7511D
   uid           [ultimate] Michal Čihař <michal@cihar.com>
   uid           [ultimate] Michal Čihař <nijel@debian.org>
   uid           [ultimate] [JPEG image of size 8848]
   uid           [ultimate] Michal Čihař (Braiins) <michal.cihar@braiins.cz>
   sub   rsa4096 2009-06-17 [E]
   sub   rsa4096 2015-09-09 [S]


* Download the keyring from `Michal's server <https://cihar.com/.well-known/openpgpkey/hu/wmxth3chu9jfxdxywj1skpmhsj311mzm>`_, then import it with:

.. code-block:: console

   $ gpg --import wmxth3chu9jfxdxywj1skpmhsj311mzm

* Download and import the key from one of the key servers:

.. code-block:: console

   $ gpg --keyserver hkp://pgp.mit.edu --recv-keys 87E673AF83F6C3A0C344C8C3F4AA229D4D58C245
   gpg: key 9C27B31342B7511D: "Michal Čihař <michal@cihar.com>" imported
   gpg: Total number processed: 1
   gpg:              unchanged: 1

This will improve the situation a bit.
At this point you can verify that the signature from the given key is correct,
but you can still not trust the name used in the key:

.. code-block:: console

   $ gpg --verify Weblate-3.5.tar.xz.asc
   gpg: assuming signed data in 'Weblate-3.5.tar.xz'
   gpg: Signature made Ne 3. března 2019, 16:43:15 CET
   gpg:                using RSA key 87E673AF83F6C3A0C344C8C3F4AA229D4D58C245
   gpg: Good signature from "Michal Čihař <michal@cihar.com>" [ultimate]
   gpg:                 aka "Michal Čihař <nijel@debian.org>" [ultimate]
   gpg:                 aka "[JPEG image of size 8848]" [ultimate]
   gpg:                 aka "Michal Čihař (Braiins) <michal.cihar@braiins.cz>" [ultimate]
   gpg: WARNING: This key is not certified with a trusted signature!
   gpg:          There is no indication that the signature belongs to the owner.
   Primary key fingerprint: 63CB 1DF1 EF12 CF2A C0EE  5A32 9C27 B313 42B7 511D

The problem here is that anybody could issue the key with this name.
You need to ensure the key is actually owned by the mentioned person.
The GNU Privacy Handbook covers this topic in the chapter
`Validating other keys on your public keyring`_.
The most reliable method is to meet the developer in person and exchange key
fingerprints, however you can also rely on the web of trust.
This way you can trust the key transitively though signatures of others,
who have met the developer in person.

Once the key is trusted, the warning will not occur:

.. code-block:: console

   $ gpg --verify Weblate-3.5.tar.xz.asc
   gpg: assuming signed data in 'Weblate-3.5.tar.xz'
   gpg: Signature made Sun Mar  3 16:43:15 2019 CET
   gpg:                using RSA key 87E673AF83F6C3A0C344C8C3F4AA229D4D58C245
   gpg: Good signature from "Michal Čihař <michal@cihar.com>" [ultimate]
   gpg:                 aka "Michal Čihař <nijel@debian.org>" [ultimate]
   gpg:                 aka "[JPEG image of size 8848]" [ultimate]
   gpg:                 aka "Michal Čihař (Braiins) <michal.cihar@braiins.cz>" [ultimate]


Should the signature be invalid (meaning archive has been changed),
you will get a clear error regardless of the fact that the key is trusted or not:

.. code-block:: console

   $ gpg --verify Weblate-3.5.tar.xz.asc
   gpg: Signature made Sun Mar  3 16:43:15 2019 CET
   gpg:                using RSA key 87E673AF83F6C3A0C344C8C3F4AA229D4D58C245
   gpg: BAD signature from "Michal Čihař <michal@cihar.com>" [ultimate]


.. _Validating other keys on your public keyring: https://www.gnupg.org/gph/en/manual.html#AEN335

.. _file-permissions:

Filesystem permissions
----------------------

The Weblate process needs access to read and write to the directory where
it keeps data — :setting:`DATA_DIR`. All files within this directory should be
owned and writable by the user running all Weblate processes
(typically WSGI and Celery, see :ref:`server` and :ref:`celery`).

The default configuration places them in the same tree as the Weblate sources,
however you might prefer to move these to a better location such as:
:file:`/var/lib/weblate`.

Weblate tries to create these directories automatically, but it will fail
when it does not have permissions to do so.

You should also take care when running :ref:`manage`, as they should be ran
by the same user that started Weblate itself. Otherwise the permissions for
some files might be wrong.

In the Docker container, all files in the :file:`/app/data` volume have to be
owned by the weblate user inside the container (UID 1000).

.. seealso::

   :ref:`static-files`

.. _database-setup:

Database setup for Weblate
--------------------------

It is recommended to run Weblate with a PostgreSQL database-server.

.. seealso::

   :ref:`production-database`,
   :doc:`django:ref/databases`,
   :ref:`database-migration`

.. _postgresql:

PostgreSQL
++++++++++

PostgreSQL is usually the best choice for Django-based sites. It's the reference
database used for implementing Django database layer.

.. note::

   Weblate uses the trigram extension which has to be installed separately in some
   cases. Try to find ``postgresql-contrib`` or a similarly named package.

.. seealso::

    :ref:`django:postgresql-notes`

.. _dbsetup-postgres:

Creating a database in PostgreSQL
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

It is usually a good idea to run Weblate in a separate database, and separate user account:

.. code-block:: sh

    # If PostgreSQL was not installed before, set the main password
    sudo -u postgres psql postgres -c "\password postgres"

    # Create a database user called "weblate"
    sudo -u postgres createuser --superuser --pwprompt weblate

    # Create the database "weblate" owned by "weblate"
    sudo -u postgres createdb -O weblate weblate

.. hint::

   If you don't want to make the Weblate user a superuser in PostgreSQL, you can
   omit that and perform some of the migration steps manually.
   This is an example of a PostgreSQL superuser in the scheme Weblate uses:

   .. code-block:: postgres

        CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA weblate;

.. _config-postgresql:

Configuring Weblate to use PostgreSQL
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The :file:`settings.py` snippet for PostgreSQL:

.. code-block:: python

    DATABASES = {
        "default": {
            # Database engine
            "ENGINE": "django.db.backends.postgresql",
            # Database name
            "NAME": "weblate",
            # Database user
            "USER": "weblate",
            # Name of role to alter to set parameters in PostgreSQL,
            # use in case role name is different than user used for authentication.
            # "ALTER_ROLE": "weblate",
            # Database password
            "PASSWORD": "password",
            # Set to empty string for localhost
            "HOST": "database.example.com",
            # Set to empty string for default
            "PORT": "",
        }
    }

Database migrations performs `ALTER ROLE
<https://www.postgresql.org/docs/12/sql-alterrole.html>`_ on the database role
used by Weblate. In most cases the name of the role matches the username.
In more complex setups the role name is different from username and you will
get an error about a non-existing role during database migration
(``psycopg2.errors.UndefinedObject: role "weblate@hostname" does not exist``).

This is known to happen with Azure Database for PostgreSQL, but it is not
limited to this environment. Please set ``ALTER_ROLE`` to change the name of the
role Weblate should alter during database migration.

.. _mysql:

MySQL and MariaDB
+++++++++++++++++

.. hint::

    Some Weblate features will perform better with :ref:`postgresql`.
    This includes searching and translation memory, which both utilize full-text
    features in the database and PostgreSQL implementation is superior.

Weblate can also be used with MariaDB (10.2.7 or later) or MySQL (5.7.8 or later),
please read :ref:`django:mysql-notes` and :ref:`django:mariadb-notes` for caveats using
Django with those. Because of these limitations it is recommended to use
:ref:`postgresql` for new installations.

Following configuration is recommended for Weblate:

* Use the ``utf8mb4`` charset to allow representation of higher Unicode planes (for example emojis).
* Configure the server with ``innodb_large_prefix`` to allow longer indices on text fields.
* Set the isolation level to ``READ COMMITTED``.
* The SQL mode should be set to ``STRICT_TRANS_TABLES``.

MySQL 8.x, MariaDB 10.5.x or newer have reasonable default configuration so
that no server tweaking should be necessary, and all that is needed can be
configured on the client side.

Below is an example :file:`/etc/my.cnf.d/server.cnf` for a server with 8 GB of
RAM. These settings should be sufficient for most installs.
MySQL and MariaDB have tunables to increase server performance that are
considered not necessary unless you are planning on having large numbers of
concurrent users accessing the system. See the various vendors documentation for
details about this.

To reduce issues it is absolutely critical that the
``innodb_file_per_table`` setting is configured correctly and that
MySQL/MariaDB is restarted before Weblate is installed.

.. code-block:: ini

   [mysqld]
   character-set-server = utf8mb4
   character-set-client = utf8mb4
   collation-server = utf8mb4_unicode_ci

   datadir=/var/lib/mysql

   log-error=/var/log/mariadb/mariadb.log

   innodb_large_prefix=1
   innodb_file_format=Barracuda
   innodb_file_per_table=1
   innodb_buffer_pool_size=2G
   sql_mode=STRICT_TRANS_TABLES

.. hint::

   In case you are getting the ``#1071 — Specified key was too long; max key length
   is 767 bytes`` error, please update your configuration to include the ``InnoDB``
   settings above and restart your install.

.. hint::

   In case you are getting the ``#2006 - MySQL server has gone away`` error,
   configuring :setting:`django:CONN_MAX_AGE` might help.

Configuring Weblate to use MySQL/MariaDB
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The :file:`settings.py` snippet for MySQL and MariaDB:

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
            "HOST": "127.0.0.1",
            # Set to empty string for default
            "PORT": "3306",
            # In case you wish to use additional
            # connection options
            "OPTIONS": {},
        }
    }

You should also create the ``weblate`` user account in MySQL or MariaDB before
you begin the install:

.. code-block:: sh

   GRANT ALL ON weblate.* to 'weblate'@'localhost' IDENTIFIED BY 'password';
   FLUSH PRIVILEGES;

Other configurations
--------------------

.. _out-mail:

Configuring outgoing e-mail
+++++++++++++++++++++++++++

Weblate needs access to an SMTP server to send out e-mails on
various occasions, for example for account activation and
various notifications configured by users.

The mail server setup is configured using these settings:
:setting:`django:EMAIL_HOST`, :setting:`django:EMAIL_HOST_PASSWORD`,
:setting:`django:EMAIL_USE_TLS`, :setting:`django:EMAIL_USE_SSL`,
:setting:`django:EMAIL_HOST_USER` and :setting:`django:EMAIL_PORT`.
Their names are quite self-explanatory, but you can find more info in the
Django documentation.

.. hint::

    In case you get error about unsupported authentication (for example
    ``SMTP AUTH extension not supported by server``), it is most likely caused
    by using an insecure connection and server refuses to authenticate this way.
    Try enabling :setting:`django:EMAIL_USE_TLS` if this is the case.

.. seealso::

   :ref:`debug-mails`,
   :ref:`Configuring outgoing e-mail in Docker container <docker-mail>`

.. _reverse-proxy:

Running behind reverse proxy
++++++++++++++++++++++++++++

Several features in Weblate rely on being able to get the IP address of the client.
This includes :ref:`rate-limit`, :ref:`spam-protection`, and :ref:`audit-log`.

In default configuration Weblate parses IP address from ``REMOTE_ADDR`` which
is set by the WSGI handler.

In case you are running a reverse proxy, this field most likely contain
its address. You need to configure Weblate to trust additional HTTP headers and
parse the IP address from these.
This can not be enabled by default as it would allow IP address spoofing for
installations not using a reverse proxy.
Enabling :setting:`IP_BEHIND_REVERSE_PROXY` might be enough for most setups,
but you might need to adjust :setting:`IP_PROXY_HEADER` and
:setting:`IP_PROXY_OFFSET` too.

.. seealso::

    :ref:`spam-protection`,
    :ref:`rate-limit`,
    :ref:`audit-log`,
    :setting:`IP_BEHIND_REVERSE_PROXY`,
    :setting:`IP_PROXY_HEADER`,
    :setting:`IP_PROXY_OFFSET`,
    :setting:`django:SECURE_PROXY_SSL_HEADER`

HTTP proxy
++++++++++

Weblate executes VCS commands that accept proxy configuration from
their environment. The recommended approach is to define proxy settings in
:file:`settings.py`:

.. code-block:: python

   import os

   os.environ["http_proxy"] = "http://proxy.example.com:8080"
   os.environ["HTTPS_PROXY"] = "http://proxy.example.com:8080"

.. seealso::

   `Proxy Environment Variables <https://ec.haxx.se/usingcurl/usingcurl-proxies#proxy-environment-variables>`_

.. _configuration:

Adjusting configuration
-----------------------

.. seealso::

   :ref:`sample-configuration`

Copy :file:`weblate/settings_example.py` to :file:`weblate/settings.py` and
adjust it to match your setup. You will probably want to adjust the following
options:

.. setting:: ADMINS

``ADMINS``

    List of site administrators to receive notifications when something goes
    wrong, for example notifications of failed merges, or Django errors.

    .. seealso::

        :setting:`django:ADMINS`

.. setting:: ALLOWED_HOSTS

``ALLOWED_HOSTS``

    You need to set this to list the hosts your site is supposed to serve.
    For example:

    .. code-block:: python

        ALLOWED_HOSTS = ["demo.weblate.org"]

    Alternatively you can include a wildcard:

    .. code-block:: python

        ALLOWED_HOSTS = ["*"]

    .. seealso::

        :setting:`django:ALLOWED_HOSTS`,
        :envvar:`WEBLATE_ALLOWED_HOSTS`,
        :ref:`production-hosts`

.. setting:: SESSION_ENGINE

``SESSION_ENGINE``

    Configure how your sessions are stored. In case you keep the default
    engine for your database back-end, you should schedule:
    :command:`weblate clearsessions` to remove stale session data from the
    database.

    If you are using Redis as cache (see :ref:`production-cache`) it is
    recommended to use it for sessions too:

    .. code-block:: python

         SESSION_ENGINE = "django.contrib.sessions.backends.cache"

    .. seealso::

        :ref:`django:configuring-sessions`,
        :setting:`django:SESSION_ENGINE`

.. setting:: DATABASES

``DATABASES``

    Connectivity to database server, please read Django's documentation for more
    details.

    .. seealso::

        :ref:`database-setup`,
        :setting:`django:DATABASES`,
        :doc:`django:ref/databases`

.. setting:: DEBUG

``DEBUG``

    In debug mode Django shows backtraces of errors to users.
    This should be turned off production use so that errors are only
    sent per e-mail to ``ADMINS`` (see above).

    Debug mode also slows down Weblate, as Django stores much more info
    internally in this case.

    .. seealso::

        :setting:`django:DEBUG`

.. setting:: DEFAULT_FROM_EMAIL

``DEFAULT_FROM_EMAIL``

    E-mail sender address for outgoing e-mail, for example registration e-mails.

    .. seealso::

        :setting:`django:DEFAULT_FROM_EMAIL`

.. setting:: SECRET_KEY

``SECRET_KEY``

    Key used by Django to sign some info in cookies, read
    :ref:`production-secret` for more info.

    .. seealso::

        :setting:`django:SECRET_KEY`

.. setting:: SERVER_EMAIL

``SERVER_EMAIL``

    E-mail used as sender address for sending e-mails to the administrator, for
    example notifications after failed merges.

    .. seealso::

        :setting:`django:SERVER_EMAIL`

.. _tables-setup:

Filling up the database
-----------------------

After your configuration is ready, you can run
:samp:`weblate migrate` to create the database structure.
Now you should be able to create translation projects using the
admin interface.

In case you want to run an installation non-interactively, you can use
:samp:`weblate migrate --noinput`, and then create an admin user using
the :djadmin:`createadmin` command.

.. hint::

    Once done, check the :guilabel:`Performance report` in the
    admin interface for info on things you can optimize on your site.

.. seealso::

   :ref:`config`,
   :ref:`privileges`

.. _production:

Production setup
----------------

For a production setup you should make the adjustments described in the following sections.
The most critical settings trigger a warning (indicated by an
exclamation mark in the top bar if signed in as a superuser):

.. image:: /images/admin-wrench.png

It is also recommended to inspect checks triggered by Django (though you might not
need to fix all of them):

.. code-block:: sh

    weblate check --deploy

You can also review the very same checklist from the :ref:`management-interface`.

.. seealso::

    :doc:`django:howto/deployment/checklist`

.. _production-debug:

Disable debug mode
++++++++++++++++++

Disable Django's debug mode (:setting:`DEBUG`) by:

.. code-block:: python

    DEBUG = False

With debug mode on, Django stores all executed queries and shows users backtraces
of errors, which is not desired in a production setup.

.. seealso::

   :ref:`configuration`

.. _production-admins:

Properly configure admins
+++++++++++++++++++++++++

Put the correct admin addresses in the :setting:`ADMINS` setting to defining who
receives e-mails in case something goes wrong on the server, for example:

.. code-block:: python

    ADMINS = (("Your Name", "your_email@example.com"),)

.. seealso::

   :ref:`configuration`

.. _production-site:

Set correct site domain
+++++++++++++++++++++++

Adjust site name and domain in the admin interface, otherwise links in RSS or
registration e-mails will not work.
This is configured using :setting:`SITE_DOMAIN` which should contain a domain name
for the site.

.. versionchanged:: 4.2

   Prior to the 4.2 release, the Django "sites" framework was used instead, please
   see :doc:`django:ref/contrib/sites`.

.. seealso::

   :ref:`production-hosts`,
   :ref:`production-ssl`
   :setting:`SITE_DOMAIN`,
   :envvar:`WEBLATE_SITE_DOMAIN`,
   :setting:`ENABLE_HTTPS`

.. _production-ssl:

Correctly configure HTTPS
+++++++++++++++++++++++++

It is strongly recommended to run Weblate using the encrypted HTTPS protocol.
After enabling it, you should set :setting:`ENABLE_HTTPS` in the settings:

.. code-block:: python

   ENABLE_HTTPS = True

.. hint::

    You might want to set up HTTP Strict Transport Security as well, see
    :ref:`django:security-recommendation-ssl` for more details.

.. seealso::

   :setting:`ENABLE_HTTPS`,
   :ref:`production-hosts`,
   :ref:`production-site`


Set properly SECURE_HSTS_SECONDS
++++++++++++++++++++++++++++++++

If your site is served over SSL, consider setting a value for :setting:`django:SECURE_HSTS_SECONDS`
in the :file:`settings.py` to enable HTTP Strict Transport Security.
By default it is set to 0 (as shown below).

.. code-block:: python

   SECURE_HSTS_SECONDS = 0

If set to a non-zero integer value, the :class:`django:django.middleware.security.SecurityMiddleware`
applies the :ref:`django:http-strict-transport-security` header to all responses without it.

.. warning::

    Setting this incorrectly can irreversibly (for some time) break your site.
    Read the :ref:`django:http-strict-transport-security` documentation first.


.. _production-database:

Use a powerful database engine
++++++++++++++++++++++++++++++

Please use PostgreSQL for production environments. Read :ref:`database-setup`
for more info.

.. seealso::

    :ref:`database-setup`,
    :ref:`database-migration`,
    :ref:`configuration`,
    :doc:`django:ref/databases`

.. _production-cache:

Enable caching
++++++++++++++

If possible, use Redis from Django by adjusting the ``CACHES`` configuration
variable, for example:

.. code-block:: python

    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": "redis://127.0.0.1:6379/0",
            # If redis is running on same host as Weblate, you might
            # want to use unix sockets instead:
            # 'LOCATION': 'unix:///var/run/redis/redis.sock?db=0',
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "PARSER_CLASS": "redis.connection.HiredisParser",
            },
        }
    }

.. hint::

   In case you change Redis settings for the cache, you might need to adjust
   them for Celery as well, see :ref:`celery`.

.. seealso::

    :ref:`production-cache-avatar`,
    :doc:`django:topics/cache`

.. _production-cache-avatar:

Avatar caching
++++++++++++++

In addition to caching of Django, Weblate performs avatar caching.
It is recommended to use a separate, file-backed cache for this purpose:

.. code-block:: python

    CACHES = {
        "default": {
            # Default caching backend setup, see above
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": "unix:///var/run/redis/redis.sock?db=0",
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "PARSER_CLASS": "redis.connection.HiredisParser",
            },
        },
        "avatar": {
            "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
            "LOCATION": os.path.join(DATA_DIR, "avatar-cache"),
            "TIMEOUT": 604800,
            "OPTIONS": {
                "MAX_ENTRIES": 1000,
            },
        },
    }

.. seealso::

    :setting:`ENABLE_AVATARS`,
    :setting:`AVATAR_URL_PREFIX`,
    :ref:`avatars`,
    :ref:`production-cache`,
    :doc:`django:topics/cache`

.. _production-email:

Configure e-mail sending
++++++++++++++++++++++++

Weblate needs to send out e-mails on several occasions, and these e-mails should
have a correct sender address, please configure :setting:`SERVER_EMAIL` and
:setting:`DEFAULT_FROM_EMAIL` to match your environment, for example:

.. code-block:: python

    SERVER_EMAIL = "admin@example.org"
    DEFAULT_FROM_EMAIL = "weblate@example.org"


.. note::

   To turn off Weblate sending e-mails, set :setting:`django:EMAIL_BACKEND`
   to ``django.core.mail.backends.dummy.EmailBackend``.

   This will prevent *all* e-mail delivery, including registration- or
   password-reset e-mails.

.. seealso::

    :ref:`configuration`,
    :ref:`out-mail`,
    :std:setting:`django:EMAIL_BACKEND`,
    :std:setting:`django:DEFAULT_FROM_EMAIL`,
    :std:setting:`django:SERVER_EMAIL`


.. _production-hosts:

Allowed hosts setup
+++++++++++++++++++

Django requires :setting:`ALLOWED_HOSTS` to hold a list of domain names
your site is allowed to serve. Leaving it empty will block any requests.

In case this is not configured to match your HTTP server, you will get errors
like :samp:`Invalid HTTP_HOST header: '1.1.1.1'. You may need to add '1.1.1.1'
to ALLOWED_HOSTS.`

.. hint::

   On Docker container, this is available as :envvar:`WEBLATE_ALLOWED_HOSTS`.

.. seealso::

    :setting:`ALLOWED_HOSTS`,
    :envvar:`WEBLATE_ALLOWED_HOSTS`,
    :ref:`production-site`

.. _production-secret:

Django secret key
+++++++++++++++++

The :setting:`SECRET_KEY` setting is used by Django to sign cookies, and you should
really generate your own value rather than using the one from the example setup.

You can generate a new key using :file:`weblate/examples/generate-secret-key` shipped
with Weblate.

.. seealso::

    :setting:`SECRET_KEY`

.. _production-home:

Home directory
++++++++++++++

.. versionchanged:: 2.1
   This is no longer required, Weblate now stores all its data in
   :setting:`DATA_DIR`.

The home directory for the user running Weblate should exist and be
writable by this user. This is especially needed if you want to use SSH to
access private repositories, but Git might need to access this directory as
well (depending on the Git version you use).

You can change the directory used by Weblate in :file:`settings.py`, for
example by setting it to the ``configuration`` folder of where you installed Weblate:

.. code-block:: python

    os.environ["HOME"] = os.path.join(BASE_DIR, "configuration")

.. note::

    On Linux, and other Unix-like systems, the path to user's home directories is
    defined in :file:`/etc/passwd`. Many distributions default to a non-writable
    directory for users used for serving web content (such as ``apache``,
    ``www-data`` or ``wwwrun``), so you either have to run Weblate from
    a different user, or change this setting.

.. seealso::

   :ref:`vcs-repos`

.. _production-templates:

Template loading
++++++++++++++++

It is recommended to use a cached template loader for Django.
It caches parsed templates, avoiding the need parse every single request.
You can configure it using the following snippet
(the ``loaders`` setting is important here):

.. code-block:: python

    TEMPLATES = [
        {
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "DIRS": [
                os.path.join(BASE_DIR, "templates"),
            ],
            "OPTIONS": {
                "context_processors": [
                    "django.contrib.auth.context_processors.auth",
                    "django.template.context_processors.debug",
                    "django.template.context_processors.i18n",
                    "django.template.context_processors.request",
                    "django.template.context_processors.csrf",
                    "django.contrib.messages.context_processors.messages",
                    "weblate.trans.context_processors.weblate_context",
                ],
                "loaders": [
                    (
                        "django.template.loaders.cached.Loader",
                        [
                            "django.template.loaders.filesystem.Loader",
                            "django.template.loaders.app_directories.Loader",
                        ],
                    ),
                ],
            },
        },
    ]

.. seealso::

    :py:class:`django:django.template.loaders.cached.Loader`

.. _production-cron:

Running maintenance tasks
+++++++++++++++++++++++++

For optimal performance, it is good idea to run some maintenance tasks in the
background.
This is now automatically done by :ref:`celery` and covers the following tasks:

* Configuration health check (hourly).
* Committing pending changes (hourly), see :ref:`lazy-commit` and :djadmin:`commit_pending`.
* Updating component alerts (daily).
* Update remote branches (nightly), see :setting:`AUTO_UPDATE`.
* Translation-memory backup to JSON (daily), see :djadmin:`dump_memory`.
* Fulltext- and database-maintenance tasks (daily and weekly tasks), see :djadmin:`cleanuptrans`.

.. versionchanged:: 3.2

   Since version 3.2, the default way of executing these tasks is by using Celery,
   and Weblate already comes with proper configuration for it, see :ref:`celery`.

.. _production-encoding:

System locales and encoding
+++++++++++++++++++++++++++

If for some reason the system locales for your distribution are not
configured to UTF-8 capable ones, you can do so by
editing :file:`/etc/default/locale` and setting ``LANG="C.UTF-8"`` there.

In some cases services have their own configuration for locales.
For example when using Apache you might want to set it in :file:`/etc/apache2/envvars`:

.. code-block:: sh

    export LANG='en_US.UTF-8'
    export LC_ALL='en_US.UTF-8'

.. _production-certs:

Using custom certificate authority
++++++++++++++++++++++++++++++++++

Weblate verifies SSL certificates during HTTPS requests.
In case you are using a custom certificate authority not trusted in default
bundles, you will have to add its certificate as trusted.

The preferred approach is to do this at a system level, please check the
documentation for your distribution for details on how to do this'
(on Debian this can be done by placing the CA certificate into
:file:`/usr/local/share/ca-certificates/` and running :command:`update-ca-certificates`).

Once this is done, system tools will trust the certificate and this includes
Git.

For Python code, you will need to configure requests to use the system CA bundle
instead of the one shipped with Python. This can be achieved by placing the following
snippet to :file:`settings.py` (the path is Debian specific):

.. code-block:: python

    import os

    os.environ["REQUESTS_CA_BUNDLE"] = "/etc/ssl/certs/ca-certificates.crt"


.. _production-compress:

Compressing client assets
+++++++++++++++++++++++++

Weblate comes with many JavaScript and CSS files.
Compressing them before sending them to a client yields better performance.
In the default configuration this is done on the fly at the cost of a little overhead.
On big installations, it is recommended to enable offline compression mode.
This needs to be done in the configuration and the compression has to be triggered on
every Weblate upgrade.

The configuration switching is done by enabling
:attr:`compressor:django.conf.settings.COMPRESS_OFFLINE` and configuring
:attr:`compressor:django.conf.settings.COMPRESS_OFFLINE_CONTEXT` (the latter is
already included in the example configuration):

.. code-block:: python

    COMPRESS_OFFLINE = True

On each deploy you need to compress the files to match the current version:

.. code-block:: sh

    weblate compress

.. hint::

   The official Docker image has this feature already enabled.

.. seealso::

   :ref:`compressor:scenarios`,
   :ref:`static-files`

.. _server:

Running server
--------------

.. hint::

   In case you are not experienced with the services described below,
   you might want to try :doc:`install/docker`.

Several services are needed to run Weblate, the recommended setup consists of:

* Database server (see :ref:`database-setup`)
* Cache server (see :ref:`production-cache`)
* Front-end web-server for static files and SSL termination (see :ref:`static-files`)
* WSGI server for dynamic content (see :ref:`uwsgi`)
* Celery for executing background tasks (see :ref:`celery`)

.. note::

   Some dependencies are shared between the services. The cache and
   database should for example be running when starting up Celery or
   uWSGI processes.

Unless you need to split them up to distribute load, you will run all
services on single (virtual) server.
The only limitation to this is Celery and WSGI servers needing access to
:setting:`DATA_DIR`.

.. note::

   The WSGI process has to be executed by the same user as the Celery
   process, otherwise files in the :setting:`DATA_DIR` are stored with
   mixed ownership, leading to runtime issues.

   See also :ref:`file-permissions` and :ref:`celery`.

Running web server
++++++++++++++++++

Running Weblate is not different from running any other Django-based
program. Django is usually executed as uWSGI or FastCGI (examples for
different web servers can be found below).

For testing purposes, you can use the built-in web server in Django:

.. code-block:: sh

    weblate runserver

.. warning::

    DO NOT USE THIS SERVER IN A PRODUCTION SETTING. It has not gone through
    security audits or performance tests.
    Also read about :djadmin:`django:runserver` in the Django documentation.

.. hint::

   The built-in Django server only serves static files with :setting:`DEBUG`
   enabled, as it is only intended for development. For production use, please
   read about WSGI setups in :ref:`uwsgi`, :ref:`apache`, :ref:`apache-gunicorn`, and
   :ref:`static-files`.

.. _static-files:

Serving static files
++++++++++++++++++++

.. versionchanged:: 2.4

    Prior to version 2.4, Weblate didn't properly use the Django static files
    framework and setup was more complex.

Django needs to collect its static files in a single directory. To do so,
execute :samp:`weblate collectstatic --noinput`. This will copy the static
files into a directory specified by the :setting:`django:STATIC_ROOT` setting (this defaults to
a ``static`` directory inside :setting:`DATA_DIR`).

It is recommended to serve static files directly from your web server, you should
use that for the following paths:

:file:`/static/`
    Serves static files for Weblate and the admin interface
    (from defined by ``STATIC_ROOT``).
:file:`/media/`
    Used for user media uploads (e.g. screenshots).
:file:`/favicon.ico`
    Should be rewritten to rewrite a rule to serve :file:`/static/favicon.ico`.

.. seealso::

   :ref:`uwsgi`,
   :ref:`apache`,
   :ref:`apache-gunicorn`,
   :ref:`production-compress`,
   :doc:`django:howto/deployment/index`,
   :doc:`django:howto/static-files/deployment`

.. _csp:

Content security policy
+++++++++++++++++++++++

The default Weblate configuration enables ``weblate.middleware.SecurityMiddleware``
middleware, which sets security related HTTP headers like ``Content-Security-Policy``
or ``X-XSS-Protection``. By default these are set up to work with Weblate and its
configuration, but this might need customization for your environment.

.. seealso::

    :setting:`CSP_SCRIPT_SRC`,
    :setting:`CSP_IMG_SRC`,
    :setting:`CSP_CONNECT_SRC`,
    :setting:`CSP_STYLE_SRC`,
    :setting:`CSP_FONT_SRC`

.. _uwsgi:

Sample configuration for NGINX and uWSGI
++++++++++++++++++++++++++++++++++++++++


To run a production web-server, use the WSGI wrapper installed with Weblate (if
running in virtualenv it is installed as
:file:`~/weblate-env/lib/python3.7/site-packages/weblate/wsgi.py`).
Don't forget to set the Python search path to your virtualenv as well (for example
using ``virtualenv = /home/user/weblate-env`` in uWSGI).

The following configuration runs Weblate as uWSGI under the NGINX web-server.

Configuration for NGINX (also available as :file:`weblate/examples/weblate.nginx.conf`):

.. literalinclude:: ../../weblate/examples/weblate.nginx.conf
    :language: nginx

Configuration for uWSGI (also available as :file:`weblate/examples/weblate.uwsgi.ini`):

.. literalinclude:: ../../weblate/examples/weblate.uwsgi.ini
    :language: ini

.. seealso::

    :doc:`django:howto/deployment/wsgi/uwsgi`

.. _apache:

Sample configuration for Apache
+++++++++++++++++++++++++++++++

It is recommended to use MPM prefork when using WSGI with Weblate.

The following configuration runs Weblate as WSGI, you need to have enabled
``mod_wsgi`` (available as :file:`weblate/examples/apache.conf`):

.. literalinclude:: ../../weblate/examples/apache.conf
    :language: apache

.. note::

    Weblate requires Python 3, so please ensure you are running the Python 3
    variant of mod_wsgi. Usually it is available as a separate package, for
    example ``libapache2-mod-wsgi-py3``.

.. seealso::

    :ref:`production-encoding`,
    :doc:`django:howto/deployment/wsgi/modwsgi`

.. _apache-gunicorn:

Sample configuration for Apache and Gunicorn
++++++++++++++++++++++++++++++++++++++++++++

The following configuration runs Weblate in Gunicorn and Apache 2.4
(available as :file:`weblate/examples/apache.gunicorn.conf`):

.. literalinclude:: ../../weblate/examples/apache.gunicorn.conf
    :language: apache

.. seealso::

    :doc:`django:howto/deployment/wsgi/gunicorn`


Running Weblate under path
++++++++++++++++++++++++++

.. versionadded:: 1.3

It is recommended to use prefork MPM when using WSGI with Weblate.

A sample Apache configuration to serve Weblate under ``/weblate``.
Again using ``mod_wsgi`` (also available as :file:`weblate/examples/apache-path.conf`):

.. literalinclude:: ../../weblate/examples/apache-path.conf
    :language: apache

Additionally, you will have to adjust :file:`weblate/settings.py`:

.. code-block:: python

    URL_PREFIX = "/weblate"

.. _celery:

Background tasks using Celery
-----------------------------

.. versionadded:: 3.2

Weblate uses Celery to process background tasks.
A typical setup using Redis as a back-end looks like this:

.. code-block:: python

   CELERY_TASK_ALWAYS_EAGER = False
   CELERY_BROKER_URL = "redis://localhost:6379"
   CELERY_RESULT_BACKEND = CELERY_BROKER_URL

.. seealso::

   :ref:`Redis broker configuration in Celery <celery:broker-redis-configuration>`

For development, you might want to use Eager configuration, which processes
all tasks in place, but has a negative performance impact on Weblate:

.. code-block:: python

   CELERY_TASK_ALWAYS_EAGER = True
   CELERY_BROKER_URL = "memory://"
   CELERY_TASK_EAGER_PROPAGATES = True

You should also start the Celery worker to process the tasks and start
scheduled tasks, this can be done directly from the command-line (which is mostly
useful when debugging or developing):

.. code-block:: sh

   ./weblate/examples/celery start
   ./weblate/examples/celery stop

.. note::

   The Celery process has to be executed by the same user as the WSGI
   process, otherwise files in the :setting:`DATA_DIR` are stored with
   mixed ownership, leading to runtime issues.

   See also :ref:`file-permissions` and :ref:`server`.


Running Celery as system service
++++++++++++++++++++++++++++++++

Most likely you will want to run Celery as a daemon, as described in
:doc:`celery:userguide/daemonizing`. For Linux setup using
systemd, you can use the example files shipped in the :file:`examples` folder
listed below.

The systemd unit should be placed in :file:`/etc/systemd/system/celery-weblate.service`:

.. literalinclude:: ../../weblate/examples/celery-weblate.service
    :language: ini

Environment configuration to be placed as :file:`/etc/default/celery-weblate`:

.. literalinclude:: ../../weblate/examples/celery-weblate.conf
    :language: sh

Additional configuration to rotate Celery logs using :command:`logrotate` to be
placed as :file:`/etc/logrotate.d/celery`:

.. literalinclude:: ../../weblate/examples/celery-weblate.logrotate
    :language: text

Periodic tasks using Celery beat
++++++++++++++++++++++++++++++++

Weblate comes with built-in setup for scheduled tasks.
Define additional tasks in :file:`settings.py`, for example see :ref:`lazy-commit`.

The tasks are supposed to be executed by Celery beat daemon.
If it is not working properly, it might not be running or its database corrupted.
Check the Celery startup logs to figure out root cause if that is the case.

Monitoring Celery status
++++++++++++++++++++++++

You can use :djadmin:`celery_queues` to see current length of Celery task
queues. If the queue gets too long, you also get a configuration
error in the admin interface.

.. warning::

   Celery errors are only in the Celery log by default, and not
   visible to the user. In case you want to have overview on such failures, it is
   recommended to configure :ref:`collecting-errors`.

.. seealso::

   :doc:`celery:userguide/configuration`,
   :doc:`celery:userguide/workers`,
   :doc:`celery:userguide/daemonizing`,
   :doc:`celery:userguide/monitoring`,
   :djadmin:`celery_queues`


Monitoring Weblate
------------------

Weblate provides the ``/healthz/`` URL to be used in simple health checks, for example
using Kubernetes.

.. _collecting-errors:

Collecting error reports
------------------------

As all software, Weblate can fail. To collect useful failure
states using third-party services to collect such info is recommended.
This is especially useful for failing Celery tasks, which would
otherwise only report errors to logs you are not notified of.
The following services are supported:

Sentry
++++++

Weblate has built-in support for `Sentry <https://sentry.io/>`_.
Use it by setting :setting:`SENTRY_DSN` in the :file:`settings.py`:

.. code-block:: python

   SENTRY_DSN = "https://id@your.sentry.example.com/"

Rollbar
+++++++

Weblate has built-in support for `Rollbar <https://rollbar.com/>`_. To use
Follow the instructions for `Rollbar notifier for
Python <https://docs.rollbar.com/docs/python/>`_ to use it.

In short, you need to adjust :file:`settings.py`:

.. code-block:: python

    # Add rollbar as last middleware:
    MIDDLEWARE = [
        # … other middleware classes …
        "rollbar.contrib.django.middleware.RollbarNotifierMiddleware",
    ]

    # Configure client access
    ROLLBAR = {
        "access_token": "POST_SERVER_ITEM_ACCESS_TOKEN",
        "client_token": "POST_CLIENT_ITEM_ACCESS_TOKEN",
        "environment": "development" if DEBUG else "production",
        "branch": "main",
        "root": "/absolute/path/to/code/root",
    }

Everything else is integrated automatically, you will now collect both server-
and client-side errors.

.. note:

    Error logging also includes exceptions that were gracefully handled, but
    might indicate a problem — such as failed parsing of an uploaded file.

Migrating Weblate to another server
-----------------------------------

Migrating Weblate to another server should be pretty easy, however it stores
data in few locations you should migrate carefully. The best approach is
to stop Weblate for the migration.

Migrating database
++++++++++++++++++

Depending on your database backend, you might have several options to migrate
the database. The most straightforward one is to dump the database on one
server and import it on the new one. Alternatively you can use replication in
case your database supports it.

The best approach is to use tools specific to the database, as they are usually
the most effective (e.g. :command:`mysqldump` or :command:`pg_dump`).
If you want to migrate between different databases, the only option might be to
use Django management to dump and import the database:

.. code-block:: sh

    # Export current data
    weblate dumpdata > /tmp/weblate.dump
    # Import dump
    weblate loaddata /tmp/weblate.dump

Migrating VCS repositories
+++++++++++++++++++++++++++

The VCS repositories stored under :setting:`DATA_DIR` need to be migrated as
well. You can simply copy them or use :command:`rsync` to do the migration
more effectively.

Other notes
+++++++++++

Don't forget to move other services Weblate might have been using like
Redis, Cron jobs or custom authentication back-ends.
