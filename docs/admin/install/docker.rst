Installing using Docker
=======================

With dockerized Weblate deployment you can get your personal Weblate instance
up and running in seconds. All of Weblate's dependencies are already included.
PostgreSQL is set up as the default database.

.. include:: steps/hw.rst

.. _docker-deploy:

Installation
------------

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
            ports:
              - 80:8080
            environment:
              WEBLATE_EMAIL_HOST: smtp.example.com
              WEBLATE_EMAIL_HOST_USER: user
              WEBLATE_EMAIL_HOST_PASSWORD: pass
              WEBLATE_SERVER_EMAIL: weblate@example.com
              WEBLATE_DEFAULT_FROM_EMAIL: weblate@example.com
              WEBLATE_SITE_DOMAIN: weblate.example.com
              WEBLATE_ADMIN_PASSWORD: password for the admin user
              WEBLATE_ADMIN_EMAIL: weblate.admin@example.com

   .. note::

        If :envvar:`WEBLATE_ADMIN_PASSWORD` is not set, the admin user is created with
        a random password shown on first startup.

        The provided example makes Weblate listen on port 80, edit the port
        mapping in the :file:`docker-compose.override.yml` file to change it.

3. Start Weblate containers:

   .. code-block:: sh

        docker-compose up

Enjoy your Weblate deployment, it's accessible on port 80 of the ``weblate`` container.

.. versionchanged:: 2.15-2

    The setup has changed recently, priorly there was separate web server
    container, since 2.15-2 the web server is embedded in the Weblate
    container.

.. versionchanged:: 3.7.1-6

   In July 2019 (starting with the 3.7.1-6 tag), the containers are not running
   as a root user. This has changed the exposed port from 80 to 8080.

.. seealso:: :ref:`invoke-manage`

Choosing Docker hub tag
-----------------------

You can use following tags on Docker hub, see https://hub.docker.com/r/weblate/weblate/tags/ for full list of available ones.

+-------------------------+------------------------------------------------------------------------------------------------------------+------------------------------------------------------+
| Tag name                | Description                                                                                                | Use case                                             |
+=========================+============================================================================================================+======================================================+
|``latest``               | Weblate stable release, matches latest tagged release                                                      | Rolling updates in a production environment          |
+-------------------------+------------------------------------------------------------------------------------------------------------+------------------------------------------------------+
|``<VERSION>-<PATCH>``    | Weblate stable release                                                                                     | Well defined deploy in a production environment      |
+-------------------------+------------------------------------------------------------------------------------------------------------+------------------------------------------------------+
|``edge``                 | Weblate stable release with development changes in the Docker container (for example updated dependencies) | Rolling updates in a staging environment             |
+-------------------------+------------------------------------------------------------------------------------------------------------+------------------------------------------------------+
|``edge-<DATE>-<SHA>``    | Weblate stable release with development changes in the Docker container (for example updated dependencies) | Well defined deploy in a staging environment         |
+-------------------------+------------------------------------------------------------------------------------------------------------+------------------------------------------------------+
|``bleeding``             | Development version Weblate from Git                                                                       | Rollling updates to test upcoming Weblate features   |
+-------------------------+------------------------------------------------------------------------------------------------------------+------------------------------------------------------+
|``bleeding-<DATE>-<SHA>``| Development version Weblate from Git                                                                       | Well defined deploy to test upcoming Weblate features|
+-------------------------+------------------------------------------------------------------------------------------------------------+------------------------------------------------------+

Every image is tested by our CI before it gets published, so even the `bleeding` version should be quite safe to use.

.. _docker-ssl:

Docker container with HTTPS support
-----------------------------------

Please see :ref:`docker-deploy` for generic deployment instructions, this
section only mentions differences compared to it.

Using own SSL certificates
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. versionadded:: 3.8-3

In case you have own SSL certificate you want to use, simply place the files
into the Weblate data volume (see :ref:`docker-volume`):

* :file:`ssl/fullchain.pem` containing the certificate including any needed CA certificates
* :file:`ssl/privkey.pem` containing the private key

Both of these files must be owned by the same user as the one starting the docker container and have file mask set to ``600`` (readable and writable only by the owning user).

Additionally, Weblate container will now accept SSL connections on port 4443,
you will want to include the port forwarding for HTTPS in docker compose override:

.. code-block:: yaml

     version: '3'
     services:
       weblate:
         ports:
           - 80:8080
           - 443:4443

If you already host other sites on the same server, it is likely ports ``80`` and ``443`` are used by a reverse proxy, such as NGINX. To pass the HTTPS connection from NGINX to the docker container, you can use the following configuration:

.. code-block:: nginx

    server {
        listen 443;
        listen [::]:443;

        server_name <SITE_URL>;
        ssl_certificate /etc/letsencrypt/live/<SITE>/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/<SITE>/privkey.pem;

        location / {
                proxy_set_header HOST $host;
                proxy_set_header X-Forwarded-Proto https;
                proxy_set_header X-Real-IP $remote_addr;
                proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                proxy_set_header X-Forwarded-Host $server_name;
                proxy_pass https://127.0.0.1:<EXPOSED_DOCKER_PORT>;
        }
    }

Replace ``<SITE_URL>``, ``<SITE>`` and ``<EXPOSED_DOCKER_PORT>`` with actual values from your environment.

Automatic SSL certificates using Let’s Encrypt
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In case you want to use `Let’s Encrypt <https://letsencrypt.org/>`_
automatically generated SSL certificates on public installation, you need to
add a reverse HTTPS proxy an additional Docker container, `https-portal
<https://hub.docker.com/r/steveltn/https-portal/>`_ will be used for that.
This is made use of in the :file:`docker-compose-https.yml` file.  Then create
a :file:`docker-compose-https.override.yml` file with your settings:

.. code-block:: yaml

    version: '3'
    services:
      weblate:
        environment:
          WEBLATE_EMAIL_HOST: smtp.example.com
          WEBLATE_EMAIL_HOST_USER: user
          WEBLATE_EMAIL_HOST_PASSWORD: pass
          WEBLATE_SITE_DOMAIN: weblate.example.com
          WEBLATE_ADMIN_PASSWORD: password for admin user
      https-portal:
        environment:
          DOMAINS: 'weblate.example.com -> http://weblate:8080'

Whenever invoking :program:`docker-compose` you need to pass both files to it,
and then do:

.. code-block:: console

    docker-compose -f docker-compose-https.yml -f docker-compose-https.override.yml build
    docker-compose -f docker-compose-https.yml -f docker-compose-https.override.yml up

.. _upgrading-docker:

Upgrading the Docker container
------------------------------

Usually it is good idea to only update the Weblate container and keep the PostgreSQL
container at the version you have, as upgrading PostgreSQL is quite painful and in most
cases does not bring many benefits.

.. versionchanged:: 4.10-1

   Since Weblate 4.10-1, the Docker container uses Django 4.0 what requires
   PostgreSQL 10 or newer, please upgrade it prior to upgrading Weblate.
   See :ref:`upgrade-4.10` and :ref:`docker-postgres-upgrade`.

You can do this by sticking with the existing docker-compose and just pull
the latest images and then restart:

.. code-block:: sh

   # Fetch latest versions of the images
   docker-compose pull
   # Stop and destroy the containers
   docker-compose down
   # Spawn new containers in the background
   docker-compose up -d
   # Follow the logs during upgrade
   docker-compose logs -f

The Weblate database should be automatically migrated on first startup, and there
should be no need for additional manual actions.

.. note::

    Upgrades across major versions are not supported by Weblate. For example,
    if you are on 3.x series and want to upgrade to 4.x, first upgrade to the
    latest 4.0.x-y image (at time of writing this it is the ``4.0.4-5``), which
    will do the migration and then continue upgrading to newer versions.

You might also want to update the ``docker-compose`` repository, though it's
not needed in most case. See :ref:`docker-postgres-upgrade` for upgrading the PostgreSQL server.

.. _docker-postgres-upgrade:

Upgrading PostgreSQL container
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

PostgreSQL containers do not support automatic upgrading between version, you
need to perform the upgrade manually. Following steps show one of the options
of upgrading.

.. seealso::

   https://github.com/docker-library/postgres/issues/37

1. Stop Weblate container:

   .. code-block:: shell

      docker-compose stop weblate cache

2. Backup the database:

   .. code-block:: shell

      docker-compose exec database pg_dumpall --clean --username weblate > backup.sql

3. Stop the database container:

   .. code-block:: shell

      docker-compose stop database

4. Remove the PostgreSQL volume:

   .. code-block:: shell

      docker-compose rm -v database
      docker volume remove weblate_postgres-data

5. Adjust :file:`docker-compose.yml` to use new PostgreSQL version.

6. Start the database container:

   .. code-block:: shell

      docker-compose up -d database

7. Restore the database from the backup:

   .. code-block:: shell

      cat backup.sql | docker-compose exec -T database psql --username weblate --dbname postgres

8. Start all remaining containers:

   .. code-block:: shell

      docker-compose up -d

.. _docker-admin-login:

Admin sign in
-------------

After container setup, you can sign in as `admin` user with password provided
in :envvar:`WEBLATE_ADMIN_PASSWORD`, or a random password generated on first
start if that was not set.

To reset `admin` password, restart the container with
:envvar:`WEBLATE_ADMIN_PASSWORD` set to new password.

.. seealso::

        :envvar:`WEBLATE_ADMIN_PASSWORD`,
        :envvar:`WEBLATE_ADMIN_NAME`,
        :envvar:`WEBLATE_ADMIN_EMAIL`

Number of processes and memory consumption
------------------------------------------

The number of worker processes for both uWSGI and Celery is determined
automatically based on number of CPUs. This works well for most cloud virtual
machines as these typically have few CPUs and good amount of memory.

In case you have a lot of CPU cores and hit out of memory issues, try reducing
number of workers:

.. code-block:: yaml

    environment:
      WEBLATE_WORKERS: 2

You can also fine-tune individual worker categories:

.. code-block:: yaml

    environment:
      WEB_WORKERS: 4
      CELERY_MAIN_OPTIONS: --concurrency 2
      CELERY_NOTIFY_OPTIONS: --concurrency 1
      CELERY_TRANSLATE_OPTIONS: --concurrency 1

.. seealso::

   :envvar:`WEBLATE_WORKERS`
   :envvar:`CELERY_MAIN_OPTIONS`,
   :envvar:`CELERY_NOTIFY_OPTIONS`,
   :envvar:`CELERY_MEMORY_OPTIONS`,
   :envvar:`CELERY_TRANSLATE_OPTIONS`,
   :envvar:`CELERY_BACKUP_OPTIONS`,
   :envvar:`CELERY_BEAT_OPTIONS`,
   :envvar:`WEB_WORKERS`

.. _docker-scaling:

Scaling horizontally
--------------------

.. versionadded:: 4.6

You can run multiple Weblate containers to scale the service horizontally. The
:file:`/app/data` volume has to be shared by all containers, it is recommended
to use cluster filesystem such as GlusterFS for this. The :file:`/app/cache`
volume should be separate for each container.

Each Weblate container has defined role using :envvar:`WEBLATE_SERVICE`
environment variable. Please follow carefully the documentation as some of the
services should be running just once in the cluster and the ordering of the
services matters as well.

You can find example setup in the ``docker-compose`` repo as
`docker-compose-split.yml
<https://github.com/WeblateOrg/docker-compose/blob/main/docker-compose-split.yml>`__.

.. _docker-environment:

Docker environment variables
----------------------------

Many of Weblate's :ref:`config` can be set in the Docker container using environment variables:

Generic settings
~~~~~~~~~~~~~~~~

.. envvar:: WEBLATE_DEBUG

    Configures Django debug mode using :setting:`DEBUG`.

    **Example:**

    .. code-block:: yaml

        environment:
          WEBLATE_DEBUG: 1

    .. seealso::

            :ref:`production-debug`

.. envvar:: WEBLATE_LOGLEVEL

    Configures the logging verbosity.

.. envvar:: WEBLATE_LOGLEVEL_DATABASE

    Configures the logging of the database queries verbosity.

.. envvar:: WEBLATE_SITE_TITLE

    Changes the site-title shown in the header of all pages.

.. envvar:: WEBLATE_SITE_DOMAIN

    Configures the site domain. This parameter is required.

    .. seealso::

        :ref:`production-site`,
        :setting:`SITE_DOMAIN`

.. envvar:: WEBLATE_ADMIN_NAME
.. envvar:: WEBLATE_ADMIN_EMAIL

    Configures the site-admin's name and e-mail. It is used for both
    :setting:`ADMINS` setting and creating `admin` user (see
    :envvar:`WEBLATE_ADMIN_PASSWORD` for more info on that).

    **Example:**

    .. code-block:: yaml

        environment:
          WEBLATE_ADMIN_NAME: Weblate admin
          WEBLATE_ADMIN_EMAIL: noreply@example.com

    .. seealso::

            :ref:`docker-admin-login`,
            :ref:`production-admins`,
            :setting:`ADMINS`

.. envvar:: WEBLATE_ADMIN_PASSWORD

    Sets the password for the `admin` user.

    * If not set and `admin` user does not exist, it is created with a random
      password shown on first container startup.
    * If not set and `admin` user exists, no action is performed.
    * If set the `admin` user is adjusted on every container startup to match
      :envvar:`WEBLATE_ADMIN_PASSWORD`, :envvar:`WEBLATE_ADMIN_NAME` and
      :envvar:`WEBLATE_ADMIN_EMAIL`.

    .. warning::

        It might be a security risk to store password in the configuration
        file. Consider using this variable only for initial setup (or let
        Weblate generate random password on initial startup) or for password
        recovery.

    .. seealso::

            :ref:`docker-admin-login`,
            :envvar:`WEBLATE_ADMIN_PASSWORD`,
            :envvar:`WEBLATE_ADMIN_PASSWORD_FILE`,
            :envvar:`WEBLATE_ADMIN_NAME`,
            :envvar:`WEBLATE_ADMIN_EMAIL`

.. envvar:: WEBLATE_ADMIN_PASSWORD_FILE

    Sets the path to a file containing the password for the `admin` user.

    .. seealso::

            :envvar:`WEBLATE_ADMIN_PASSWORD`

.. envvar:: WEBLATE_SERVER_EMAIL

    The email address that error messages are sent from.

    .. seealso::

        :std:setting:`django:SERVER_EMAIL`,
        :ref:`production-email`

.. envvar:: WEBLATE_DEFAULT_FROM_EMAIL

    Configures the address for outgoing e-mails.

    .. seealso::

        :std:setting:`django:DEFAULT_FROM_EMAIL`,
        :ref:`production-email`

.. envvar:: WEBLATE_CONTACT_FORM

     Configures contact form behavior, see :setting:`CONTACT_FORM`.

.. envvar:: WEBLATE_ALLOWED_HOSTS

    Configures allowed HTTP hostnames using :setting:`ALLOWED_HOSTS`.

    Defaults to ``*`` which allows all hostnames.

    **Example:**

    .. code-block:: yaml

        environment:
          WEBLATE_ALLOWED_HOSTS: weblate.example.com,example.com

    .. seealso::

        :setting:`ALLOWED_HOSTS`,
        :ref:`production-hosts`,
        :ref:`production-site`

.. envvar:: WEBLATE_REGISTRATION_OPEN

    Configures whether registrations are open by toggling :std:setting:`REGISTRATION_OPEN`.

    **Example:**

    .. code-block:: yaml

        environment:
          WEBLATE_REGISTRATION_OPEN: 0

.. envvar:: WEBLATE_REGISTRATION_ALLOW_BACKENDS

   Configure which authentication methods can be used to create new account via
   :setting:`REGISTRATION_ALLOW_BACKENDS`.

    **Example:**

    .. code-block:: yaml

        environment:
          WEBLATE_REGISTRATION_OPEN: 0
          WEBLATE_REGISTRATION_ALLOW_BACKENDS: azuread-oauth2,azuread-tenant-oauth2

.. envvar:: WEBLATE_TIME_ZONE

    Configures the used time zone in Weblate, see :std:setting:`django:TIME_ZONE`.

    .. note::

       To change the time zone of the Docker container itself, use the ``TZ``
       environment variable.

    **Example:**

    .. code-block:: yaml

        environment:
          WEBLATE_TIME_ZONE: Europe/Prague

.. envvar:: WEBLATE_ENABLE_HTTPS

    Makes Weblate assume it is operated behind a reverse HTTPS proxy, it makes
    Weblate use HTTPS in e-mail and API links or set secure flags on cookies.

    .. hint::

        Please see :setting:`ENABLE_HTTPS` documentation for possible caveats.

    .. note::

        This does not make the Weblate container accept HTTPS connections, you
        need to configure that as well, see :ref:`docker-ssl` for examples.

    **Example:**

    .. code-block:: yaml

        environment:
          WEBLATE_ENABLE_HTTPS: 1

    .. seealso::

      :setting:`ENABLE_HTTPS`
      :ref:`production-site`,
      :envvar:`WEBLATE_SECURE_PROXY_SSL_HEADER`

.. envvar:: WEBLATE_INTERLEDGER_PAYMENT_POINTERS

    .. versionadded:: 4.12.1

    Lets Weblate set the `meta[name=monetization]` field in the head of the
    document. If multiple are specified, chooses one randomly.

    .. seealso::

        :setting:`INTERLEDGER_PAYMENT_POINTERS`

.. envvar:: WEBLATE_IP_PROXY_HEADER

    Lets Weblate fetch the IP address from any given HTTP header. Use this when using
    a reverse proxy in front of the Weblate container.

    Enables :setting:`IP_BEHIND_REVERSE_PROXY` and sets :setting:`IP_PROXY_HEADER`.

    .. note::

        The format must conform to Django's expectations. Django
        `transforms <https://docs.djangoproject.com/en/2.2/ref/request-response/#django.http.HttpRequest.META>`_
        raw HTTP header names as follows:

        - converts all characters to uppercase
        - replaces any hyphens with underscores
        - prepends ``HTTP_`` prefix

        So ``X-Forwarded-For`` would be mapped to ``HTTP_X_FORWARDED_FOR``.

    **Example:**

    .. code-block:: yaml

        environment:
          WEBLATE_IP_PROXY_HEADER: HTTP_X_FORWARDED_FOR


.. envvar:: WEBLATE_SECURE_PROXY_SSL_HEADER

    A tuple representing a HTTP header/value combination that signifies a
    request is secure. This is needed when Weblate is running behind a reverse
    proxy doing SSL termination which does not pass standard HTTPS headers.

    **Example:**

    .. code-block:: yaml

        environment:
          WEBLATE_SECURE_PROXY_SSL_HEADER: HTTP_X_FORWARDED_PROTO,https

    .. seealso::

        :setting:`django:SECURE_PROXY_SSL_HEADER`

.. envvar:: WEBLATE_REQUIRE_LOGIN

    Enables :setting:`REQUIRE_LOGIN` to enforce authentication on whole Weblate.

    **Example:**

    .. code-block:: yaml

        environment:
          WEBLATE_REQUIRE_LOGIN: 1

.. envvar:: WEBLATE_LOGIN_REQUIRED_URLS_EXCEPTIONS
.. envvar:: WEBLATE_ADD_LOGIN_REQUIRED_URLS_EXCEPTIONS
.. envvar:: WEBLATE_REMOVE_LOGIN_REQUIRED_URLS_EXCEPTIONS

    Adds URL exceptions for authentication required for the whole Weblate
    installation using :setting:`LOGIN_REQUIRED_URLS_EXCEPTIONS`.

    You can either replace whole settings, or modify default value using ``ADD`` and ``REMOVE`` variables.

.. envvar:: WEBLATE_GOOGLE_ANALYTICS_ID

    Configures ID for Google Analytics by changing :setting:`GOOGLE_ANALYTICS_ID`.

.. envvar:: WEBLATE_GITHUB_USERNAME

    Configures GitHub username for GitHub pull-requests by changing
    :setting:`GITHUB_USERNAME`.

    .. seealso::

       :ref:`vcs-github`

.. envvar:: WEBLATE_GITHUB_TOKEN

    .. versionadded:: 4.3

    Configures GitHub personal access token for GitHub pull-requests via API by changing
    :setting:`GITHUB_TOKEN`.

    .. seealso::

       :ref:`vcs-github`

.. envvar:: WEBLATE_GITLAB_USERNAME

    Configures GitLab username for GitLab merge-requests by changing
    :setting:`GITLAB_USERNAME`

    .. seealso::

       :ref:`vcs-gitlab`

.. envvar:: WEBLATE_GITLAB_TOKEN

    Configures GitLab personal access token for GitLab merge-requests via API by changing
    :setting:`GITLAB_TOKEN`

    .. seealso::

       :ref:`vcs-gitlab`

.. envvar:: WEBLATE_PAGURE_USERNAME

    Configures Pagure username for Pagure merge-requests by changing
    :setting:`PAGURE_USERNAME`

    .. seealso::

       :ref:`vcs-pagure`

.. envvar:: WEBLATE_PAGURE_TOKEN

    Configures Pagure personal access token for Pagure merge-requests via API by changing
    :setting:`PAGURE_TOKEN`

    .. seealso::

       :ref:`vcs-pagure`

.. envvar:: WEBLATE_DEFAULT_PULL_MESSAGE

    Configures the default title and message for pull requests via API by changing
    :setting:`DEFAULT_PULL_MESSAGE`

    .. seealso::

       :ref:`config-pull-message`

.. envvar:: WEBLATE_SIMPLIFY_LANGUAGES

    Configures the language simplification policy, see :setting:`SIMPLIFY_LANGUAGES`.

.. envvar:: WEBLATE_DEFAULT_ACCESS_CONTROL

    Configures the default :ref:`project-access_control` for new projects, see :setting:`DEFAULT_ACCESS_CONTROL`.

.. envvar:: WEBLATE_DEFAULT_RESTRICTED_COMPONENT

    Configures the default value for :ref:`component-restricted` for new components, see :setting:`DEFAULT_RESTRICTED_COMPONENT`.

.. envvar:: WEBLATE_DEFAULT_TRANSLATION_PROPAGATION

    Configures the default value for :ref:`component-allow_translation_propagation` for new components, see :setting:`DEFAULT_TRANSLATION_PROPAGATION`.

.. envvar:: WEBLATE_DEFAULT_COMMITER_EMAIL

    Configures :setting:`DEFAULT_COMMITER_EMAIL`.

.. envvar:: WEBLATE_DEFAULT_COMMITER_NAME

    Configures :setting:`DEFAULT_COMMITER_NAME`.

.. envvar::  WEBLATE_DEFAULT_SHARED_TM

   Configures :setting:`DEFAULT_SHARED_TM`.

.. envvar:: WEBLATE_AKISMET_API_KEY

    Configures the Akismet API key, see :setting:`AKISMET_API_KEY`.

.. envvar:: WEBLATE_GPG_IDENTITY

   Configures GPG signing of commits, see :setting:`WEBLATE_GPG_IDENTITY`.

   .. seealso::

       :ref:`gpg-sign`

.. envvar:: WEBLATE_URL_PREFIX

   Configures URL prefix where Weblate is running, see :setting:`URL_PREFIX`.

.. envvar:: WEBLATE_SILENCED_SYSTEM_CHECKS

   Configures checks which you do not want to be displayed, see
   :setting:`django:SILENCED_SYSTEM_CHECKS`.

.. envvar:: WEBLATE_CSP_SCRIPT_SRC
.. envvar:: WEBLATE_CSP_IMG_SRC
.. envvar:: WEBLATE_CSP_CONNECT_SRC
.. envvar:: WEBLATE_CSP_STYLE_SRC
.. envvar:: WEBLATE_CSP_FONT_SRC

    Allows to customize ``Content-Security-Policy`` HTTP header.

    .. seealso::

        :ref:`csp`,
        :setting:`CSP_SCRIPT_SRC`,
        :setting:`CSP_IMG_SRC`,
        :setting:`CSP_CONNECT_SRC`,
        :setting:`CSP_STYLE_SRC`,
        :setting:`CSP_FONT_SRC`

.. envvar:: WEBLATE_LICENSE_FILTER

    Configures :setting:`LICENSE_FILTER`.

.. envvar:: WEBLATE_LICENSE_REQUIRED

   Configures :setting:`LICENSE_REQUIRED`

.. envvar:: WEBLATE_WEBSITE_REQUIRED

   Configures :setting:`WEBSITE_REQUIRED`

.. envvar:: WEBLATE_HIDE_VERSION

    Configures :setting:`HIDE_VERSION`.

.. envvar:: WEBLATE_BASIC_LANGUAGES

    Configures :setting:`BASIC_LANGUAGES`.

.. envvar:: WEBLATE_DEFAULT_AUTO_WATCH

   Configures :setting:`DEFAULT_AUTO_WATCH`.

.. envvar:: WEBLATE_RATELIMIT_ATTEMPTS
.. envvar:: WEBLATE_RATELIMIT_LOCKOUT
.. envvar:: WEBLATE_RATELIMIT_WINDOW

   .. versionadded:: 4.6

   Configures rate limiter.

   .. hint::

      You can set configuration for any rate limiter scopes. To do that add ``WEBLATE_`` prefix to
      any of setting described in :ref:`rate-limit`.

   .. seealso::

      :ref:`rate-limit`,
      :setting:`RATELIMIT_ATTEMPTS`,
      :setting:`RATELIMIT_WINDOW`,
      :setting:`RATELIMIT_LOCKOUT`


.. envvar:: WEBLATE_API_RATELIMIT_ANON
.. envvar:: WEBLATE_API_RATELIMIT_USER

   .. versionadded:: 4.11

   Configures API rate limiting. Defaults to ``100/day`` for anonymous and
   ``5000/hour`` for authenticated users.

   .. seealso::

      :ref:`api-rate`

.. envvar:: WEBLATE_ENABLE_HOOKS

   .. versionadded:: 4.13

   Configures :setting:`ENABLE_HOOKS`.

.. envvar:: WEBLATE_ENABLE_AVATARS

   .. versionadded:: 4.6.1

   Configures :setting:`ENABLE_AVATARS`.

.. envvar:: WEBLATE_LIMIT_TRANSLATION_LENGTH_BY_SOURCE_LENGTH

   .. versionadded:: 4.9

   Configures :setting:`LIMIT_TRANSLATION_LENGTH_BY_SOURCE_LENGTH`.

.. envvar:: WEBLATE_SSH_EXTRA_ARGS

   .. versionadded:: 4.9

   Configures :setting:`SSH_EXTRA_ARGS`.

.. envvar:: WEBLATE_BORG_EXTRA_ARGS

   .. versionadded:: 4.9

   Configures :setting:`BORG_EXTRA_ARGS`.


.. _docker-machine:

Automatic suggestion settings
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. versionchanged:: 4.13

   Automatic suggestion services are now configured in the user interface,
   see :ref:`machine-translation-setup`.

   The existing environment variables are imported during the migration to
   Weblate 4.13, but changing them will not have any further effect.

.. _docker-auth:

Authentication settings
~~~~~~~~~~~~~~~~~~~~~~~

LDAP
++++

.. envvar:: WEBLATE_AUTH_LDAP_SERVER_URI
.. envvar:: WEBLATE_AUTH_LDAP_USER_DN_TEMPLATE
.. envvar:: WEBLATE_AUTH_LDAP_USER_ATTR_MAP
.. envvar:: WEBLATE_AUTH_LDAP_BIND_DN
.. envvar:: WEBLATE_AUTH_LDAP_BIND_PASSWORD
.. envvar:: WEBLATE_AUTH_LDAP_BIND_PASSWORD_FILE

    Path to the file containing the LDAP server bind password.

    .. seealso:: :envvar:`WEBLATE_AUTH_LDAP_BIND_PASSWORD`

.. envvar:: WEBLATE_AUTH_LDAP_CONNECTION_OPTION_REFERRALS
.. envvar:: WEBLATE_AUTH_LDAP_USER_SEARCH
.. envvar:: WEBLATE_AUTH_LDAP_USER_SEARCH_FILTER
.. envvar:: WEBLATE_AUTH_LDAP_USER_SEARCH_UNION
.. envvar:: WEBLATE_AUTH_LDAP_USER_SEARCH_UNION_DELIMITER

    LDAP authentication configuration.

    **Example for direct bind:**

    .. code-block:: yaml

        environment:
          WEBLATE_AUTH_LDAP_SERVER_URI: ldap://ldap.example.org
          WEBLATE_AUTH_LDAP_USER_DN_TEMPLATE: uid=%(user)s,ou=People,dc=example,dc=net
          # map weblate 'full_name' to ldap 'name' and weblate 'email' attribute to 'mail' ldap attribute.
          # another example that can be used with OpenLDAP: 'full_name:cn,email:mail'
          WEBLATE_AUTH_LDAP_USER_ATTR_MAP: full_name:name,email:mail

    **Example for search and bind:**

    .. code-block:: yaml

        environment:
          WEBLATE_AUTH_LDAP_SERVER_URI: ldap://ldap.example.org
          WEBLATE_AUTH_LDAP_BIND_DN: CN=ldap,CN=Users,DC=example,DC=com
          WEBLATE_AUTH_LDAP_BIND_PASSWORD: password
          WEBLATE_AUTH_LDAP_USER_ATTR_MAP: full_name:name,email:mail
          WEBLATE_AUTH_LDAP_USER_SEARCH: CN=Users,DC=example,DC=com


    **Example for union search and bind:**

    .. code-block:: yaml

        environment:
          WEBLATE_AUTH_LDAP_SERVER_URI: ldap://ldap.example.org
          WEBLATE_AUTH_LDAP_BIND_DN: CN=ldap,CN=Users,DC=example,DC=com
          WEBLATE_AUTH_LDAP_BIND_PASSWORD: password
          WEBLATE_AUTH_LDAP_USER_ATTR_MAP: full_name:name,email:mail
          WEBLATE_AUTH_LDAP_USER_SEARCH_UNION: ou=users,dc=example,dc=com|ou=otherusers,dc=example,dc=com


    **Example with search and bind against Active Directory:**

    .. code-block:: yaml

        environment:
          WEBLATE_AUTH_LDAP_BIND_DN: CN=ldap,CN=Users,DC=example,DC=com
          WEBLATE_AUTH_LDAP_BIND_PASSWORD: password
          WEBLATE_AUTH_LDAP_SERVER_URI: ldap://ldap.example.org
          WEBLATE_AUTH_LDAP_CONNECTION_OPTION_REFERRALS: 0
          WEBLATE_AUTH_LDAP_USER_ATTR_MAP: full_name:name,email:mail
          WEBLATE_AUTH_LDAP_USER_SEARCH: CN=Users,DC=example,DC=com
          WEBLATE_AUTH_LDAP_USER_SEARCH_FILTER: (sAMAccountName=%(user)s)

    .. seealso::

        :ref:`ldap-auth`

GitHub
++++++

.. envvar:: WEBLATE_SOCIAL_AUTH_GITHUB_KEY
.. envvar:: WEBLATE_SOCIAL_AUTH_GITHUB_SECRET
.. envvar:: WEBLATE_SOCIAL_AUTH_GITHUB_ORG_KEY
.. envvar:: WEBLATE_SOCIAL_AUTH_GITHUB_ORG_SECRET
.. envvar:: WEBLATE_SOCIAL_AUTH_GITHUB_ORG_NAME
.. envvar:: WEBLATE_SOCIAL_AUTH_GITHUB_TEAM_KEY
.. envvar:: WEBLATE_SOCIAL_AUTH_GITHUB_TEAM_SECRET
.. envvar:: WEBLATE_SOCIAL_AUTH_GITHUB_TEAM_ID

    Enables :ref:`github_auth`.

Bitbucket
+++++++++

.. envvar:: WEBLATE_SOCIAL_AUTH_BITBUCKET_OAUTH2_KEY
.. envvar:: WEBLATE_SOCIAL_AUTH_BITBUCKET_OAUTH2_SECRET
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
.. envvar:: WEBLATE_SOCIAL_AUTH_GOOGLE_OAUTH2_WHITELISTED_DOMAINS
.. envvar:: WEBLATE_SOCIAL_AUTH_GOOGLE_OAUTH2_WHITELISTED_EMAILS

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

    Enables Azure Active Directory authentication, see :ref:`azure-auth`.

Azure Active Directory with Tenant support
++++++++++++++++++++++++++++++++++++++++++

.. envvar:: WEBLATE_SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_KEY
.. envvar:: WEBLATE_SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_SECRET
.. envvar:: WEBLATE_SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_TENANT_ID

    Enables Azure Active Directory authentication with Tenant support, see
    :ref:`azure-auth`.

Keycloak
++++++++

.. envvar:: WEBLATE_SOCIAL_AUTH_KEYCLOAK_KEY
.. envvar:: WEBLATE_SOCIAL_AUTH_KEYCLOAK_SECRET
.. envvar:: WEBLATE_SOCIAL_AUTH_KEYCLOAK_PUBLIC_KEY
.. envvar:: WEBLATE_SOCIAL_AUTH_KEYCLOAK_ALGORITHM
.. envvar:: WEBLATE_SOCIAL_AUTH_KEYCLOAK_AUTHORIZATION_URL
.. envvar:: WEBLATE_SOCIAL_AUTH_KEYCLOAK_ACCESS_TOKEN_URL
.. envvar:: WEBLATE_SOCIAL_AUTH_KEYCLOAK_TITLE
.. envvar:: WEBLATE_SOCIAL_AUTH_KEYCLOAK_IMAGE

    Enables Keycloak authentication, see
    `documentation <https://github.com/python-social-auth/social-core/blob/master/social_core/backends/keycloak.py>`_.

Linux vendors
+++++++++++++

You can enable authentication using Linux vendors authentication services by
setting following variables to any value.

.. envvar:: WEBLATE_SOCIAL_AUTH_FEDORA
.. envvar:: WEBLATE_SOCIAL_AUTH_OPENSUSE
.. envvar:: WEBLATE_SOCIAL_AUTH_UBUNTU

Slack
+++++

.. envvar:: WEBLATE_SOCIAL_AUTH_SLACK_KEY
.. envvar:: SOCIAL_AUTH_SLACK_SECRET

    Enables Slack authentication, see :ref:`slack-auth`.


OpenID Connect
++++++++++++++

.. versionadded:: 4.13-1

.. envvar:: WEBLATE_SOCIAL_AUTH_OIDC_OIDC_ENDPOINT
.. envvar:: WEBLATE_SOCIAL_AUTH_OIDC_KEY
.. envvar:: WEBLATE_SOCIAL_AUTH_OIDC_SECRET
.. envvar:: WEBLATE_SOCIAL_AUTH_OIDC_USERNAME_KEY

   Configures generic OpenID Connect intergration.

   .. seealso::

      :doc:`psa:backends/oidc`

.. _docker-saml:

SAML
++++

Self-signed SAML keys are automatically generated on first container startup.
In case you want to use own keys, place the certificate and private key in
:file:`/app/data/ssl/saml.crt` and :file:`/app/data/ssl/saml.key`.

.. envvar:: WEBLATE_SAML_IDP_ENTITY_ID
.. envvar:: WEBLATE_SAML_IDP_URL
.. envvar:: WEBLATE_SAML_IDP_X509CERT
.. envvar:: WEBLATE_SAML_IDP_IMAGE
.. envvar:: WEBLATE_SAML_IDP_TITLE

    SAML Identity Provider settings, see :ref:`saml-auth`.


Other authentication settings
+++++++++++++++++++++++++++++

.. envvar:: WEBLATE_NO_EMAIL_AUTH

    Disables e-mail authentication when set to any value. See
    :ref:`disable-email-auth`.


PostgreSQL database setup
~~~~~~~~~~~~~~~~~~~~~~~~~

The database is created by :file:`docker-compose.yml`, so these settings affect
both Weblate and PostgreSQL containers.

.. seealso:: :ref:`database-setup`

.. envvar:: POSTGRES_PASSWORD

    PostgreSQL password.

.. envvar:: POSTGRES_PASSWORD_FILE

    Path to the file containing the PostgreSQL password. Use as an alternative to POSTGRES_PASSWORD.

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

.. envvar:: POSTGRES_ALTER_ROLE

    Configures name of role to alter during migrations, see :ref:`config-postgresql`.

.. envvar:: POSTGRES_CONN_MAX_AGE

   .. versionadded:: 4.8.1

   The lifetime of a database connection, as an integer of seconds. Use 0 to
   close database connections at the end of each request (this is the default
   behavior).

   Enabling connection persistence will typically, cause more open connection
   to the database. Please adjust your database configuration prior enabling.

   Example configuration:

   .. code-block:: yaml

       environment:
           POSTGRES_CONN_MAX_AGE: 3600

   .. seealso::

      :setting:`django:CONN_MAX_AGE`, :ref:`django:persistent-database-connections`

.. envvar:: POSTGRES_DISABLE_SERVER_SIDE_CURSORS

   .. versionadded:: 4.9.1

   Disable server side cursors in the database. This is necessary in some
   :command:`pgbouncer` setups.

   Example configuration:

   .. code-block:: yaml

       environment:
           POSTGRES_DISABLE_SERVER_SIDE_CURSORS: 1

   .. seealso::

      :setting:`DISABLE_SERVER_SIDE_CURSORS <django:DATABASE-DISABLE_SERVER_SIDE_CURSORS>`,
      :ref:`django:transaction-pooling-server-side-cursors`


Database backup settings
~~~~~~~~~~~~~~~~~~~~~~~~

.. seealso::
    :ref:`backup-dumps`

.. envvar:: WEBLATE_DATABASE_BACKUP

    Configures the daily database dump using :setting:`DATABASE_BACKUP`. Defaults to ``plain``.


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

.. envvar:: REDIS_PASSWORD_FILE

    Path to the file containing the Redis server password.

    .. seealso:: :envvar:`REDIS_PASSWORD`

.. envvar:: REDIS_TLS

    Enables using SSL for Redis connection.

.. envvar:: REDIS_VERIFY_SSL

    Can be used to disable SSL certificate verification for Redis connection.

.. _docker-mail:

Email server setup
~~~~~~~~~~~~~~~~~~

To make outgoing e-mail work, you need to provide a mail server.

Example TLS configuration:

.. code-block:: yaml

    environment:
        WEBLATE_EMAIL_HOST: smtp.example.com
        WEBLATE_EMAIL_HOST_USER: user
        WEBLATE_EMAIL_HOST_PASSWORD: pass

Example SSL configuration:

.. code-block:: yaml

    environment:
        WEBLATE_EMAIL_HOST: smtp.example.com
        WEBLATE_EMAIL_PORT: 465
        WEBLATE_EMAIL_HOST_USER: user
        WEBLATE_EMAIL_HOST_PASSWORD: pass
        WEBLATE_EMAIL_USE_TLS: 0
        WEBLATE_EMAIL_USE_SSL: 1


.. seealso:: :ref:`out-mail`

.. envvar:: WEBLATE_EMAIL_HOST

    Mail server hostname or IP address.

    .. seealso::

        :envvar:`WEBLATE_EMAIL_PORT`,
        :envvar:`WEBLATE_EMAIL_USE_SSL`,
        :envvar:`WEBLATE_EMAIL_USE_TLS`,
        :setting:`django:EMAIL_HOST`

.. envvar:: WEBLATE_EMAIL_PORT

    Mail server port, defaults to 25.

    .. seealso:: :setting:`django:EMAIL_PORT`

.. envvar:: WEBLATE_EMAIL_HOST_USER

    E-mail authentication user.

    .. seealso:: :setting:`django:EMAIL_HOST_USER`

.. envvar:: WEBLATE_EMAIL_HOST_PASSWORD

    E-mail authentication password.

    .. seealso:: :setting:`django:EMAIL_HOST_PASSWORD`

.. envvar:: WEBLATE_EMAIL_HOST_PASSWORD_FILE

    Path to the file containing the e-mail authentication password.

    .. seealso:: :envvar:`WEBLATE_EMAIL_HOST_PASSWORD`

.. envvar:: WEBLATE_EMAIL_USE_SSL

    Whether to use an implicit TLS (secure) connection when talking to the SMTP
    server. In most e-mail documentation, this type of TLS connection is referred
    to as SSL. It is generally used on port 465. If you are experiencing
    problems, see the explicit TLS setting :envvar:`WEBLATE_EMAIL_USE_TLS`.

    .. versionchanged:: 4.11

       The SSL/TLS support is automatically enabled based on the
       :envvar:`WEBLATE_EMAIL_PORT`.

    .. seealso::

        :envvar:`WEBLATE_EMAIL_PORT`,
        :envvar:`WEBLATE_EMAIL_USE_TLS`,
        :setting:`django:EMAIL_USE_SSL`

.. envvar:: WEBLATE_EMAIL_USE_TLS

    Whether to use a TLS (secure) connection when talking to the SMTP server.
    This is used for explicit TLS connections, generally on port 587 or 25. If
    you are experiencing connections that hang, see the implicit TLS setting
    :envvar:`WEBLATE_EMAIL_USE_SSL`.

    .. versionchanged:: 4.11

       The SSL/TLS support is automatically enabled based on the
       :envvar:`WEBLATE_EMAIL_PORT`.

    .. seealso::

        :envvar:`WEBLATE_EMAIL_PORT`,
        :envvar:`WEBLATE_EMAIL_USE_SSL`,
        :setting:`django:EMAIL_USE_TLS`

.. envvar:: WEBLATE_EMAIL_BACKEND

    Configures Django back-end to use for sending e-mails.


    .. seealso::

        :ref:`production-email`,
        :setting:`django:EMAIL_BACKEND`

.. envvar:: WEBLATE_AUTO_UPDATE

    Configures if and how Weblate should update repositories.

    .. seealso::

        :setting:`AUTO_UPDATE`

    .. note:: This is a Boolean setting (use ``"true"`` or ``"false"``).

Site integration
~~~~~~~~~~~~~~~~

.. envvar:: WEBLATE_GET_HELP_URL

   Configures :setting:`GET_HELP_URL`.

.. envvar:: WEBLATE_STATUS_URL

   Configures :setting:`STATUS_URL`.

.. envvar:: WEBLATE_LEGAL_URL

   Configures :setting:`LEGAL_URL`.

.. envvar:: WEBLATE_PRIVACY_URL

   Configures :setting:`PRIVACY_URL`.

Error reporting
~~~~~~~~~~~~~~~

It is recommended to collect errors from the installation systematically,
see :ref:`collecting-errors`.

To enable support for Rollbar, set the following:

.. envvar:: ROLLBAR_KEY

    Your Rollbar post server access token.

.. envvar:: ROLLBAR_ENVIRONMENT

    Your Rollbar environment, defaults to ``production``.

To enable support for Sentry, set following:

.. envvar:: SENTRY_DSN

    Your Sentry DSN.

.. envvar:: SENTRY_ENVIRONMENT

    Your Sentry Environment (optional).

Localization CDN
~~~~~~~~~~~~~~~~

.. envvar:: WEBLATE_LOCALIZE_CDN_URL
.. envvar:: WEBLATE_LOCALIZE_CDN_PATH

    .. versionadded:: 4.2.1

    Configuration for :ref:`addon-weblate.cdn.cdnjs`.

    The :envvar:`WEBLATE_LOCALIZE_CDN_PATH` is path within the container. It
    should be stored on the persistent volume and not in the transient storage.

    One of possibilities is storing that inside the Weblate data dir:

    .. code-block:: yaml

        environment:
          WEBLATE_LOCALIZE_CDN_URL: https://cdn.example.com/
          WEBLATE_LOCALIZE_CDN_PATH: /app/data/l10n-cdn

    .. note::

       You are responsible for setting up serving of the files generated by
       Weblate, it only does stores the files in configured location.

    .. seealso::

        :ref:`weblate-cdn`,
        :setting:`LOCALIZE_CDN_URL`,
        :setting:`LOCALIZE_CDN_PATH`


Changing enabled apps, checks, add-ons or autofixes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. versionadded:: 3.8-5

The built-in configuration of enabled checks, add-ons or autofixes can be
adjusted by the following variables:

.. envvar:: WEBLATE_ADD_APPS
.. envvar:: WEBLATE_REMOVE_APPS
.. envvar:: WEBLATE_ADD_CHECK
.. envvar:: WEBLATE_REMOVE_CHECK
.. envvar:: WEBLATE_ADD_AUTOFIX
.. envvar:: WEBLATE_REMOVE_AUTOFIX
.. envvar:: WEBLATE_ADD_ADDONS
.. envvar:: WEBLATE_REMOVE_ADDONS

**Example:**

.. code-block:: yaml

    environment:
      WEBLATE_REMOVE_AUTOFIX: weblate.trans.autofixes.whitespace.SameBookendingWhitespace
      WEBLATE_ADD_ADDONS: customize.addons.MyAddon,customize.addons.OtherAddon

.. seealso::

   :setting:`CHECK_LIST`,
   :setting:`AUTOFIX_LIST`,
   :setting:`WEBLATE_ADDONS`,
   :setting:`django:INSTALLED_APPS`

Container settings
~~~~~~~~~~~~~~~~~~

.. envvar:: WEBLATE_WORKERS

   .. versionadded:: 4.6.1

   Base number of worker processes running in the container. When not set it is
   determined automatically on container startup based on number of CPU cores
   available.

   It is used to determine :envvar:`CELERY_MAIN_OPTIONS`,
   :envvar:`CELERY_NOTIFY_OPTIONS`, :envvar:`CELERY_MEMORY_OPTIONS`,
   :envvar:`CELERY_TRANSLATE_OPTIONS`, :envvar:`CELERY_BACKUP_OPTIONS`,
   :envvar:`CELERY_BEAT_OPTIONS`, and :envvar:`WEB_WORKERS`. You can use
   these settings to fine-tune.

.. envvar:: CELERY_MAIN_OPTIONS
.. envvar:: CELERY_NOTIFY_OPTIONS
.. envvar:: CELERY_MEMORY_OPTIONS
.. envvar:: CELERY_TRANSLATE_OPTIONS
.. envvar:: CELERY_BACKUP_OPTIONS
.. envvar:: CELERY_BEAT_OPTIONS

    These variables allow you to adjust Celery worker options. It can be useful
    to adjust concurrency (``--concurrency 16``) or use different pool
    implementation (``--pool=gevent``).

    By default, the number of concurrent workers is based on :envvar:`WEBLATE_WORKERS`.

    **Example:**

    .. code-block:: yaml

        environment:
          CELERY_MAIN_OPTIONS: --concurrency 16

    .. seealso::

        :doc:`Celery worker options <celery:reference/celery.bin.worker>`,
        :ref:`celery`

.. envvar:: WEB_WORKERS

    Configure how many uWSGI workers should be executed.

    It defaults to :envvar:`WEBLATE_WORKERS`.

    **Example:**

    .. code-block:: yaml

        environment:
          WEB_WORKERS: 32

.. envvar:: WEBLATE_SERVICE

   Defines which services should be executed inside the container. Use this for :ref:`docker-scaling`.

   Following services are defined:

   ``celery-beat``
      Celery task scheduler, only one instance should be running.
      This container is also responsible for the database structure migrations
      and it should be started prior others.
   ``celery-backup``
      Celery worker for backups, only one instance should be running.
   ``celery-celery``
      Generic Celery worker.
   ``celery-memory``
      Translation memory Celery worker.
   ``celery-notify``
      Notifications Celery worker.
   ``celery-translate``
      Automatic translation Celery worker.
   ``web``
      Web server.


.. _docker-volume:

Docker container volumes
------------------------

There are two volumes (data and cache) exported by the Weblate container. The
other service containers (PostgreSQL or Redis) have their data volumes as well,
but those are not covered by this document.

The data volume is used to store Weblate persistent data such as cloned
repositories or to customize Weblate installation.

The placement of the Docker volume on host system depends on your Docker
configuration, but usually it is stored in
:file:`/var/lib/docker/volumes/weblate-docker_weblate-data/_data/` (the path
consist of name of your docker-compose directory, container, and volume names).
In the container it is mounted as :file:`/app/data`.

The cache volume is mounted as :file:`/app/cache` and is used to store static
files. Its content is recreated on container startup and the volume can be
mounted using ephemeral filesystem such as `tmpfs`.

When creating the volumes manually, the directories should be owned by UID 1000
as that is user used inside the container.

.. seealso::

   `Docker volumes documentation <https://docs.docker.com/storage/volumes/>`_

Further configuration customization
-----------------------------------

You can further customize Weblate installation in the data volume, see
:ref:`docker-volume`.

.. _docker-custom-config:

Custom configuration files
~~~~~~~~~~~~~~~~~~~~~~~~~~

You can additionally override the configuration in
:file:`/app/data/settings-override.py` (see :ref:`docker-volume`). This is
executed at the end of built-in settings, after all environment settings
are loaded, and you can adjust or override them.

Replacing logo and other static files
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. versionadded:: 3.8-5

The static files coming with Weblate can be overridden by placing into
:file:`/app/data/python/customize/static` (see :ref:`docker-volume`). For
example creating :file:`/app/data/python/customize/static/favicon.ico` will
replace the favicon.

.. hint::

   The files are copied to the corresponding location upon container startup, so
   a restart of Weblate is needed after changing the content of the volume.

This approach can be also used to override Weblate templates. For example
:ref:`legal` documents can be placed into
:file:`/app/data/python/customize/templates/legal/documents`.

Alternatively you can also include own module (see :doc:`../customize`) and add
it as separate volume to the Docker container, for example:

.. code-block:: yaml

  weblate:
    volumes:
      - weblate-data:/app/data
      - ./weblate_customization/weblate_customization:/app/data/python/weblate_customization
    environment:
      WEBLATE_ADD_APPS: weblate_customization

Adding own Python modules
~~~~~~~~~~~~~~~~~~~~~~~~~

.. versionadded:: 3.8-5

You can place own Python modules in :file:`/app/data/python/` (see
:ref:`docker-volume`) and they can be then loaded by Weblate, most likely by
using :ref:`docker-custom-config`.

.. seealso::

   :doc:`../customize`

Configuring PostgreSQL server
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The PostgtreSQL container uses default PostgreSQL configuration and it won't
effectively utilize your CPU cores or memory. It is recommended to customize
the configuration to improve the performance.

The configuration can be adjusted as described in `Database Configuration` at
https://hub.docker.com/_/postgres. The configuration matching your environment
can be generated using https://pgtune.leopard.in.ua/.
