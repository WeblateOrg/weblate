.. _quick-openshift2:

Installing on OpenShift 2
=========================

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

    # Install Git from the development master branch
    rhc -aweblate app create -t python-2.7 --from-code https://github.com/WeblateOrg/weblate.git --no-git

    # Install Weblate release
    rhc -aweblate app create -t python-2.7 --from-code https://github.com/WeblateOrg/weblate.git#weblate-3.9.1 --no-git

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
* Weblate directories (STATIC_ROOT, :setting:`DATA_DIR`, avatar cache) set according to OpenShift requirements/conventions.
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

    rhc -aweblate env set WEBLATE_SCRIPTS='("${OPENSHIFT_DATA_DIR}/weblate/examples/hook-unwrap-po",)'

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
