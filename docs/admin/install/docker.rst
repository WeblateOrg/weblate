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

Upgrading the Docker container
------------------------------

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

You might also want to update the ``docker-compose`` repository, though it's
not needed in most case. Please beware of PostgreSQL version changes in this
case as it's not straightforward to upgrade the database, see `GitHub issue <https://github.com/docker-library/postgres/issues/37>`_ for more info.

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
      UWSGI_WORKERS: 4
      CELERY_MAIN_OPTIONS: --concurrency 2
      CELERY_NOTIFY_OPTIONS: --concurrency 1
      CELERY_TRANSLATE_OPTIONS: --concurrency 1

.. seealso::

   :envvar:`CELERY_MAIN_OPTIONS`,
   :envvar:`CELERY_NOTIFY_OPTIONS`,
   :envvar:`CELERY_MEMORY_OPTIONS`,
   :envvar:`CELERY_TRANSLATE_OPTIONS`,
   :envvar:`CELERY_BACKUP_OPTIONS`,
   :envvar:`CELERY_BEAT_OPTIONS`,
   :envvar:`UWSGI_WORKERS`

.. _docker-scaling:

Scaling horizontally
--------------------

.. versionadded:: 4.6

.. warning::

   This feature is a technology preview.

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
            :envvar:`WEBLATE_ADMIN_NAME`,
            :envvar:`WEBLATE_ADMIN_EMAIL`

.. envvar:: WEBLATE_SERVER_EMAIL
.. envvar:: WEBLATE_DEFAULT_FROM_EMAIL

    Configures the address for outgoing e-mails.

    .. seealso::

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


Machine translation settings
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. envvar:: WEBLATE_MT_APERTIUM_APY

    Enables :ref:`apertium` machine translation and sets :setting:`MT_APERTIUM_APY`

.. envvar:: WEBLATE_MT_AWS_REGION
.. envvar:: WEBLATE_MT_AWS_ACCESS_KEY_ID
.. envvar:: WEBLATE_MT_AWS_SECRET_ACCESS_KEY

    Configures :ref:`aws` machine translation.

    .. code-block:: yaml

        environment:
          WEBLATE_MT_AWS_REGION: us-east-1
          WEBLATE_MT_AWS_ACCESS_KEY_ID: AKIAIOSFODNN7EXAMPLE
          WEBLATE_MT_AWS_SECRET_ACCESS_KEY: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY

.. envvar:: WEBLATE_MT_DEEPL_KEY

    Enables :ref:`deepl` machine translation and sets :setting:`MT_DEEPL_KEY`

.. envvar:: WEBLATE_MT_DEEPL_API_VERSION

   Configures :ref:`deepl` API version to use, see :setting:`MT_DEEPL_API_VERSION`.

.. envvar:: WEBLATE_MT_GOOGLE_KEY

    Enables :ref:`google-translate` and sets :setting:`MT_GOOGLE_KEY`

.. envvar:: WEBLATE_MT_MICROSOFT_COGNITIVE_KEY

    Enables :ref:`ms-cognitive-translate` and sets :setting:`MT_MICROSOFT_COGNITIVE_KEY`

.. envvar:: WEBLATE_MT_MICROSOFT_ENDPOINT_URL

    Sets :setting:`MT_MICROSOFT_ENDPOINT_URL`, please note this is supposed to contain domain name only.

.. envvar:: WEBLATE_MT_MICROSOFT_REGION

    Sets :setting:`MT_MICROSOFT_REGION`

.. envvar:: WEBLATE_MT_MICROSOFT_BASE_URL

    Sets :setting:`MT_MICROSOFT_BASE_URL`

.. envvar:: WEBLATE_MT_MODERNMT_KEY

    Enables :ref:`modernmt` and sets :setting:`MT_MODERNMT_KEY`.

.. envvar:: WEBLATE_MT_MYMEMORY_ENABLED

    Enables :ref:`mymemory` machine translation and sets
    :setting:`MT_MYMEMORY_EMAIL` to :envvar:`WEBLATE_ADMIN_EMAIL`.

   **Example:**

    .. code-block:: yaml

        environment:
          WEBLATE_MT_MYMEMORY_ENABLED: 1

.. envvar:: WEBLATE_MT_GLOSBE_ENABLED

    Enables :ref:`glosbe` machine translation.

    .. code-block:: yaml

        environment:
          WEBLATE_MT_GLOSBE_ENABLED: 1

.. envvar:: WEBLATE_MT_MICROSOFT_TERMINOLOGY_ENABLED

    Enables :ref:`ms-terminology` machine translation.

    .. code-block:: yaml

        environment:
          WEBLATE_MT_MICROSOFT_TERMINOLOGY_ENABLED: 1

.. envvar:: WEBLATE_MT_SAP_BASE_URL
.. envvar:: WEBLATE_MT_SAP_SANDBOX_APIKEY
.. envvar:: WEBLATE_MT_SAP_USERNAME
.. envvar:: WEBLATE_MT_SAP_PASSWORD
.. envvar:: WEBLATE_MT_SAP_USE_MT

    Configures :ref:`saptranslationhub` machine translation.

    .. code-block:: yaml

        environment:
            WEBLATE_MT_SAP_BASE_URL: "https://example.hana.ondemand.com/translationhub/api/v1/"
            WEBLATE_MT_SAP_USERNAME: "user"
            WEBLATE_MT_SAP_PASSWORD: "password"
            WEBLATE_MT_SAP_USE_MT: 1


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

    Enables :ref:`github_auth`.

Bitbucket
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

.. _docker-saml:

SAML
++++

Self-signed SAML keys are automatically generated on first container startup.
In case you want to use own keys, place the certificate and private key in
:file:`/app/data/ssl/saml.crt` and :file:`/app/data/ssl/saml.key`.

.. envvar:: WEBLATE_SAML_IDP_ENTITY_ID
.. envvar:: WEBLATE_SAML_IDP_URL
.. envvar:: WEBLATE_SAML_IDP_X509CERT

    SAML Identity Provider settings, see :ref:`saml-auth`.


Other authentication settings
+++++++++++++++++++++++++++++

.. envvar:: WEBLATE_NO_EMAIL_AUTH

    Disables e-mail authentication when set to any value.


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

.. envvar:: POSTGRES_ALTER_ROLE

    Configures name of role to alter during migrations, see :ref:`config-postgresql`.


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

.. envvar:: WEBLATE_EMAIL_USE_SSL

    Whether to use an implicit TLS (secure) connection when talking to the SMTP
    server. In most e-mail documentation, this type of TLS connection is referred
    to as SSL. It is generally used on port 465. If you are experiencing
    problems, see the explicit TLS setting :envvar:`WEBLATE_EMAIL_USE_TLS`.

    .. seealso::

        :envvar:`WEBLATE_EMAIL_PORT`,
        :envvar:`WEBLATE_EMAIL_USE_TLS`,
        :setting:`django:EMAIL_USE_SSL`

.. envvar:: WEBLATE_EMAIL_USE_TLS

    Whether to use a TLS (secure) connection when talking to the SMTP server.
    This is used for explicit TLS connections, generally on port 587 or 25. If
    you are experiencing connections that hang, see the implicit TLS setting
    :envvar:`WEBLATE_EMAIL_USE_SSL`.

    .. seealso::

        :envvar:`WEBLATE_EMAIL_PORT`,
        :envvar:`WEBLATE_EMAIL_USE_SSL`,
        :setting:`django:EMAIL_USE_TLS`

.. envvar:: WEBLATE_EMAIL_BACKEND

    Configures Django back-end to use for sending e-mails.


    .. seealso::

        :ref:`production-email`,
        :setting:`django:EMAIL_BACKEND`

Site integration
~~~~~~~~~~~~~~~~

.. envvar:: WEBLATE_GET_HELP_URL

   Configures :setting:`GET_HELP_URL`.

.. envvar:: WEBLATE_STATUS_URL

   Configures :setting:`STATUS_URL`.

.. envvar:: WEBLATE_LEGAL_URL

   Configures :setting:`LEGAL_URL`.

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


Changing enabled apps, checks, addons or autofixes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. versionadded:: 3.8-5

The built-in configuration of enabled checks, addons or autofixes can be
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

.. envvar:: CELERY_MAIN_OPTIONS
.. envvar:: CELERY_NOTIFY_OPTIONS
.. envvar:: CELERY_MEMORY_OPTIONS
.. envvar:: CELERY_TRANSLATE_OPTIONS
.. envvar:: CELERY_BACKUP_OPTIONS
.. envvar:: CELERY_BEAT_OPTIONS

    These variables allow you to adjust Celery worker options. It can be useful
    to adjust concurrency (``--concurrency 16``) or use different pool
    implementation (``--pool=gevent``).

    By default, the number of concurrent workers matches the number of processors
    (except the backup worker, which is supposed to run only once).

    **Example:**

    .. code-block:: yaml

        environment:
          CELERY_MAIN_OPTIONS: --concurrency 16

    .. seealso::

        :doc:`Celery worker options <celery:reference/celery.bin.worker>`,
        :ref:`celery`

.. envvar:: UWSGI_WORKERS

    Configure how many uWSGI workers should be executed.

    It defaults to number of processors + 1.

    **Example:**

    .. code-block:: yaml

        environment:
          UWSGI_WORKERS: 32

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
:file:`/var/lib/docker/volumes/weblate-docker_weblate-data/_data/`. In the
container it is mounted as :file:`/app/data`.

The cache volume is mounted as :file:`/app/cache` and is used to store static
files. Its content is recreated on container startup and the volume can be
mounted using ephemeral filesystem such as `tmpfs`.

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


Select your machine - local or cloud providers
----------------------------------------------

With Docker Machine you can create your Weblate deployment either on your local
machine, or on any large number of cloud-based deployments on e.g. Amazon AWS,
Greenhost, and many other providers.
