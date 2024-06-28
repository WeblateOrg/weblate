Getting support for Weblate
===========================


*Weblate* is copylefted libre software with community support.
Hosting subscribers receive priority support at no extra charge.
Prepaid help packages are available for everyone, including self-hosting users.
Find info about current support offerings at https://weblate.org/support.

.. _activate-support:

Integrating support
-------------------

Purchased support packages can optionally be integrated into your Weblate
`subscription management <https://weblate.org/user/>`_ interface, from where you will find a link to it.
Basic instance details about your installation are also reported back to Weblate this way.

.. image:: /screenshots/support.webp

.. _support-data:

Info sent to the Weblate
------------------------

* Your Weblate instance URL
* Its site title
* The version you are running
* Tallies of projects, components, languages, source strings, and users
* The public SSH key of your instance

Additionally, if you turn on :ref:`discover-weblate`:

* List of public projects (name, URL, and website).

.. hint::
   Check what *Discover* shows publicly in the :ref:`discover-weblate` description.

No other data is submitted.

Integration services
--------------------

* See if your support package is still valid
* :ref:`cloudbackup`
* :ref:`discover-weblate`

.. hint::

   Purchased support packages are already activated upon purchase and can be used without integrating them.

.. _discover-weblate:

Discover Weblate
----------------

.. versionadded:: 4.5.2

*Discover* is an opt-in service making it easier for translators to find
other Weblate instances and communities.
Users can browse registered sites and find projects to contribute to on
https://weblate.org/discover/.

Getting listed
++++++++++++++

.. note::

   Make sure you are OK with publishing your instance name, URL, tally of projects, components, and users,
   together with names of public projects and components for use on *Discover*.


List your server directly from the management panel if you have an active
support subscription (:ref:`activate-support`):

.. image:: /screenshots/support-discovery.webp

All steps for listing a server without a support contract:

1. Register yourself at https://weblate.org/user/
2. Register your Weblate site at https://weblate.org/subscription/discovery/
3. Confirm you want your Weblate listed by clicking :guilabel:`Enable discovery` from its management page :

.. image:: /screenshots/support-discovery.webp

.. _customize-discover:

Listing customization
+++++++++++++++++++++

You are encouraged to provide an image (570 x 260 pixels) and description of your Weblate site
at https://weblate.org/user/. This improves your instance’s visibility in the list.
