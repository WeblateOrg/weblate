.. _deployments:

Weblate deployments
===================

Weblate can be easily installed in your cloud. Please find detailed guide for your platform:

* :ref:`quick-docker`
* :ref:`quick-openshift2`

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
