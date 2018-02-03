.. _deployments:

Weblate deployments
===================

Weblate comes with support for deployment using several technologies. This
section is overview of them.

.. _docker:

Running Weblate in the Docker
-----------------------------

With dockerized weblate deployment you can get your personal weblate instance
up an running in seconds. All of Weblate's dependencies are already included.
PostgreSQL is configured as the default database.

.. _docker-deploy:

Deployment
++++++++++

The following examples assume you have a working Docker environment, with
docker-compose installed. Please check Docker documentation for instructions on
this.

1. Clone weblate-docker repo:

   .. code-block:: sh

        git clone https://github.com/WeblateOrg/docker.git weblate-docker
        cd weblate-docker

2. Create a :file:`docker-compose.override.yml` file with your settings.
   See :ref:`docker-environment` full list of environment vars

   .. code-block:: yaml

        version: '2'
        services:
          weblate:
            environment:
              - WEBLATE_EMAIL_HOST=smtp.example.com
              - WEBLATE_EMAIL_HOST_USER=user
              - WEBLATE_EMAIL_HOST_PASSWORD=pass
              - WEBLATE_ALLOWED_HOSTS=weblate.example.com
              - WEBLATE_ADMIN_PASSWORD=password for admin user

   .. note::

        If :envvar:`WEBLATE_ADMIN_PASSWORD` is not set, admin user is created with
        random password printed out on first startup.

3. Build Weblate containers:

   .. code-block:: sh

        docker-compose build

4. Start Weblate containers:

   .. code-block:: sh

        docker-compose up

Enjoy your Weblate deployment, it's accessible on port 80 of the ``weblate`` container.

.. versionchanged:: 2.15-2

    The setup has changed recently, prior there was separate web server
    container, since 2.15-2 the web server is embedded in weblate container.

.. seealso:: :ref:`invoke-manage`

.. _docker-ssl:

Docker container with https support
+++++++++++++++++++++++++++++++++++

Please see :ref:`docker-deploy` for generic deployment instructions. To add
HTTPS reverse proxy additional Docker container is required, we will use
`https-portal <https://hub.docker.com/r/steveltn/https-portal/>`_. This is 
used in the :file:`docker-compose-https.yml` file. Then you just need to create
a :file:`docker-compose-https.override.yml` file with your settings:

.. code-block:: yaml

    version: '2'
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

Whenever invoking :program:`docker-compose` you need to pass both files to it
then:

.. code-block:: console

    docker-compose -f docker-compose-https.yml -f docker-compose-https.override.yml build
    docker-compose -f docker-compose-https.yml -f docker-compose-https.override.yml up

Upgrading Docker container
++++++++++++++++++++++++++

Usually it is good idea to update the weblate container only and keep the PostgreSQL
container at version you have as upgrading PostgreSQL is quite painful and in most
cases it does not bring many benefits.

You can do this by sticking with existing docker-compose and just pulling
latest images and restarting:

.. code-block:: sh

    docker-compose down
    docker-compose pull
    docker-compose build --pull
    docker-compose up

The Weblate database should be automatically migrated on first start and there
should be no need for additional manual actions.

Maintenance tasks
+++++++++++++++++

There are some cron jobs to run. You should set :envvar:`WEBLATE_OFFLOAD_INDEXING` to ``1`` when these are setup

.. code-block:: text

    */5 * * * * cd /usr/share/weblate/; docker-compose run --rm weblate update_index
    @daily cd /usr/share/weblate/; docker-compose run --rm weblate cleanuptrans
    @hourly cd /usr/share/weblate-docker/; docker-compose run --rm weblate commit_pending --all --age=96

.. _docker-environment:

Docker environment variables
++++++++++++++++++++++++++++

Many of Weblate :ref:`config` can be set in Docker container using environment variables:

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

    Configures verbosity of logging.


.. envvar:: WEBLATE_SITE_TITLE

    Configures site title shown on headings of all pages.

.. envvar:: WEBLATE_ADMIN_NAME
.. envvar:: WEBLATE_ADMIN_EMAIL

    Configures site admins name and email.

    **Example:**

    .. code-block:: yaml

        environment:
          - WEBLATE_ADMIN_NAME=Weblate Admin
          - WEBLATE_ADMIN_EMAIL=noreply@example.com

    .. seealso::

            :ref:`production-admins`

.. envvar:: WEBLATE_ADMIN_PASSWORD

    Sets password for admin user. If not set, admin user is created with random
    password printed out on first startup.

    .. versionchanged:: 2.9

        Since version 2.9, the admin user is adjusted on every container
        startup to match :envvar:`WEBLATE_ADMIN_PASSWORD`, :envvar:`WEBLATE_ADMIN_NAME`
        and :envvar:`WEBLATE_ADMIN_EMAIL`.

.. envvar:: WEBLATE_SERVER_EMAIL
.. envvar:: WEBLATE_DEFAULT_FROM_EMAIL

    Configures address for outgoing mails.

    .. seealso::

        :ref:`production-email`

.. envvar:: WEBLATE_ALLOWED_HOSTS

    Configures allowed HTTP hostnames using :setting:`ALLOWED_HOSTS` and sets
    site name to first one.

    **Example:**

    .. code-block:: yaml

        environment:
          - WEBLATE_ALLOWED_HOSTS=weblate.example.com,example.com

    .. seealso::

        :ref:`production-hosts`,
        :ref:`production-site`

.. envvar:: WEBLATE_SECRET_KEY

    Configures secret used for Django for cookies signing.

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

    Configures time zone used.

.. envvar:: WEBLATE_OFFLOAD_INDEXING

    Configures offloaded indexing.

    **Example:**

    .. code-block:: yaml

        environment:
          - WEBLATE_OFFLOAD_INDEXING=1

    .. seealso::

        :ref:`production-indexing`

.. envvar:: WEBLATE_ENABLE_HTTPS

    Makes Weblate assume it is operated behind HTTPS reverse proxy, it makes
    Weblate use https in email and API links or set secure flags on cookies.

    .. note::

        This does not make the Weblate container accept https connections, you
        need to use a standalone HTTPS reverse proxy, see :ref:`docker-ssl` for
        example.

    **Example:**

    .. code-block:: yaml

        environment:
          - WEBLATE_ENABLE_HTTPS=1

    .. seealso::

        :ref:`production-site`

.. envvar:: WEBLATE_IP_PROXY_HEADER

    Enables Weblate fetching IP address from given HTTP header. Use this when using
    reverse proxy in front of Weblate container.

    Enables :setting:`IP_BEHIND_REVERSE_PROXY` and sets :setting:`IP_PROXY_HEADER`.

    **Example:**

    .. code-block:: yaml

        environment:
          - WEBLATE_IP_PROXY_HEADER=HTTP_X_FORWARDED_FOR


.. envvar:: WEBLATE_REQUIRE_LOGIN

    Configures login required for whole Weblate using :setting:`LOGIN_REQUIRED_URLS`.

    **Example:**

    .. code-block:: yaml

        environment:
          - WEBLATE_REQUIRE_LOGIN=1

.. envvar:: WEBLATE_GOOGLE_ANALYTICS_ID

    Configures ID for Google Analytics by changing :setting:`GOOGLE_ANALYTICS_ID`.

.. envvar:: WEBLATE_GITHUB_USERNAME

    Configures github username for GitHub pull requests by changing
    :setting:`GITHUB_USERNAME`.

    .. seealso::

       :ref:`github-push`,
       :ref:`hub-setup`

.. envvar:: WEBLATE_SIMPLIFY_LANGUAGES

    Configures language simplification policy, see :setting:`SIMPLIFY_LANGUAGES`.

.. envvar:: WEBLATE_AKISMET_API_KEY

    Configures Akismet API key, see :setting:`AKISMET_API_KEY`.


Machine translation settings
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. envvar:: WEBLATE_MT_GOOGLE_KEY

    Enables Google machine translation and sets :setting:`MT_GOOGLE_KEY`

.. envvar:: WEBLATE_MT_MICROSOFT_COGNITIVE_KEY

    Enables Microsoft machine translation and sets :setting:`MT_MICROSOFT_COGNITIVE_KEY`

Authentication settings
~~~~~~~~~~~~~~~~~~~~~~~

.. envvar:: WEBLATE_AUTH_LDAP_SERVER_URI
.. envvar:: WEBLATE_AUTH_LDAP_USER_DN_TEMPLATE
.. envvar:: WEBLATE_AUTH_LDAP_USER_ATTR_MAP

    LDAP authentication configuration.

    **Example:**

    .. code-block:: yaml

        environment:
          - WEBLATE_AUTH_LDAP_SERVER_URI=ldap://ldap.example.org
          - WEBLATE_AUTH_LDAP_USER_DN_TEMPLATE=uid=%(user)s,ou=People,dc=example,dc=net
          # map weblate 'first_name' to ldap 'name' and weblate 'email' attribute to 'mail' ldap attribute.
          # another example that can be used with OpenLDAP: 'first_name:cn,email:mail'
          - WEBLATE_AUTH_LDAP_USER_ATTR_MAP=first_name:name,email:mail

    .. seealso::

        :ref:`ldap-auth`

.. envvar:: WEBLATE_SOCIAL_AUTH_GITHUB_KEY
.. envvar:: WEBLATE_SOCIAL_AUTH_GITHUB_SECRET

    Enables :ref:`github_auth`.

.. envvar:: WEBLATE_SOCIAL_AUTH_BITBUCKET_KEY
.. envvar:: WEBLATE_SOCIAL_AUTH_BITBUCKET_SECRET

    Enables :ref:`bitbucket_auth`.

.. envvar:: WEBLATE_SOCIAL_AUTH_FACEBOOK_KEY
.. envvar:: WEBLATE_SOCIAL_AUTH_FACEBOOK_SECRET

    Enables :ref:`facebook_auth`.

.. envvar:: WEBLATE_SOCIAL_AUTH_GOOGLE_OAUTH2_KEY
.. envvar:: WEBLATE_SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET

    Enables :ref:`google_auth`.

.. envvar:: WEBLATE_SOCIAL_AUTH_GITLAB_KEY
.. envvar:: WEBLATE_SOCIAL_AUTH_GITLAB_SECRET
.. envvar:: WEBLATE_SOCIAL_AUTH_GITLAB_API_URL

    Enables :ref:`gitlab_auth`.

Processing hooks
~~~~~~~~~~~~~~~~

All these processing hooks should get a comma-separated list of available
scripts, for example:

.. code-block:: sh

    WEBLATE_POST_UPDATE_SCRIPTS=/usr/local/share/weblate/examples/hook-unwrap-po

.. seealso::

    :ref:`processing`

.. envvar:: WEBLATE_POST_UPDATE_SCRIPTS

    Sets :setting:`POST_UPDATE_SCRIPTS`.

.. envvar:: WEBLATE_PRE_COMMIT_SCRIPTS

    Sets :setting:`PRE_COMMIT_SCRIPTS`.

.. envvar:: WEBLATE_POST_COMMIT_SCRIPTS

    Sets :setting:`POST_COMMIT_SCRIPTS`.

.. envvar:: WEBLATE_POST_PUSH_SCRIPTS

    Sets :setting:`POST_PUSH_SCRIPTS`.

.. envvar:: WEBLATE_POST_ADD_SCRIPTS

    Sets :setting:`POST_ADD_SCRIPTS`.


PostgreSQL database setup
~~~~~~~~~~~~~~~~~~~~~~~~~

The database is created by :file:`docker-compose.yml`, so this settings affects
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

    PostgreSQL server port. Default to empty (use default value).


Caching server setup
~~~~~~~~~~~~~~~~~~~~

Using memcached is strongly recommended by Weblate and you have to provide
memcached instance when running Weblate in Docker.

.. seealso:: :ref:`production-cache`

.. envvar:: MEMCACHED_HOST

   The memcached server hostname or IP adress. Defaults to ``cache``.

.. envvar:: MEMCACHED_PORT

    The memcached server port. Defaults to ``11211``.

Email server setup
~~~~~~~~~~~~~~~~~~

To make outgoing email work, you need to provide mail server.

.. seealso:: :ref:`out-mail`

.. envvar:: WEBLATE_EMAIL_HOST

    Mail server, the server has to listen on port 587 and understand TLS.

    .. seealso:: :setting:`django:EMAIL_HOST`

.. envvar:: WEBLATE_EMAIL_PORT

    Mail server port, use if your cloud provider or ISP blocks outgoing
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
    server. In most email documentation this type of TLS connection is referred
    to as SSL. It is generally used on port 465. If you are experiencing
    problems, see the explicit TLS setting :envvar:`WEBLATE_EMAIL_USE_TLS`.

    .. seealso:: :setting:`django:EMAIL_USE_SSL`

.. envvar:: WEBLATE_EMAIL_USE_TLS

    Whether to use a TLS (secure) connection when talking to the SMTP server.
    This is used for explicit TLS connections, generally on port 587. If you
    are experiencing hanging connections, see the implicit TLS setting
    :envvar:`WEBLATE_EMAIL_USE_SSL`.

    .. seealso:: :setting:`django:EMAIL_USE_TLS`

Hub setup
+++++++++

In order to use the Github pull requests feature, you must initialize hub configuration by entering the weblate container and executing an arbitrary hub command. For example:

.. code-block:: sh

    docker-compose exec weblate bash
    cd
    HOME=/app/data/home hub clone octocat/Spoon-Knife

The username passed for credentials must be the same as :setting:`GITHUB_USERNAME`.

.. seealso::

    :ref:`github-push`,
    :ref:`hub-setup`

Select your machine - local or cloud providers
++++++++++++++++++++++++++++++++++++++++++++++

With docker-machine you can create your Weblate deployment either on your local
machine or on any large number of cloud-based deployments on e.g. Amazon AWS,
Digitalocean and many more providers.

.. _openshift:

Running Weblate on OpenShift 2
------------------------------

This repository contains a configuration for the OpenShift platform as a
service product, which facilitates easy installation of Weblate on OpenShift
Online (https://www.openshift.com/), OpenShift Enterprise
(https://enterprise.openshift.com/) and OpenShift Origin
(https://www.openshift.org/).

Prerequisites
+++++++++++++

1. OpenShift Account

   You need an account for OpenShift Online (https://www.openshift.com/) or
   another OpenShift installation you have access to.

   You can register a free account on OpenShift Online, which allows you to
   host up to 3 applications free of charge.

2. OpenShift Client Tools

   In order to follow the examples given in this documentation you need to have
   the OpenShift Client Tools (RHC) installed:
   https://developers.openshift.com/en/managing-client-tools.html

   While there are other possibilities to create and configure OpenShift
   applications, this documentation is based on the OpenShift Client Tools
   (RHC) because they provide a consistent interface for all described
   operations.

Installation
++++++++++++

You can install Weblate on OpenShift directly from Weblate's Github repository
with the following command:

.. code-block:: sh

    # Install Git HEAD
    rhc -aweblate app create -t python-2.7 --from-code https://github.com/WeblateOrg/weblate.git --no-git

    # Install Weblate 2.10
    rhc -aweblate app create -t python-2.7 --from-code https://github.com/WeblateOrg/weblate.git#weblate-2.10 --no-git

The ``-a`` option defines the name of your weblate installation, ``weblate`` in
this instance. You are free to specify a different name.

The above example installs latest development version, you can optionally
specify tag identifier right of the ``#`` sign to identify the version of
Weblate to install. For a list of available versions see here:
https://github.com/WeblateOrg/weblate/tags.

The ``--no-git`` option skips the creation of a
local git repository.

You can also specify which database you want to use:

.. code-block:: sh

    # For MySQL
    rhc -aweblate app create -t python-2.7 -t mysql-5.5 --from-code https://github.com/WeblateOrg/weblate.git --no-git

    # For PostgreSQL
    rhc -aweblate app create -t python-2.7 -t postgresql-9.2 --from-code https://github.com/WeblateOrg/weblate.git --no-git

Default Configuration
+++++++++++++++++++++

After installation on OpenShift Weblate is ready to use and preconfigured as follows:

* SQLite embedded database (:setting:`DATABASES`)
* Random admin password
* Random Django secret key (:setting:`SECRET_KEY`)
* Indexing offloading if the cron cartridge is installed (:setting:`OFFLOAD_INDEXING`)
* Committing of pending changes if the cron cartridge is installed (:djadmin:`commit_pending`)
* Weblate machine translations for suggestions bases on previous translations (:setting:`MACHINE_TRANSLATION_SERVICES`)
* Weblate directories (STATIC_ROOT, :setting:`DATA_DIR`, :setting:`TTF_PATH`, Avatar cache) set according to OpenShift requirements/conventions
* Django site name and ALLOWED_HOSTS set to DNS name of your OpenShift application
* Email sender addresses set to no-reply@<OPENSHIFT_CLOUD_DOMAIN>, where <OPENSHIFT_CLOUD_DOMAIN> is the domain OpenShift runs under. In case of OpenShift Online it's rhcloud.com.

.. seealso::

   :ref:`customize_config`

Retrieve Admin Password
~~~~~~~~~~~~~~~~~~~~~~~

You can retrieve the generated admin password with the following command:

.. code-block:: sh

    rhc -aweblate ssh credentials

Indexing Offloading
~~~~~~~~~~~~~~~~~~~

To enable the preconfigured indexing offloading you need to add the cron cartridge to your application and restart it:

.. code-block:: sh

    rhc -aweblate add-cartridge cron
    rhc -aweblate app stop
    rhc -aweblate app start

The fulltext search index will then be updated every 5 minutes.
Restarting with ``rhc restart`` instead will not enable indexing offloading in Weblate.
You can verify that indexing offloading is indeed enabled by visiting the URL ``/admin/performance/`` of your application.

Pending Changes
~~~~~~~~~~~~~~~

Weblate's OpenShift configuration contains a cron job which periodically commits pending changes older than a certain age (24h by default).
To enable the cron job you need to add the cron cartridge and restart Weblate as described in the previous section. You can change the age
parameter by setting the environment variable WEBLATE_PENDING_AGE to the desired number of hours, e.g.:

.. code-block:: sh

    rhc -aweblate env set WEBLATE_PENDING_AGE=48

.. _customize_config:

Customize Weblate Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You can customize the configuration of your Weblate installation on OpenShift
through environment variables.  Override any of Weblate's setting documented
under :ref:`config` using ``rhc env set`` by prepending the settings name with
``WEBLATE_``. The variable content is put verbatim to the configuration file,
so it is parsed as Python string, after replacing environment variables in it
(eg. ``$PATH``). To put literal ``$`` you need to escape it as ``$$``.

For example override the :setting:`ADMINS` setting like this:

.. code-block:: sh

    rhc -aweblate env set WEBLATE_ADMINS='(("John Doe", "jdoe@example.org"),)'

To change site title, do not forget to include additional quotes:

.. code-block:: sh

    rhc -aweblate env set WEBLATE_SITE_TITLE='"Custom Title"'

New settings will only take effect after restarting Weblate:

.. code-block:: sh

    rhc -aweblate app stop
    rhc -aweblate app start

Restarting using ``rhc -aweblate app restart`` does not work. For security reasons only constant expressions are allowed as values.
With the exception of environment variables which can be referenced using ``${ENV_VAR}``. For example:

.. code-block:: sh

    rhc -aweblate env set WEBLATE_PRE_COMMIT_SCRIPTS='("${OPENSHIFT_DATA_DIR}/examples/hook-unwrap-po",)'

You can check the effective settings Weblate is using by running:

.. code-block:: sh

    rhc -aweblate ssh settings

This will also print syntax errors in your expressions.
To reset a setting to its preconfigured value just delete the corresponding environment variable:

.. code-block:: sh

   rhc -aweblate env unset WEBLATE_ADMINS

.. seealso::

   :ref:`config`

Updating
++++++++

It is recommended that you try updates on a clone of your Weblate installation before running the actual update.
To create such a clone run:

.. code-block:: sh

    rhc -aweblate2 app create --from-app weblate

Visit the newly given URL with a browser and wait for the install/update page to disappear.

You can update your Weblate installation on OpenShift directly from Weblate's github repository by executing:

.. code-block:: sh

    rhc -aweblate2 ssh update https://github.com/WeblateOrg/weblate.git

The identifier right of the ``#`` sign identifies the version of Weblate to install.
For a list of available versions see here: https://github.com/WeblateOrg/weblate/tags.
Please note that the update process will not work if you modified the git repository of you weblate installation.
You can force an update by specifying the ``--force`` option to the update script. However any changes you made to the
git repository of your installation will be discarded:

.. code-block:: sh

   rhc -aweblate2 ssh update --force https://github.com/WeblateOrg/weblate.git

The ``--force`` option is also needed when downgrading to an older version.
Please note that only version 2.0 and newer can be installed on OpenShift,
as older versions don't include the necessary configuration files.

The update script takes care of the following update steps as described under :ref:`generic-upgrade-instructions`.

* Install any new requirements
* manage.py migrate
* manage.py setupgroups --move
* manage.py setuplang
* manage.py rebuild_index --all
* manage.py collectstatic --noinput


Bitnami Weblate stack
---------------------

Bitnami provides Weblate stack for many platforms at
<https://bitnami.com/stack/weblate>. The setup will be adjusted during
installation, see <https://bitnami.com/stack/weblate/README.txt> for more
documentation.

Weblate in YunoHost
-------------------

The self-hosting project `YunoHost <https://yunohost.org/>`_ provides a package
for Weblate. Once you have your YunoHost installation, you may install Weblate
as any other application. It will provide you a fully working stack with backup
and restoration, but you may still have to edit your settings file for specific
usages.

You may use your administration interface or this button (it will bring you to your server):

.. image:: https://install-app.yunohost.org/install-with-yunohost.png
             :alt: Install Weblate with YunoHost
             :target: https://install-app.yunohost.org/?app=weblate

It also is possible to use the command line interface:

.. code-block:: sh

    yunohost app install https://github.com/YunoHost-Apps/weblate_ynh
