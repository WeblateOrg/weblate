.. _componentlists:

Component Lists
===============

Specify multiple lists of components to appear as options on the user dashboard,
from which users can pick one as their default view.
See :ref:`dashboard` to learn more.

.. versionchanged:: 2.20

    A status will be presented for each component list presented on the dashboard.

The names and content of component lists can be specified in the admin
interface, in :guilabel:`Component lists` section. Each component list must
have a name that is displayed to the user, and a slug representing it in the
URL.


.. versionchanged:: 2.13

    Change dashboard settings for anonymous users from the admin interface,
    altering what dashboard is presented to unauthenticated users.

Automatic component lists
-------------------------

.. versionadded:: 2.13

Add components to the list automatically based on their slug by creating
:guilabel:`Automatic component list assignment` rules.

* Useful for maintaining component lists for large installations, or in case
  you want to have one component list with all components on your Weblate installation.

.. hint::

    Make a component list containing all the components of your Weblate installation.

1. Define :guilabel:`Automatic component list assignment` with ``^.*$`` as regular expression
in both the project and the component fields, as shown on this image:

.. image:: /images/componentlist-add.png
   :alt: Image showing the Weblate administration panel with the above configuration filled in.
