.. _componentlists:

Component Lists
===============

Specify multiple lists of components to appear as options on the user dashboard,
from which users can pick one as their default view.
See :ref:`dashboard` to learn more.

.. hint::

    A status will be presented for each component list presented on the dashboard.

Each component list has a name displayed to the user and a slug used in the
URL. Component lists can be managed using the :ref:`api`. Instance
administrators can also use the low-level :ref:`admin-interface` when direct
database-object management is necessary.


.. hint::

    Change dashboard settings for anonymous users from the admin interface,
    altering what dashboard is presented to unauthenticated users.

Automatic component lists
-------------------------

Add components to the list automatically based on their slug by creating
:guilabel:`Automatic component list assignment` rules.

* Useful for maintaining component lists for large installations, or in case
  you want to have one component list with all components on your Weblate installation.

.. hint::

    Make a component list containing all the components of your Weblate installation.

1. Define :guilabel:`Automatic component list assignment` with ``^.*$`` as
   regular expression in both the project and the component fields.
