.. _admin-interface:

Django admin interface
======================

.. warning::

   Using Django admin interface is discouraged - you can manage most of the
   features directly in Weblate. The admin interface will be removed in future.

Administration of Weblate is done through standard Django admin interface,
which is available under :file:`/admin/` URL. Once logged in as user with
proper privileges, you can access it using the wrench icon in top navigation:

.. image:: /images/admin-wrench.png

Here you can manage objects stored in the database, such as users, translations
and other settings:

.. image:: /images/admin.png

In the :guilabel:`Reports` section you can check the status of your site, tweak
it for :ref:`production` or manage SSH keys to access :ref:`vcs-repos`.

With all sections below you can manage database objects. The most interesting one is
probably :guilabel:`Weblate translations`, where you can manage translatable
projects, see :ref:`project` and :ref:`component`.

Another section, :guilabel:`Weblate languages` holds language definitions, see
:ref:`languages` for more details.

Adding project
--------------

First you have to add project, which will serve as container for all
components. Usually you create one project for one piece of software or book
(see :ref:`project` for information on individual parameters):

.. image:: /images/add-project.png

.. seealso:: 
   
   :ref:`project`

.. _bilingual:

Bilingual components
--------------------

Once you have added a project, you can add translation components to it
(see :ref:`component` for information on individual parameters):

.. image:: /images/add-component.png

.. seealso:: 
   
   :ref:`component`,
   :ref:`bimono`

.. _monolingual:

Monolingual components
----------------------

For easier translating of monolingual formats, you should provide a template
file, which contains mapping of message IDs to source language (usually
English) (see :ref:`component` for information on individual parameters):

.. image:: /images/add-component-mono.png

.. seealso:: 
   
   :ref:`component`,
   :ref:`bimono`
