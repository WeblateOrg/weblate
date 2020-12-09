Installing on Kubernetes
========================

.. note::

   This guide is looking for contributors experienced with Kubernetes to cover
   the setup in more details.

With the Kubernetes Helm chart you can get your personal Weblate
instance up and running in seconds. All of Weblate’s dependencies are
already included. PostgreSQL is set up as the default database and
persistent volume claims are used.

You can find the chart at <https://github.com/WeblateOrg/helm/> and it can be
displayed at <https://artifacthub.io/packages/helm/weblate/weblate>.

Installation
------------

.. code-block:: shell

   helm repo add weblate https://helm.weblate.org
   helm install my-release weblate/weblate
