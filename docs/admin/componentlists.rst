.. _componentlists:

Component Lists
===============

Weblate allows you to specify multiple lists of components. These will then
appear as options on the user dashboard, and users can pick a list to be their
default view when they log in. See :ref:`dashboard` to learn more about this
feature.

The names and contents of component lists can be specified in the admin
interface, in :guilabel:`Component lists` section. Each component list must
have a name that is displayed to the user, and a slug that represents it in the
URL.

.. note::

    Since version 2.13 you can also change the dashboard settings for the
    anonymous user in the admin interface, this will change what dashboard is
    visible to unauthenticated users.

Automatic component lists
-------------------------

.. versionadded:: 2.13

Additionally you can create :guilabel:`Automatic component list assignment`
rules to automatically add components to the list based on their slug. This can
be useful for maintaining component lists for large installations or in case
you want to have component list with all components on your Weblate
installation.
