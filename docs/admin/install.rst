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

Depending on your setup and experience, choose an appropriate installation method for you:

* :doc:`install/docker`, recommended for production setups.

* Virtualenv installation, recommended for production setups:

  * :doc:`install/venv-debian`
  * :doc:`install/venv-suse`
  * :doc:`install/venv-redhat`
  * :doc:`install/venv-macos`

* :doc:`install/source`, recommended for development.

* :doc:`install/openshift`
* :doc:`install/kubernetes`


.. _architecture:

Architecture overview
---------------------

.. graphviz::

   digraph architecture {
      graph [fontname="sans-serif",
         fontsize=10,
         newrank=true,
         rankdir=LR,
         splines=ortho
      ];
      node [fontname="sans-serif",
         fontsize=10,
         height=0,
         margin=.15,
         shape=box
      ];
      edge [fontname="sans-serif",
         fontsize=10
      ];
      subgraph cluster_thirdparty {
         graph [color=lightgrey,
            label="Third-party services",
            style=filled
         ];
         mt	[label="Machine translation",
            style=dotted];
         sentry	[label="Sentry\nError collection",
            style=dotted];
         mail	[label="E-mail server"];
         auth	[label="SSO\nAuthentication provider",
            style=dotted];
      }
      subgraph cluster_ingress {
         graph [color=lightgrey,
            label=Ingress,
            style=filled
         ];
         web	[label="Web server",
            shape=hexagon];
      }
      subgraph cluster_weblate {
         graph [color=lightgrey,
            label="Weblate code-base",
            style=filled
         ];
         celery	[fillcolor="#144d3f",
            fontcolor=white,
            label="Celery workers",
            style=filled];
         wsgi	[fillcolor="#144d3f",
            fontcolor=white,
            label="WSGI server",
            style=filled];
      }
      subgraph cluster_services {
         graph [color=lightgrey,
            label=Services,
            style=filled
         ];
         redis	[label="Redis\nTask queue\nCache",
            shape=cylinder];
         db	[label="PostgreSQL\nDatabase",
            shape=cylinder];
         fs	[label=Filesystem,
            shape=cylinder];
      }
      web -> wsgi;
      web -> fs;
      celery -> mt	[style=dotted];
      celery -> sentry	[style=dotted];
      celery -> mail;
      celery -> redis;
      celery -> db;
      celery -> fs;
      wsgi -> mt	[style=dotted];
      wsgi -> sentry	[style=dotted];
      wsgi -> auth	[style=dotted];
      wsgi -> redis;
      wsgi -> db;
      wsgi -> fs;
   }

Web server
   Handling incoming HTTP requests, :ref:`static-files`.
Celery workers
   :ref:`celery` are executed here.

   Depending on your workload, you might want to customize the number of workers.

   Use dedicated node when scaling Weblate horizontally.
WSGI server
   A WSGI server serving web pages to users.

   Use dedicated node when scaling Weblate horizontally.
Database
   PostgreSQL database server for storing all the content, see :ref:`database-setup`.

   Use dedicated database node for sites with hundreds of millions of hosted words.
Redis
   Redis server for cache and tasks queue, see :ref:`celery`.

   Use dedicated node when scaling Weblate horizontally.
File system
   File system storage for storing VCS repositories and uploaded user data. This is shared by all the processes.

   Use networked storage when scaling Weblate horizontally.
E-mail server
   SMTP server for outgoing e-mail, see :ref:`out-mail`. It can be provided externally.

.. hint::

   :doc:`/admin/install/docker` includes PostgreSQL and Redis, making the installation easier.

.. _requirements:

Software requirements
---------------------

Operating system
++++++++++++++++

Weblate is known to work on Linux, FreeBSD and macOS. Other Unix like systems
will most likely work too.

Weblate is not supported on Windows. But it may still work and patches are
happily accepted.

.. seealso::

   :ref:`architecture` describes overall Weblate architecture and required services.

.. _python-deps:

Python dependencies
+++++++++++++++++++

Weblate is written in `Python <https://www.python.org/>`_ and supports Python
3.10 or newer. You can install dependencies using pip or from your
distribution packages, full list is available in :file:`requirements.txt`.

Most notable dependencies:

Django
    https://www.djangoproject.com/
Celery
    https://docs.celeryq.dev/
Translate Toolkit
    https://toolkit.translatehouse.org/
translation-finder
    https://github.com/WeblateOrg/translation-finder
Python Social Auth
    https://python-social-auth.readthedocs.io/
Django REST Framework
    https://www.django-rest-framework.org/

.. Table is generated using scripts/show-extras

.. list-table:: Optional dependencies
     :header-rows: 1

     * - pip extra
       - Python Package
       - Weblate feature


     * - ``alibaba``
       - `aliyun-python-sdk-alimt <https://pypi.org/project/aliyun-python-sdk-alimt>`_
       - :ref:`mt-alibaba`

     * - ``amazon``
       - `boto3 <https://pypi.org/project/boto3>`_
       - :ref:`mt-aws`


     * - ``antispam``
       - `python-akismet <https://pypi.org/project/python-akismet>`_
       - :ref:`spam-protection`


     * - ``gerrit``
       - `git-review <https://pypi.org/project/git-review>`_
       - :ref:`vcs-gerrit`


     * - ``google``
       - `google-cloud-translate <https://pypi.org/project/google-cloud-translate>`_
       - :ref:`mt-google-translate-api-v3`


     * - ``ldap``
       - `django-auth-ldap <https://pypi.org/project/django-auth-ldap>`_
       - :ref:`ldap-auth`



     * - ``mercurial``
       - `mercurial <https://pypi.org/project/mercurial>`_
       - :ref:`vcs-mercurial`


     * - ``mysql``
       - `mysqlclient <https://pypi.org/project/mysqlclient>`_
       - MySQL or MariaDB, see :ref:`database-setup`


     * - ``openai``
       - `openai <https://pypi.org/project/openai>`_
       - :ref:`mt-openai`

     * - ``postgres``
       - `psycopg <https://pypi.org/project/psycopg>`_
       - PostgreSQL, see :ref:`database-setup`



     * - ``saml``
       - `python3-saml <https://pypi.org/project/python3-saml>`_
       - :ref:`saml-auth`

     * - ``zxcvbn``
       - `django-zxcvbn-password <https://pypi.org/project/django-zxcvbn-password>`_
       - :ref:`password-authentication`

When installing using pip, you can directly specify desired features when installing:

.. code-block:: sh

   pip install "Weblate[Postgres,Amazon,SAML]"

Or you can install Weblate with all optional features:

.. code-block:: sh

   pip install "Weblate[all]"

Or you can install Weblate without any optional features:

.. code-block:: sh

   pip install Weblate

Other system requirements
+++++++++++++++++++++++++

The following dependencies have to be installed on the system:

``Git``
    https://git-scm.com/
Pango, Cairo and related header files and GObject introspection data
    https://cairographics.org/, https://pango.gnome.org/, see :ref:`pangocairo`
``git-review`` (optional for Gerrit support)
    https://pypi.org/project/git-review/
``git-svn`` (optional for Subversion support)
    https://git-scm.com/docs/git-svn
``tesseract`` (needed only if :program:`tesserocr` binary wheels are not available for your system)
    https://github.com/tesseract-ocr/tesseract
``licensee`` (optional for detecting license when creating component)
    https://github.com/licensee/licensee

Build-time dependencies
+++++++++++++++++++++++

To build some of the :ref:`python-deps` you might need to install their
dependencies. This depends on how you install them, so please consult
individual packages for documentation. You won't need those if using prebuilt
``Wheels`` while installing using ``pip`` or when you use distribution packages.

.. _pangocairo:

Pango and Cairo
+++++++++++++++

Weblate uses Pango and Cairo for rendering bitmap widgets (see
:ref:`promotion`) and rendering checks (see :ref:`fonts`). To properly install
Python bindings for those you need to install system libraries first - you need
both Cairo and Pango, which in turn need GLib. All those should be installed
with development files and GObject introspection data.

.. seealso::

  :doc:`install/venv-debian`,
  :doc:`install/venv-suse`,
  :doc:`install/venv-redhat`,
  :doc:`install/venv-macos`

.. include:: install/steps/hw.rst

.. _verify:

Verifying release signatures
----------------------------

Weblate release are cryptographically signed using `Sigstore signatures
<https://www.sigstore.dev/>`_. The signatures are attached to the GitHub
release.

The verification can be performed using `sigstore package
<https://pypi.org/project/sigstore/>`_. The following example verifies
signature of the 5.4 release:

.. code-block:: sh

   sigstore verify github  \
      --cert-identity https://github.com/WeblateOrg/weblate/.github/workflows/setup.yml@refs/tags/weblate-5.4 \
      --bundle Weblate-5.4-py3-none-any.whl.sigstore \
      Weblate-5.4-py3-none-any.whl

.. _file-permissions:

Filesystem permissions
----------------------

The Weblate process needs to be able to read and write to the directory where
it keeps data - :setting:`DATA_DIR`. All files within this directory should be
owned and writable by the user running all Weblate processes (typically WSGI and Celery, see :ref:`server` and :ref:`celery`).

The default configuration places them in the same tree as the Weblate sources, however
you might prefer to move these to a better location such as:
:file:`/var/lib/weblate`.

Weblate tries to create these directories automatically, but it will fail
when it does not have permissions to do so.

You should also take care when running :ref:`manage`, as they should be ran
under the same user as Weblate itself is running, otherwise permissions on some
files might be wrong.

In the Docker container, all files in the :file:`/app/data` volume have to be
owned by the ``weblate`` user inside the container (UID 1000).

.. seealso::

   :ref:`static-files`

.. _database-setup:

Database setup for Weblate
--------------------------

It is recommended to run Weblate with a PostgreSQL database server.

PostgreSQL 12 and higher is supported. PostgreSQL 15 or newer is recommended.

:ref:`mysql` is supported, but not recommended for new installs.



.. note::

   No other database servers are currently supported, but support for other
   Django supported databases should be possible to implement.

.. seealso::

   :ref:`production-database`,
   :doc:`django:ref/databases`,
   :ref:`database-migration`

.. _db-connections:

Database connections
++++++++++++++++++++

In the default configuration, each Weblate process keeps a persistent
connection to the database. Persistent connections improve Weblate
responsiveness, but might require more resources for the database server.
Please consult :setting:`django:CONN_MAX_AGE` and
:ref:`django:persistent-database-connections` for more info.

Weblate needs at least the following number of connections:

* :math:`(4 \times \mathit{nCPUs}) + 2` for Celery processes
* :math:`\mathit{nCPUs} + 1` for WSGI workers

This applies to Docker container defaults and example configurations provided
in this documentation, but the numbers will change once you customize the amount of
WSGI workers or adjust parallelism of Celery.

The actual limit for the number of database connections needs to be higher to
account following situations:

* :ref:`manage` need their connection as well.
* If case process is killed (for example by OOM killer), it might block the existing connection until timeout.

.. seealso::
   :ref:`celery`,
   :ref:`uwsgi`,
   :envvar:`WEBLATE_WORKERS`

.. _postgresql:

PostgreSQL
++++++++++

PostgreSQL is usually the best choice for Django-based sites. It's the reference
database used for implementing Django database layer.

.. note::

   Weblate uses trigram extension which has to be installed separately in some
   cases. Look for ``postgresql-contrib`` or a similarly named package.

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
    sudo -u postgres createdb -E UTF8 -O weblate weblate

.. hint::

   If you don't want to make the Weblate user a superuser in PostgreSQL, you can
   omit that. In that case you will have to perform some of the migration steps
   manually as a PostgreSQL superuser in schema Weblate will use:

   .. code-block:: postgres

        CREATE EXTENSION IF NOT EXISTS pg_trgm;
        CREATE EXTENSION IF NOT EXISTS btree_gin;

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
            # Persistent connections
            "CONN_MAX_AGE": None,
            "CONN_HEALTH_CHECKS": True,
        }
    }

The database migration performs `ALTER ROLE
<https://www.postgresql.org/docs/12/sql-alterrole.html>`_ on database role used
by Weblate. In most cases the name of the role matches username. In more
complex setups the role name is different than username and you will get error
about non-existing role during the database migration
(``psycopg2.errors.UndefinedObject: role "weblate@hostname" does not exist``).
This is known to happen with Azure Database for PostgreSQL, but it's not
limited to this environment. Please set ``ALTER_ROLE`` to change name of the
role Weblate should alter during the database migration.

.. seealso::

   :ref:`db-connections`

.. _mysql:

MySQL and MariaDB
+++++++++++++++++

.. warning::

   While MySQL and MariaDB support is still maintained in Weblate, our primary
   focus is PostgreSQL. It is recommended to use PostgreSQL for new installs,
   and to migrate existing installs to PostgreSQL, see
   :ref:`database-migration`.

   Some Weblate features will perform better with :ref:`postgresql`. This
   includes searching and translation memory, which both utilize full-text
   features in the database and PostgreSQL implementation is superior.

Weblate can be also used with MySQL or MariaDB, please see
:ref:`django:mysql-notes` and :ref:`django:mariadb-notes` for caveats using
Django with those. Because of the limitations it is recommended to use
:ref:`postgresql` for new installations.

Weblate requires MySQL at least 8 or MariaDB at least 10.4.

Following configuration is recommended for Weblate:

* Use the ``utf8mb4`` charset to allow representation of higher Unicode planes (for example emojis).
* Configure the server with ``innodb_large_prefix`` to allow longer indices on text fields.
* Set the isolation level to ``READ COMMITTED``.
* The SQL mode should be set to ``STRICT_TRANS_TABLES``.

MySQL 8.x, MariaDB 10.5.x or newer have reasonable default configuration so
that no server tweaking should be necessary and all what is needed can be
configured on the client side.

Below is an example :file:`/etc/my.cnf.d/server.cnf` for a server with 8 GB of
RAM. These settings should be sufficient for most installs. MySQL and MariaDB
have tunables that will increase the performance of your server that are
considered not necessary unless you are planning on having large numbers of
concurrent users accessing the system. See the various vendors documentation on
those details.

It is absolutely critical to reduce issues when installing that the setting
``innodb_file_per_table`` is set properly and MySQL/MariaDB restarted before
you start your Weblate install.

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

   In case you are getting ``#1071 - Specified key was too long; max key length
   is 767 bytes`` error, please update your configuration to include the ``innodb``
   settings above and restart your install.

.. hint::

   In case you are getting ``#2006 - MySQL server has gone away`` error,
   configuring :setting:`django:CONN_MAX_AGE` might help.

.. seealso::

   :ref:`db-connections`

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
you begin the install. Use the commands below to achieve that:

.. code-block:: sh

   GRANT ALL ON weblate.* to 'weblate'@'localhost' IDENTIFIED BY 'password';
   FLUSH PRIVILEGES;

.. seealso::

   :ref:`db-connections`

Other configurations
--------------------

.. _out-mail:

Configuring outgoing e-mail
+++++++++++++++++++++++++++

Weblate sends out e-mails on various occasions - for account activation and on
various notifications configured by users. For this it needs access to an SMTP
server.

The mail server setup is configured using these settings:
:setting:`django:EMAIL_HOST`, :setting:`django:EMAIL_HOST_PASSWORD`,
:setting:`django:EMAIL_USE_TLS`, :setting:`django:EMAIL_USE_SSL`,
:setting:`django:EMAIL_HOST_USER` and :setting:`django:EMAIL_PORT`. Their
names are quite self-explanatory, but you can find more info in the
Django documentation.

.. hint::

    In case you get error about not supported authentication (for example
    ``SMTP AUTH extension not supported by server``), it is most likely caused
    by using insecure connection and server refuses to authenticate this way.
    Try enabling :setting:`django:EMAIL_USE_TLS` in such case.

.. seealso::

   :ref:`debug-mails`,
   :ref:`Configuring outgoing e-mail in Docker container <docker-mail>`

.. _reverse-proxy:

Running behind reverse proxy
++++++++++++++++++++++++++++

Several features in Weblate rely on being able to get client IP address. This
includes :ref:`rate-limit`, :ref:`spam-protection` or :ref:`audit-log`.

In default configuration Weblate parses IP address from ``REMOTE_ADDR`` which
is set by the WSGI handler.

In case you are running a reverse proxy, this field will most likely contain
its address. You need to configure Weblate to trust additional HTTP headers and
parse the IP address from these. This can not be enabled by default as it would
allow IP address spoofing for installations not using a reverse proxy. Enabling
:setting:`IP_BEHIND_REVERSE_PROXY` might be enough for the most usual setups,
but you might need to adjust :setting:`IP_PROXY_HEADER` and
:setting:`IP_PROXY_OFFSET` as well.

Another thing to take care of is the :http:header:`Host` header. It should match
to whatever is configured as :setting:`SITE_DOMAIN`. Additional configuration
might be needed in your reverse proxy (for example use ``ProxyPreserveHost On``
for Apache or ``proxy_set_header Host $host;`` with nginx).

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

Weblate does execute VCS commands and those accept proxy configuration from
environment. The recommended approach is to define proxy settings in
:file:`settings.py`:

.. code-block:: python

   import os

   os.environ["http_proxy"] = "http://proxy.example.com:8080"
   os.environ["HTTPS_PROXY"] = "http://proxy.example.com:8080"

.. seealso::

   `Proxy Environment Variables <https://everything.curl.dev/usingcurl/proxies/env.html>`_

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
    wrong, for example notifications on failed merges, or Django errors.

    Contact form sends e-mail on these as well unless :setting:`ADMINS_CONTACT`
    is configured.

    .. seealso::

        :setting:`django:ADMINS`,
        :setting:`ADMINS_CONTACT`,
        :ref:`production-admins`

.. setting:: ALLOWED_HOSTS

``ALLOWED_HOSTS``

    You need to set this to list the hosts your site is supposed to serve. For
    example:

    .. code-block:: python

        ALLOWED_HOSTS = ["demo.weblate.org"]

    Alternatively you can include wildcard:

    .. code-block:: python

        ALLOWED_HOSTS = ["*"]

    .. seealso::

        :setting:`django:ALLOWED_HOSTS`,
        :envvar:`WEBLATE_ALLOWED_HOSTS`,
        :ref:`production-hosts`

.. setting:: SESSION_ENGINE

``SESSION_ENGINE``

    Configure how your sessions will be stored. In case you keep the default
    database backend engine, you should schedule:
    :command:`weblate clearsessions` to remove stale session data from the
    database.

    If you are using Redis as cache (see :ref:`production-cache`) it is
    recommended to use it for sessions as well:

    .. code-block:: python

         SESSION_ENGINE = "django.contrib.sessions.backends.cache"

    .. seealso::

        :ref:`django:configuring-sessions`,
        :setting:`django:SESSION_ENGINE`

.. setting:: DATABASES

``DATABASES``

    Connectivity to database server, please check Django's documentation for more
    details.

    .. seealso::

        :ref:`database-setup`,
        :setting:`django:DATABASES`,
        :doc:`django:ref/databases`

.. setting:: DEBUG

``DEBUG``

    Disable this for any production server. With debug mode enabled, Django will
    show backtraces in case of error to users, when you disable it, errors will
    be sent per e-mail to ``ADMINS`` (see above).

    Debug mode also slows down Weblate, as Django stores much more info
    internally in this case.

    .. seealso::

        :setting:`django:DEBUG`,
        :ref:`production-debug`

.. setting:: DEFAULT_FROM_EMAIL

``DEFAULT_FROM_EMAIL``

    E-mail sender address for outgoing e-mail, for example registration e-mails.

    .. seealso::

        :setting:`django:DEFAULT_FROM_EMAIL`

.. setting:: SECRET_KEY

``SECRET_KEY``

    Key used by Django to sign some info in cookies, see
    :ref:`production-secret` for more info.

    .. seealso::

        :setting:`django:SECRET_KEY`

.. setting:: SERVER_EMAIL

``SERVER_EMAIL``

    E-mail used as sender address for sending e-mails to the administrator, for
    example notifications on failed merges.

    .. seealso::

        :setting:`django:SERVER_EMAIL`

.. _tables-setup:

Filling up the database
-----------------------

After your configuration is ready, you can run
:wladmin:`migrate` to create the database structure. Now you should be
able to create translation projects using the admin interface.

Once you are done, you should also check the :guilabel:`Performance report` in the
admin interface, which will give you hints of potential non optimal configuration on your
site.

.. seealso::

   :ref:`config`,
   :ref:`privileges`

.. _production:

Production setup
----------------

For a production setup you should carry out adjustments described in the following sections.
The most critical settings will trigger a warning, which is indicated by an
exclamation mark in the top bar if signed in as a superuser:

.. image:: /screenshots/admin-wrench.webp

It is also recommended to inspect checks triggered by Django (though you might not
need to fix all of them):

.. code-block:: sh

    weblate check --deploy

You can also review the very same checklist at :ref:`manage-performance` in the :ref:`management-interface`.

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

Set the correct admin addresses to the :setting:`ADMINS` setting to defining who will receive
e-mails in case something goes wrong on the server, for example:

.. code-block:: python

    ADMINS = (("Your Name", "your_email@example.com"),)

.. seealso::

   :ref:`configuration`

.. _production-site:

Set correct site domain
+++++++++++++++++++++++

Adjust site name and domain in the admin interface, otherwise links in RSS or
registration e-mails will not work. This is configured using
:setting:`SITE_DOMAIN` which should contain site domain name.

.. versionchanged:: 4.2

   Prior to the 4.2 release the Django sites framework was used instead, please
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

    You might want to set up HSTS as well, see
    :ref:`django:security-recommendation-ssl` for more details.

.. seealso::

   :setting:`ENABLE_HTTPS`,
   :ref:`production-hosts`,
   :ref:`production-site`


Set properly SECURE_HSTS_SECONDS
++++++++++++++++++++++++++++++++

If your site is served over SSL, you have to consider setting a value for :setting:`django:SECURE_HSTS_SECONDS`
in the :file:`settings.py` to enable HTTP Strict Transport Security.
By default it's set to 0 as shown below.

.. code-block:: python

   SECURE_HSTS_SECONDS = 0

If set to a non-zero integer value, the :class:`django:django.middleware.security.SecurityMiddleware`
sets the :ref:`django:http-strict-transport-security` header on all responses that do not already have it.

.. warning::

    Setting this incorrectly can irreversibly (for some time) break your site. Read the
    :ref:`django:http-strict-transport-security` documentation first.


.. _production-database:

Use a powerful database engine
++++++++++++++++++++++++++++++

* Please use PostgreSQL for a production environment, see :ref:`database-setup`
  for more info.
* Use adjacent location for running the database server, otherwise the networking
  performance or reliability might ruin your Weblate experience.
* Check the database server performance or tweak its configuration, for example
  using `PGTune <https://pgtune.leopard.in.ua/>`_.

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

In addition to caching of Django, Weblate performs caching of avatars. It is
recommended to use a separate, file-backed cache for this purpose:

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

   To disable sending e-mails by Weblate set :setting:`django:EMAIL_BACKEND`
   to ``django.core.mail.backends.dummy.EmailBackend``.

   This will disable *all* e-mail delivery including registration or password
   reset e-mails.

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
your site is allowed to serve, leaving it empty will block any requests.

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

You can generate a new key using :program:`weblate-generate-secret-key` shipped
with Weblate.

.. seealso::

    :setting:`SECRET_KEY`

.. _production-cron:

Running maintenance tasks
+++++++++++++++++++++++++

For optimal performance, it is good idea to run some maintenance tasks in the
background. This is automatically done by :ref:`celery` and covers following tasks:

* Configuration health check (hourly).
* Committing pending changes (hourly), see :ref:`lazy-commit` and :wladmin:`commit_pending`.
* Updating component alerts (daily).
* Update remote branches (nightly), see :setting:`AUTO_UPDATE`.
* Translation memory backup to JSON (daily), see :wladmin:`dump_memory`.
* Fulltext and database maintenance tasks (daily and weekly tasks), see :wladmin:`cleanuptrans`.

.. _production-encoding:

System locales and encoding
+++++++++++++++++++++++++++

The system locales should be configured to UTF-8 capable ones. On most Linux
distributions this is the default setting. In case it is not the case on your
system, please change locales to UTF-8 variant.

For example by editing :file:`/etc/default/locale` and setting there
``LANG="C.UTF-8"``.

In some cases the individual services have separate configuration for locales.
This varies between distribution and web servers, so check documentation of
your web server packages for that.

Apache on Ubuntu uses :file:`/etc/apache2/envvars`:

.. code-block:: sh

    export LANG='en_US.UTF-8'
    export LC_ALL='en_US.UTF-8'

Apache on CentOS uses :file:`/etc/sysconfig/httpd` (or
:file:`/opt/rh/httpd24/root/etc/sysconfig/httpd`):

.. code-block:: sh

    LANG='en_US.UTF-8'

.. _production-certs:

Using custom certificate authority
++++++++++++++++++++++++++++++++++

Weblate does verify SSL certificates during HTTP requests. In case you are
using custom certificate authority which is not trusted in default bundles, you
will have to add its certificate as trusted.

The preferred approach is to do this at system level, please check your distro
documentation for more details (for example on debian this can be done by
placing the CA certificate into :file:`/usr/local/share/ca-certificates/` and
running :command:`update-ca-certificates`).

Once this is done, system tools will trust the certificate and this includes
Git.

For Python code, you will need to configure requests to use system CA bundle
instead of the one shipped with it. This can be achieved by placing following
snippet to :file:`settings.py` (the path is Debian specific):

.. code-block:: python

    import os

    os.environ["REQUESTS_CA_BUNDLE"] = "/etc/ssl/certs/ca-certificates.crt"


.. _production-compress:

Compressing client assets
+++++++++++++++++++++++++

Weblate comes with a bunch of JavaScript and CSS files. For performance reasons
it is good to compress them before sending to a client. In default
configuration this is done on the fly at cost of little overhead. On big
installations, it is recommended to enable offline compression mode. This needs
to be done in the configuration and the compression has to be triggered on
every Weblate upgrade.

The configuration switch is simple by enabling
:attr:`compressor:django.conf.settings.COMPRESS_OFFLINE` and configuring
:attr:`compressor:django.conf.settings.COMPRESS_OFFLINE_CONTEXT` (the latter is
already included in the example configuration):

.. code-block:: python

    COMPRESS_OFFLINE = True

On each deploy you need to compress the files to match current version:

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

   In case you are not experienced with services described below, you might want to try :doc:`install/docker`.

You will need several services to run Weblate, the recommended setup consists of:

* Database server (see :ref:`database-setup`)
* Cache server (see :ref:`production-cache`)
* Frontend web server for static files and SSL termination (see :ref:`static-files`)
* WSGI server for dynamic content (see :ref:`uwsgi`)
* Celery for executing background tasks (see :ref:`celery`)

.. note::

   There are some dependencies between the services, for example cache and
   database should be running when starting up Celery or uwsgi processes.

In most cases, you will run all services on single (virtual) server, but in
case your installation is heavy loaded, you can split up the services. The only
limitation on this is that Celery and Wsgi servers need access to
:setting:`DATA_DIR`.

.. note::

   The WSGI process has to be executed under the same user the Celery
   process, otherwise files in the :setting:`DATA_DIR` will be stored with
   mixed ownership, leading to runtime issues.

   See also :ref:`file-permissions` and :ref:`celery`.

Running web server
++++++++++++++++++

Running Weblate is not different from running any other Django based
program. Django is usually executed as uWSGI or fcgi (see examples for
different webservers below).

For testing purposes, you can use the built-in web server in Django:

.. code-block:: sh

    weblate runserver

.. warning::

    DO NOT USE THIS SERVER IN A PRODUCTION SETTING. It has not gone through
    security audits or performance tests. See also Django documentation on
    :djadmin:`django:runserver`.

.. hint::

   The Django built-in server serves static files only with :setting:`DEBUG`
   enabled as it is intended for development only. For production use, please
   see WSGI setups in :ref:`uwsgi`, :ref:`apache`, :ref:`apache-gunicorn`, and
   :ref:`static-files`.

.. _static-files:

Serving static files
++++++++++++++++++++

Django needs to collect its static files in a single directory. To do so,
execute :samp:`weblate collectstatic --noinput`. This will copy the static
files into a directory specified by the :setting:`django:STATIC_ROOT` setting (this defaults to
a ``static`` directory inside :setting:`CACHE_DIR`).

It is recommended to serve static files directly from your web server, you should
use that for the following paths:

:file:`/static/`
    Serves static files for Weblate and the admin interface
    (from defined by :setting:`django:STATIC_ROOT`).
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
middleware which sets security related HTTP headers like ``Content-Security-Policy``
or ``X-XSS-Protection``. These are by default set up to work with Weblate and its
configuration, but this might need customization for your environment.

.. seealso::

    :setting:`CSP_SCRIPT_SRC`,
    :setting:`CSP_IMG_SRC`,
    :setting:`CSP_CONNECT_SRC`,
    :setting:`CSP_STYLE_SRC`,
    :setting:`CSP_FONT_SRC`
    :setting:`CSP_FORM_SRC`

.. _uwsgi:

Sample configuration for NGINX and uWSGI
++++++++++++++++++++++++++++++++++++++++


To run production webserver, use the WSGI wrapper installed with Weblate (in
virtual env case it is installed as
:file:`~/weblate-env/lib/python3.9/site-packages/weblate/wsgi.py`).  Don't
forget to set the Python search path to your virtualenv as well (for example
using ``virtualenv = /home/user/weblate-env`` in uWSGI).

The following configuration runs Weblate as uWSGI under the NGINX webserver.

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

It is recommended to use prefork MPM when using WSGI with Weblate.

The following configuration runs Weblate as WSGI, you need to have enabled
``mod_wsgi`` (available as :file:`weblate/examples/apache.conf`):

.. literalinclude:: ../../weblate/examples/apache.conf
    :language: apache

.. note::

    Weblate requires Python 3, so please ensure you are running Python 3
    variant of the modwsgi. Usually it is available as a separate package, for
    example ``libapache2-mod-wsgi-py3``.

    Use matching Python version to install Weblate.

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

It is recommended to use prefork MPM when using WSGI with Weblate.

A sample Apache configuration to serve Weblate under ``/weblate``. Again using
``mod_wsgi`` (also available as :file:`weblate/examples/apache-path.conf`):

.. literalinclude:: ../../weblate/examples/apache-path.conf
    :language: apache

Additionally, you will have to adjust :file:`weblate/settings.py`:

.. code-block:: python

    URL_PREFIX = "/weblate"

.. _celery:

Background tasks using Celery
-----------------------------

Weblate uses Celery to execute regular and background tasks. You are supposed
to run a Celery service that will execute these. For example, it is responsible
for handling following operations (this list is not complete):

* Receiving webhooks from external services (see :ref:`hooks`).
* Running regular maintenance tasks such as backups, cleanups, daily add-ons, or updates
  (see :ref:`backup`, :setting:`BACKGROUND_TASKS`, :ref:`addons`).
* Running :ref:`auto-translation`.
* Sending digest notifications.
* Offloading expensive operations from the WSGI process.
* Committing pending changes (see :ref:`lazy-commit`).

A typical setup using Redis as a backend looks like this:

.. code-block:: python

   CELERY_TASK_ALWAYS_EAGER = False
   CELERY_BROKER_URL = "redis://localhost:6379"
   CELERY_RESULT_BACKEND = CELERY_BROKER_URL

.. seealso::

   :ref:`Redis broker configuration in Celery <celery:broker-redis-configuration>`

You should also start the Celery worker to process the tasks and start
scheduled tasks, this can be done directly on the command-line (which is mostly
useful when debugging or developing):

.. code-block:: sh

   ./weblate/examples/celery start
   ./weblate/examples/celery stop

.. note::

   The Celery process has to be executed under the same user as the WSGI
   process, otherwise files in the :setting:`DATA_DIR` will be stored with
   mixed ownership, leading to runtime issues.

   See also :ref:`file-permissions` and :ref:`server`.

Executing Celery tasks in the WSGI using eager mode
+++++++++++++++++++++++++++++++++++++++++++++++++++

.. note::

   This will have severe performance impact on the web interface, and will
   break features depending on regular trigger (for example committing pending
   changes, digest notifications, or backups).

For development, you might want to use eager configuration, which does process
all tasks in place:

.. code-block:: python

   CELERY_TASK_ALWAYS_EAGER = True
   CELERY_BROKER_URL = "memory://"
   CELERY_TASK_EAGER_PROPAGATES = True

Running Celery as system service
++++++++++++++++++++++++++++++++

Most likely you will want to run Celery as a daemon and that is covered by
:doc:`celery:userguide/daemonizing`. For the most common Linux setup using
systemd, you can use the example files shipped in the :file:`examples` folder
listed below.

Systemd unit to be placed as :file:`/etc/systemd/system/celery-weblate.service`:

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

Weblate comes with built-in setup for scheduled tasks. You can however define
additional tasks in :file:`settings.py`, for example see :ref:`lazy-commit`.

The tasks are supposed to be executed by Celery beats daemon. In case it is not
working properly, it might not be running or its database was corrupted. Check
the Celery startup logs in such case to figure out root cause.

.. _monitoring-celery:

Monitoring Celery status
++++++++++++++++++++++++

You can find current length of the Celery task queues in the
:ref:`management-interface` or you can use :wladmin:`celery_queues` on the
command-line. In case the queue will get too long, you will also get
configuration error in the admin interface.

.. warning::

   The Celery errors are by default only logged into Celery log and are not
   visible to user. In case you want to have overview on such failures, it is
   recommended to configure :ref:`collecting-errors`.

.. seealso::

   :ref:`monitoring`,
   :ref:`faq-monitoring`,
   :doc:`celery:userguide/configuration`,
   :doc:`celery:userguide/workers`,
   :doc:`celery:userguide/daemonizing`,
   :doc:`celery:userguide/monitoring`,
   :wladmin:`celery_queues`

.. _minimal-celery:

Single-process Celery setup
+++++++++++++++++++++++++++

In case you have very limited memory, you might want to reduce number of
Weblate processes. All Celery tasks can be executed in a single process using:

.. code-block:: sh

   celery --app=weblate.utils worker --beat --queues=celery,notify,memory,translate,backup --pool=solo

An installation using Docker can be configured to use a single-process Celery setup by setting :envvar:`CELERY_SINGLE_PROCESS`.

.. warning::

   This will have a noticeable performance impact on Weblate.

.. _monitoring:

Monitoring Weblate
------------------

Weblate provides the ``/healthz/`` URL to be used in simple health checks, for example
using Kubernetes. The Docker container has built-in health check using this URL.

For monitoring metrics of Weblate you can use :http:get:`/api/metrics/` API endpoint.

.. seealso::

   :ref:`faq-monitoring`,
   :ref:`monitoring-celery`,
   `Weblate plugin for Munin <https://github.com/WeblateOrg/munin>`_

.. _collecting-errors:

Collecting error reports and monitoring performance
---------------------------------------------------

Weblate, as any other software, can fail. In order to collect useful failure
states we recommend to use third party services to collect such information.
This is especially useful in case of failing Celery tasks, which would
otherwise only report error to the logs and you won't get notified on them.
Weblate has support for the following services:

Sentry
++++++

Weblate has built-in support for `Sentry <https://sentry.io/>`_. To use
it, it's enough to set :setting:`SENTRY_DSN` in the :file:`settings.py`:

.. code-block:: python

   SENTRY_DSN = "https://id@your.sentry.example.com/"

Sentry can be also used to monitor performance of Weblate by collecting traces
and profiles for defined percentage of operations. This can be configured using
:setting:`SENTRY_TRACES_SAMPLE_RATE` and :setting:`SENTRY_PROFILES_SAMPLE_RATE`.

.. seealso::

   `Sentry Performance Monitoring <https://docs.sentry.io/product/performance/>`_,
   `Sentry Profiling <https://docs.sentry.io/product/explore/profiling/>`_

Rollbar
+++++++

Weblate has built-in support for `Rollbar <https://rollbar.com/>`_. To use
it, it's enough to follow instructions for `Rollbar notifier for Python <https://docs.rollbar.com/docs/python/>`_.

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

Everything else is integrated automatically, you will now collect both server
and client side errors.

.. note::

    Error logging also includes exceptions that were gracefully handled, but
    might indicate a problem - such as failed parsing of an uploaded file.

Migrating Weblate to another server
-----------------------------------

Migrating Weblate to another server should be pretty easy, however it stores
data in few locations which you should migrate carefully. The best approach is
to stop Weblate for the migration.

Migrating database
++++++++++++++++++

Depending on your database backend, you might have several options to migrate
the database. The most straightforward approach is to use database native
tools, as they are usually the most effective (e.g. :command:`mysqldump` or
:command:`pg_dump`). Alternatively you can use replication in
case your database supports it.

.. seealso::

   Migrating between databases described in :ref:`database-migration`.

Migrating VCS repositories
+++++++++++++++++++++++++++

The VCS repositories stored under :setting:`DATA_DIR` need to be migrated as
well. You can simply copy them or use :command:`rsync` to do the migration
more effectively.

Other notes
+++++++++++

Don't forget to move other services Weblate might have been using like
Redis, Cron jobs or custom authentication backends.
