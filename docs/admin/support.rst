Getting support for Weblate
===========================


Weblate is copylefted libre software with community support.
Subscribers receive priority support at no extra charge. Prepaid help packages are
available for everyone. You can find more info about current support
offerings at `https://weblate.org/support <https://weblate.org/support/>`_.

.. _activate-support:

Integrating support
-------------------


.. versionadded:: 3.8

Purchased support packages can optionally be integrated into your Weblate
`subscription management <https://weblate.org/user/>`_ interface, from where you will find a link to it.
Basic instance details about your installation are also reported back to Weblate this way.

.. image:: /images/support.png

.. _support-data:

Info sent to and shown on Weblate.org
-------------------------------------

* URL to your Weblate
* Its site title
* The version you are running
* Tallies of projects, components, languages, source strings and users
* The public SSH key of your instance

Additionally, when :ref:`discover-weblate` is on:

* List of public projects (name, URL and website)

No other data is submitted.

Integration services
--------------------

* See if your support package is still valid
* :ref:`cloudbackup`
* :ref:`discover-weblate`

.. hint::

   Purchased support packages are already activated upon purchase, and can be used without integrating them.

.. _discover-weblate:

Discover Weblate
----------------

.. versionadded:: 4.5.2

.. note::

   This feature is currently in early beta.

Discover Weblate is an opt-in service making it easier for users to find
other Weblate sites and communities. Users can browse registered sites on
`https://weblate.org/discover <https://weblate.org/discover/>`_, and find
projects to contribute to there.

Getting listed
++++++++++++++

.. note::

   Make sure you are OK with publishing the info about your Weblate
   described in :ref:`support-data` for use on Discover Weblate.


List your server directly from the management panel if you have an active
support subscription (:ref:`activate-support`):

.. image:: /images/support-discovery.png

Listing your server manually:

1. Register yourself at `https://weblate.org/user <https://weblate.org/user/>`_
2. Register your Weblate site at `https://weblate.org/subscription/discovery <https://weblate.org/subscription/discovery/>`_
3. Confirm you want to activate the service from your Weblate, and turn on "Discovery listing" from its management page by clicking :guilabel:`Enable discovery`:

.. image:: /images/support-discovery.png

.. _customize-discover:

Listing description
+++++++++++++++++++

Add a text and an image (570 x 260 pixels) about your Weblate site
from `https://weblate.org/user <https://weblate.org/user/>`_.
