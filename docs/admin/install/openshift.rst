Installing on OpenShift
=======================

With the OpenShift Weblate template you can get your personal Weblate
instance up and running in seconds. All of Weblate’s dependencies are
already included. PostgreSQL is set up as the default database and
persistent volume claims are used.

You can find the template at <https://github.com/WeblateOrg/openshift/>.

Installation
------------

The following examples assume you have a working OpenShift v3.x
environment, with ``oc`` client tool installed. Please check the
OpenShift documentation for instructions.

Web Console
~~~~~~~~~~~

Copy the raw content from :file:`template.yml` and import them into your
project, then use the ``Create`` button in the OpenShift web console to
create your application. The web console will prompt you for the values
for all of the parameters used by the template.

CLI
~~~

To upload the Weblate template to your current project’s template
library, pass the :file:`template.yml` file with the following command:

.. code:: bash

   $ oc create -f https://raw.githubusercontent.com/WeblateOrg/openshift/main/template.yml \
      -n <PROJECT>

The template is now available for selection using the web console or the
CLI.

Parameters
^^^^^^^^^^

The parameters that you can override are listed in the parameters section of
the template. You can list them with the CLI by using the following command and
specifying the file to be used:

.. code:: bash

   $ oc process --parameters -f https://raw.githubusercontent.com/WeblateOrg/openshift/main/template.yml

   # If the template is already uploaded
   $ oc process --parameters -n <PROJECT> weblate

Provisioning
^^^^^^^^^^^^

You can also use the CLI to process templates and use the configuration
that is generated to create objects immediately.

.. code:: bash

   $ oc process -f https://raw.githubusercontent.com/WeblateOrg/openshift/main/template.yml \
       -p APPLICATION_NAME=weblate \
       -p WEBLATE_VERSION=4.3.1-1 \
       -p WEBLATE_SITE_DOMAIN=weblate.app-openshift.example.com \
       -p POSTGRESQL_IMAGE=docker-registry.default.svc:5000/openshift/postgresql:9.6 \
       -p REDIS_IMAGE=docker-registry.default.svc:5000/openshift/redis:3.2 \
       | oc create -f

The Weblate instance should be available after successful migration and
deployment at the specified ``WEBLATE_SITE_DOMAIN`` parameter.

After container setup, you can sign in as `admin` user with password provided
in ``WEBLATE_ADMIN_PASSWORD``, or a random password generated on first
start if that was not set.

To reset `admin` password, restart the container with
``WEBLATE_ADMIN_PASSWORD`` set to new password in the respective ``Secret``.

Eliminate
^^^^^^^^^

.. code:: bash

   $ oc delete all -l app=<APPLICATION_NAME>
   $ oc delete configmap -l app= <APPLICATION_NAME>
   $ oc delete secret -l app=<APPLICATION_NAME>
   # ATTTENTION! The following command is only optional and will permanently delete all of your data.
   $ oc delete pvc -l app=<APPLICATION_NAME>

   $ oc delete all -l app=weblate \
       && oc delete secret -l app=weblate \
       && oc delete configmap -l app=weblate \
       && oc delete pvc -l app=weblate

Configuration
-------------

By processing the template a respective ``ConfigMap`` will be created
and which can be used to customize the Weblate image. The ``ConfigMap``
is directly mounted as environment variables and triggers a new
deployment every time it is changed. For further configuration options,
see :ref:`docker-environment` for full list of environment variables.
