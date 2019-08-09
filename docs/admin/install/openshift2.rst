.. _quick-openshift:

Installing on OpenShift 2
-------------------------

#. You can install Weblate on OpenShift PaaS directly from its Git repository using the OpenShift Client Tools:

   .. parsed-literal::

        rhc -aweblate app create -t python-2.7 --from-code \https://github.com/WeblateOrg/weblate.git --no-git

#. After installation everything should be preconfigured, and you can immediately start adding a translation
   project as described below.

.. seealso::

    For more info, including how to retrieve the generated admin password, see :ref:`openshift`.


