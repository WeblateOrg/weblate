.. _deployments:

Weblate deployments
===================

This is an overview of the supported deployment technologies.

.. _docker:

Running Weblate with Docker
-----------------------------

With dockerized Weblate deployment you can get your personal Weblate instance
up an running in seconds. All of Weblate's dependencies are already included.
PostgreSQL is set up as the default database.

.. _docker-deploy:

Deployment
++++++++++

The following examples assume you have a working Docker environment, with
``docker-compose`` installed. Please check the Docker documentation for instructions.

1. Clone the weblate-docker repo:

   .. code-block:: sh

        git clone https://github.com/WeblateOrg/docker-compose.git weblate-docker
        cd weblate-docker

2. Create a :file:`docker-compose.override.yml` file with your settings.
   See :ref:`docker-environment` for full list of environment variables.

   .. code-block:: yaml

        version: '3'
        services:
          weblate:
            environment:
              - WEBLATE_EMAIL_HOST=smtp.example.com
              - WEBLATE_EMAIL_HOST_USER=user
              - WEBLATE_EMAIL_HOST_PASSWORD=pass
              - WEBLATE_SERVER_EMAIL=weblate@example.com
              - WEBLATE_DEFAULT_FROM_EMAIL=weblate@example.com
              - WEBLATE_ALLOWED_HOSTS=weblate.example.com,localhost
              - WEBLATE_ADMIN_PASSWORD=password for the admin user
              - WEBLATE_ADMIN_EMAIL=weblate.admin@example.com

   .. note::

        If :envvar:`WEBLATE_ADMIN_PASSWORD` is not set, the admin user is created with
        a random password shown on first startup.
        
        Append ',localhost' to *WEBLATE_ALLOWED_HOSTS* to be able to access locally for testing.
        
        You may also need to edit the *docker-compose.yml* file and change the default port from 80 if you already have a web server running on your local machine

3. Start Weblate containers:

   .. code-block:: sh

        docker-compose up

Enjoy your Weblate deployment, it's accessible on port 80 of the ``weblate`` container.

.. versionchanged:: 2.15-2

    The setup has changed recently, priorly there was separate web server
    container, since 2.15-2 the web server is embedded in the Weblate container.

.. seealso:: :ref:`invoke-manage`

.. _docker-ssl:

Docker container with HTTPS support
+++++++++++++++++++++++++++++++++++

Please see :ref:`docker-deploy` for generic deployment instructions. To add a
reverse HTTPS proxy an additional Docker container is required,
`https-portal <https://hub.docker.com/r/steveltn/https-portal/>`_ will be used.
This is made use of in the :file:`docker-compose-https.yml` file.
Then create a :file:`docker-compose-https.override.yml` file with your settings:

.. code-block:: yaml

    version: '3'
    services:
      weblate:
        environment:
          - WEBLATE_EMAIL_HOST=smtp.example.com
          - WEBLATE_EMAIL_HOST_USER=user
          - WEBLATE_EMAIL_HOST_PASSWORD=pass
          - WEBLATE_ALLOWED_HOSTS=weblate.example.com
          - WEBLATE_ADMIN_PASSWORD=password for admin user
      https-portal:
        environment:
          DOMAINS: 'weblate.example.com -> http://weblate'

Whenever invoking :program:`docker-compose` you need to pass both files to it,
and then do:

.. code-block:: console

    docker-compose -f docker-compose-https.yml -f docker-compose-https.override.yml build
    docker-compose -f docker-compose-https.yml -f docker-compose-https.override.yml up

Upgrading the Docker container
++++++++++++++++++++++++++++++

Usually it is good idea to only update the Weblate container and keep the PostgreSQL
container at the version you have, as upgrading PostgreSQL is quite painful and in most
cases does not bring many benefits.

You can do this by sticking with the existing docker-compose and just pull
the latest images and then restart:

.. code-block:: sh

    docker-compose stop
    docker-compose pull
    docker-compose up

The Weblate database should be automatically migrated on first startup, and there
should be no need for additional manual actions.

.. note::

    Upgrades across 3.0 are not supported by Weblate. If you are on 2.x series
    and want to upgrade to 3.x, first upgrade to the latest 3.0.1-x (at time of
    writing this it is the ``3.0.1-7``) image, which will do the migration and then
    continue upgrading to newer versions.

.. _docker-environment:

Docker environment variables
++++++++++++++++++++++++++++

Many of Weblate's :ref:`config` can be set in the Docker container using environment variables:

Generic settings
~~~~~~~~~~~~~~~~

.. envvar:: WEBLATE_DEBUG

    Configures Django debug mode using :setting:`DEBUG`.

    **Example:**

    .. code-block:: yaml

        environment:
          - WEBLATE_DEBUG=1

    .. seealso::

            :ref:`production-debug`.

.. envvar:: WEBLATE_LOGLEVEL

    Configures the logging verbosity.


.. envvar:: WEBLATE_SITE_TITLE

    Configures the site-title shown on the heading of all pages.

.. envvar:: WEBLATE_ADMIN_NAME
.. envvar:: WEBLATE_ADMIN_EMAIL

    Configures the site-admin's name and email.

    **Example:**

    .. code-block:: yaml

        environment:
          - WEBLATE_ADMIN_NAME=Weblate admin
          - WEBLATE_ADMIN_EMAIL=noreply@example.com

    .. seealso::

            :ref:`production-admins`

.. envvar:: WEBLATE_ADMIN_PASSWORD

    Sets the password for the admin user. If not set, the admin user is created with a random
    password shown on first startup.

    .. versionchanged:: 2.9

        Since version 2.9, the admin user is adjusted on every container
        startup to match :envvar:`WEBLATE_ADMIN_PASSWORD`, :envvar:`WEBLATE_ADMIN_NAME`
        and :envvar:`WEBLATE_ADMIN_EMAIL`.

.. envvar:: WEBLATE_SERVER_EMAIL
.. envvar:: WEBLATE_DEFAULT_FROM_EMAIL

    Configures the address for outgoing emails.

    .. seealso::

        :ref:`production-email`

.. envvar:: WEBLATE_ALLOWED_HOSTS

    Configures allowed HTTP hostnames using :setting:`ALLOWED_HOSTS` and sets
    sitename to the first one.

    **Example:**

    .. code-block:: yaml

        environment:
          - WEBLATE_ALLOWED_HOSTS=weblate.example.com,example.com

    .. seealso::

        :ref:`production-hosts`,
        :ref:`production-site`

.. envvar:: WEBLATE_SECRET_KEY

    Configures the secret used by Django for cookie signing.

    .. deprecated:: 2.9

        The secret is now generated automatically on first startup, there is no
        need to set it manually.

    .. seealso::

        :ref:`production-secret`

.. envvar:: WEBLATE_REGISTRATION_OPEN

    Configures whether registrations are open by toggling :std:setting:`REGISTRATION_OPEN`.

    **Example:**

    .. code-block:: yaml

        environment:
          - WEBLATE_REGISTRATION_OPEN=0

.. envvar:: WEBLATE_TIME_ZONE

    Configures the used time-zone.

.. envvar:: WEBLATE_ENABLE_HTTPS

    Makes Weblate assume it is operated behind a reverse HTTPS proxy, it makes
    Weblate use HTTPS in email and API links or set secure flags on cookies.

    .. note::

        This does not make the Weblate container accept HTTPS connections, you
        need to use a standalone reverse HTTPS proxy, see :ref:`docker-ssl` for
        example.

    **Example:**

    .. code-block:: yaml

        environment:
          - WEBLATE_ENABLE_HTTPS=1

    .. seealso::

        :ref:`production-site`

.. envvar:: WEBLATE_IP_PROXY_HEADER

    Lets Weblate fetching the IP address from any given HTTP header. Use this when using
    a reverse proxy in front of the Weblate container.

    Enables :setting:`IP_BEHIND_REVERSE_PROXY` and sets :setting:`IP_PROXY_HEADER`.

    **Example:**

    .. code-block:: yaml

        environment:
          - WEBLATE_IP_PROXY_HEADER=HTTP_X_FORWARDED_FOR


.. envvar:: WEBLATE_REQUIRE_LOGIN

    Configures login required for the whole of the Weblate installation using :setting:`LOGIN_REQUIRED_URLS`.

    **Example:**

    .. code-block:: yaml

        environment:
          - WEBLATE_REQUIRE_LOGIN=1

.. envvar:: WEBLATE_LOGIN_REQUIRED_URLS_EXCEPTIONS

    Adds URL exceptions for login required for the whole Weblate installation using :setting:`LOGIN_REQUIRED_URLS_EXCEPTIONS`.

.. envvar:: WEBLATE_GOOGLE_ANALYTICS_ID

    Configures ID for Google Analytics by changing :setting:`GOOGLE_ANALYTICS_ID`.

.. envvar:: WEBLATE_GITHUB_USERNAME

    Configures GitHub username for GitHub pull-requests by changing
    :setting:`GITHUB_USERNAME`.

    .. seealso::

       :ref:`github-push`,
       :ref:`hub-setup`

.. envvar:: WEBLATE_SIMPLIFY_LANGUAGES

    Configures the language simplification policy, see :setting:`SIMPLIFY_LANGUAGES`.

.. envvar:: WEBLATE_AKISMET_API_KEY

    Configures the Akismet API key, see :setting:`AKISMET_API_KEY`.


Machine translation settings
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. envvar:: WEBLATE_MT_DEEPL_KEY

    Enables :ref:`deepl` machine translation and sets :setting:`MT_DEEPL_KEY`

.. envvar:: WEBLATE_MT_GOOGLE_KEY

    Enables :ref:`google-translate` and sets :setting:`MT_GOOGLE_KEY`

.. envvar:: WEBLATE_MT_MICROSOFT_COGNITIVE_KEY

    Enables :ref:`ms-cognitive-translate` and sets :setting:`MT_MICROSOFT_COGNITIVE_KEY`

.. envvar:: WEBLATE_MT_MYMEMORY_ENABLED

    Enables :ref:`mymemory` machine translation and sets
    :setting:`MT_MYMEMORY_EMAIL` to :envvar:`WEBLATE_ADMIN_EMAIL`.

.. envvar:: WEBLATE_MT_GLOSBE_ENABLED

    Enables :ref:`glosbe` machine translation.

Authentication settings
~~~~~~~~~~~~~~~~~~~~~~~

LDAP
++++

.. envvar:: WEBLATE_AUTH_LDAP_SERVER_URI
.. envvar:: WEBLATE_AUTH_LDAP_USER_DN_TEMPLATE
.. envvar:: WEBLATE_AUTH_LDAP_USER_ATTR_MAP
.. envvar:: WEBLATE_AUTH_LDAP_BIND_DN
.. envvar:: WEBLATE_AUTH_LDAP_BIND_PASSWORD

    LDAP authentication configuration.

    **Example:**

    .. code-block:: yaml

        environment:
          - WEBLATE_AUTH_LDAP_SERVER_URI=ldap://ldap.example.org
          - WEBLATE_AUTH_LDAP_USER_DN_TEMPLATE=uid=%(user)s,ou=People,dc=example,dc=net
          # map weblate 'full_name' to ldap 'name' and weblate 'email' attribute to 'mail' ldap attribute.
          # another example that can be used with OpenLDAP: 'full_name:cn,email:mail'
          - WEBLATE_AUTH_LDAP_USER_ATTR_MAP=full_name:name,email:mail

    .. seealso::

        :ref:`ldap-auth`

GitHub
++++++

.. envvar:: WEBLATE_SOCIAL_AUTH_GITHUB_KEY
.. envvar:: WEBLATE_SOCIAL_AUTH_GITHUB_SECRET

    Enables :ref:`github_auth`.

BitBucket
+++++++++

.. envvar:: WEBLATE_SOCIAL_AUTH_BITBUCKET_KEY
.. envvar:: WEBLATE_SOCIAL_AUTH_BITBUCKET_SECRET

    Enables :ref:`bitbucket_auth`.

Facebook
++++++++

.. envvar:: WEBLATE_SOCIAL_AUTH_FACEBOOK_KEY
.. envvar:: WEBLATE_SOCIAL_AUTH_FACEBOOK_SECRET

    Enables :ref:`facebook_auth`.

Google
++++++

.. envvar:: WEBLATE_SOCIAL_AUTH_GOOGLE_OAUTH2_KEY
.. envvar:: WEBLATE_SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET

    Enables :ref:`google_auth`.

GitLab
++++++

.. envvar:: WEBLATE_SOCIAL_AUTH_GITLAB_KEY
.. envvar:: WEBLATE_SOCIAL_AUTH_GITLAB_SECRET
.. envvar:: WEBLATE_SOCIAL_AUTH_GITLAB_API_URL

    Enables :ref:`gitlab_auth`.

Azure Active Directory
++++++++++++++++++++++

.. envvar:: WEBLATE_SOCIAL_AUTH_AZUREAD_OAUTH2_KEY
.. envvar:: WEBLATE_SOCIAL_AUTH_AZUREAD_OAUTH2_SECRET

    Enables Azure Active Directory authentication, see :doc:`psa:backends/azuread`.

Azure Active Directory with Tenant support
++++++++++++++++++++++++++++++++++++++++++

.. envvar:: WEBLATE_SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_KEY
.. envvar:: WEBLATE_SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_SECRET
.. envvar:: WEBLATE_SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_TENANT_ID

    Enables Azure Active Directory authentication with Tenant support, see
    :doc:`psa:backends/azuread`.

Other authentication settings
+++++++++++++++++++++++++++++

.. envvar:: WEBLATE_NO_EMAIL_AUTH

    Disables email authentication when set to any value.


PostgreSQL database setup
~~~~~~~~~~~~~~~~~~~~~~~~~

The database is created by :file:`docker-compose.yml`, so these settings affect
both Weblate and PostgreSQL containers.

.. seealso:: :ref:`database-setup`

.. envvar:: POSTGRES_PASSWORD

    PostgreSQL password.

.. envvar:: POSTGRES_USER

    PostgreSQL username.

.. envvar:: POSTGRES_DATABASE

    PostgreSQL database name.

.. envvar:: POSTGRES_HOST

    PostgreSQL server hostname or IP address. Defaults to ``database``.

.. envvar:: POSTGRES_PORT

    PostgreSQL server port. Defaults to none (uses the default value).

.. envvar:: POSTGRES_SSL_MODE

   Configure how PostgreSQL handles SSL in connection to the server, for possible choices see
   `SSL Mode Descriptions <https://www.postgresql.org/docs/11/libpq-ssl.html#LIBPQ-SSL-SSLMODE-STATEMENTS>`_


Caching server setup
~~~~~~~~~~~~~~~~~~~~

Using Redis is strongly recommended by Weblate and you have to provide a Redis
instance when running Weblate in Docker.

.. seealso:: :ref:`production-cache`

.. envvar:: REDIS_HOST

   The Redis server hostname or IP address. Defaults to ``cache``.

.. envvar:: REDIS_PORT

    The Redis server port. Defaults to ``6379``.

.. envvar:: REDIS_DB

    The Redis database number, defaults to ``1``.

.. envvar:: REDIS_PASSWORD
   
    The Redis server password, not used by default.

Email server setup
~~~~~~~~~~~~~~~~~~

To make outgoing email work, you need to provide a mail server.

.. seealso:: :ref:`out-mail`

.. envvar:: WEBLATE_EMAIL_HOST

    Mail server, the server has to listen on port 587 and understand TLS.

    .. seealso:: :setting:`django:EMAIL_HOST`

.. envvar:: WEBLATE_EMAIL_PORT

    Mail server port. Use if your cloud provider or ISP blocks outgoing
    connections on port 587.

    .. seealso:: :setting:`django:EMAIL_PORT`

.. envvar:: WEBLATE_EMAIL_HOST_USER

    Email authentication user, do NOT use quotes here.

    .. seealso:: :setting:`django:EMAIL_HOST_USER`

.. envvar:: WEBLATE_EMAIL_HOST_PASSWORD

    Email authentication password, do NOT use quotes here.

    .. seealso:: :setting:`django:EMAIL_HOST_PASSWORD`

.. envvar:: WEBLATE_EMAIL_USE_SSL

    Whether to use an implicit TLS (secure) connection when talking to the SMTP
    server. In most email documentation, this type of TLS connection is referred
    to as SSL. It is generally used on port 465. If you are experiencing
    problems, see the explicit TLS setting :envvar:`WEBLATE_EMAIL_USE_TLS`.

    .. seealso:: :setting:`django:EMAIL_USE_SSL`

.. envvar:: WEBLATE_EMAIL_USE_TLS

    Whether to use a TLS (secure) connection when talking to the SMTP server.
    This is used for explicit TLS connections, generally on port 587. If you
    are experiencing connections that hang, see the implicit TLS setting
    :envvar:`WEBLATE_EMAIL_USE_SSL`.

    .. seealso:: :setting:`django:EMAIL_USE_TLS`

Error reporting
~~~~~~~~~~~~~~~

It is recommended to collect errors from the installation in a systematic way,
see :ref:`collecting-errors`.

To enable support for Rollbar, set the following:

.. envvar:: ROLLBAR_KEY

    Your Rollbar post server access token.

.. envvar:: ROLLBAR_ENVIRONMENT

    Your Rollbar environment, defaults to ``production``.

To enable support for Sentry, set following:

.. envvar:: SENTRY_DSN

    Your Sentry DSN.

.. envvar:: SENTRY_PUBLIC_DSN

    Your Sentry public DSN.

.. envvar:: SENTRY_ENVIRONMENT

    Your Sentry environment, defaults to ``production``.

Further configuration customization
+++++++++++++++++++++++++++++++++++

You can additionally override the configuration in
:file:`/app/data/settings-override.py`. This is executed after all environment
settings are loaded, so it gets completely set up, and can be used to customize
anything.

Hub setup
+++++++++

In order to use the GitHub's pull-request feature, you must initialize hub configuration by entering the Weblate container and executing an arbitrary Hub command. For example:

.. code-block:: sh

    docker-compose exec --user weblate weblate bash
    cd
    HOME=/app/data/home hub clone octocat/Spoon-Knife

The username passed for credentials must be the same as :setting:`GITHUB_USERNAME`.

.. seealso::

    :ref:`github-push`,
    :ref:`hub-setup`

Select your machine - local or cloud providers
++++++++++++++++++++++++++++++++++++++++++++++

With docker-machine you can create your Weblate deployment either on your local
machine, or on any large number of cloud-based deployments on e.g. Amazon AWS,
Greenhost, and many other providers.

.. _openshift:

Running Weblate on OpenShift 2
------------------------------

This repository contains a configuration for the OpenShift platform as a
service product, which facilitates easy installation of Weblate on OpenShift
variants (see https://www.openshift.com/ and https://www.okd.io/).

Prerequisites
+++++++++++++

1. OpenShift Account

   You need an account on OpenShift Online (https://www.openshift.com/) or
   another OpenShift installation you have access to.

   You can register a gratis account on OpenShift Online, which allows you to
   host up to 3 programs gratis.

2. OpenShift Client Tools

   In order to follow the examples given in this documentation, you need to have
   the OpenShift Client Tools (RHC) installed:
   https://docs.openshift.com/online/cli_reference/get_started_cli.html

   While there are other possibilities to create and configure OpenShift
   programs, this documentation is based on the OpenShift Client Tools
   (RHC) because they provide a consistent interface for all described
   operations.

Installation
++++++++++++

You can install Weblate on OpenShift directly from Weblate's GitHub repository
with the following command:

.. code-block:: sh

    # Install Git HEAD
    rhc -aweblate app create -t python-2.7 --from-code https://github.com/WeblateOrg/weblate.git --no-git

    # Install Weblate 2.10
    rhc -aweblate app create -t python-2.7 --from-code https://github.com/WeblateOrg/weblate.git#weblate-3.5.1 --no-git

The ``-a`` option defines the name of your weblate installation, ``weblate`` in
this instance. Feel free to specify a different name.

The above example installs the latest development version, you can optionally
specify tag identifier to the right of the ``#`` sign to identify the version of
Weblate to install. A list of available versions is available here:
https://github.com/WeblateOrg/weblate/tags.

The ``--no-git`` option skips the creation of a
local Git repository.

You can also specify which database you want to use:

.. code-block:: sh

    # For MySQL
    rhc -aweblate app create -t python-2.7 -t mysql-5.5 --from-code https://github.com/WeblateOrg/weblate.git --no-git

    # For PostgreSQL
    rhc -aweblate app create -t python-2.7 -t postgresql-9.2 --from-code https://github.com/WeblateOrg/weblate.git --no-git

Default Configuration
+++++++++++++++++++++

After installation on OpenShift, Weblate is ready for use and, preconfigured as follows:

* SQLite embedded database (:setting:`DATABASES`)
* Random admin password
* Random Django secret key (:setting:`SECRET_KEY`)
* Committing of pending changes if the Cron cartridge is installed (:djadmin:`commit_pending`)
* Weblate machine translations for suggestions, based on previous translations (:setting:`MT_SERVICES`)
* Weblate directories (STATIC_ROOT, :setting:`DATA_DIR`, :setting:`TTF_PATH`, avatar cache) set according to OpenShift requirements/conventions.
* Django sitename and ALLOWED_HOSTS set to DNS name of your OpenShift program
* Email sender addresses set to no-reply@<OPENSHIFT_CLOUD_DOMAIN>, where <OPENSHIFT_CLOUD_DOMAIN> is the domain OpenShift runs under. In case of OpenShift Online it is rhcloud.com.

.. seealso::

   :ref:`customize_config`

Retrieve the Admin Password
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Retrieve the generated admin password using the following command:

.. code-block:: sh

    rhc -aweblate ssh credentials

Pending Changes
~~~~~~~~~~~~~~~

Weblate's OpenShift configuration contains a Cron job which periodically commits pending changes older than a certain age (24h by default).
To enable the Cron job you need to add the Cron cartridge and restart Weblate as described in the previous section.
You can change the age parameter by setting the environment variable WEBLATE_PENDING_AGE
to the desired number of hours, e.g.:

.. code-block:: sh

    rhc -aweblate env set WEBLATE_PENDING_AGE=48

.. _customize_config:

Customize the Weblate Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Customize the configuration of your Weblate installation on OpenShift
through the use of environment variables. Override any of Weblate's settings documented
under :ref:`config` using ``rhc env set`` by prepending the settings name with
``WEBLATE_``. The variable content is put into the configuration file verbatim,
so it is parsed as a Python string, after replacing the environment variables in it
(e.g. ``$PATH``). To put in a literal ``$`` you need to escape it as ``$$``.

For example override the :setting:`ADMINS` setting like this:

.. code-block:: sh

    rhc -aweblate env set WEBLATE_ADMINS='(("John Doe", "john@example.org"),)'

To change the sitetitle, do not forget to include additional quotes:

.. code-block:: sh

    rhc -aweblate env set WEBLATE_SITE_TITLE='"Custom Title"'

The new settings will only take effect once Weblate is restarted:

.. code-block:: sh

    rhc -aweblate app stop
    rhc -aweblate app start

Restarting using ``rhc -aweblate app restart`` does not work.
For security reasons only constant expressions are allowed as values.
With the exception of environment variables, which can be referenced using ``${ENV_VAR}``. For example:

.. code-block:: sh

    rhc -aweblate env set WEBLATE_SCRIPTS='("${OPENSHIFT_DATA_DIR}/examples/hook-unwrap-po",)'

You can check the effective settings Weblate is using by running:

.. code-block:: sh

    rhc -aweblate ssh settings

This will also print syntax errors in your expressions.
To reset a setting to its preconfigured value, just delete the corresponding environment variable:

.. code-block:: sh

   rhc -aweblate env unset WEBLATE_ADMINS

.. seealso::

   :ref:`config`

Updating
++++++++

It is recommended that you try updates on a clone of your Weblate installation before running the actual update.
To create such a clone, run:

.. code-block:: sh

    rhc -aweblate2 app create --from-app weblate

Visit the newly given URL with a web browser and wait for the install/update page to disappear.

You can update your Weblate installation on OpenShift directly from Weblate's GitHub repository by executing:

.. code-block:: sh

    rhc -aweblate2 ssh update https://github.com/WeblateOrg/weblate.git

The identifier to the right of the ``#`` sign identifies the version of Weblate to install.
For a list of available versions see: https://github.com/WeblateOrg/weblate/tags.
Please note that the update process will not work if you modified the Git repository of you Weblate installation.
You can force an update by specifying the ``--force`` option with the update script. However any changes you made to the
Git repository of your installation will be discarded:

.. code-block:: sh

   rhc -aweblate2 ssh update --force https://github.com/WeblateOrg/weblate.git

The ``--force`` option is also needed when downgrading to an older version.
Please note that only version 2.0 and newer can be installed on OpenShift,
as older versions don't include the necessary configuration files.

The update script takes care of the following update steps, as described in :ref:`generic-upgrade-instructions`.

* Install any new requirements
* manage.py migrate
* manage.py setupgroups --move
* manage.py setuplang
* manage.py rebuild_index --all
* manage.py collectstatic --noinput


Bitnami Weblate stack
---------------------

Bitnami provides a Weblate stack for many platforms at
<https://bitnami.com/stack/weblate>. The setup will be adjusted during
installation, see <https://bitnami.com/stack/weblate/README.txt> for more
documentation.

Weblate in YunoHost
-------------------

The self-hosting project `YunoHost <https://yunohost.org/>`_ provides a package
for Weblate. Once you have your YunoHost installation, you may install Weblate
as any other application. It will provide you with a fully working stack with backup
and restoration, but you may still have to edit your settings file for specific
usages.

You may use your administration interface, or this button (it will bring you to your server):

.. image:: /images/install-with-yunohost.png
             :alt: Install Weblate with YunoHost
             :target: https://install-app.yunohost.org/?app=weblate

It also is possible to use the commandline interface:

.. code-block:: sh

    yunohost app install https://github.com/YunoHost-Apps/weblate_ynh
