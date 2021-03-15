Getting support for Weblate
===========================


Weblate is copylefted libre software with community support.
Subscribers receive priority support at no extra charge. Prepaid help packages are
available for everyone. You can find more info about current support
offerings at <https://weblate.org/support/>.

.. _activate-support:

Integrating support
-------------------


.. versionadded:: 3.8

Purchased support packages can optionally be integrated into your Weblate
`subscription management <https://weblate.org/user/>`_ interface, from where you will find a link to it.
Basic instance details about your installation are also reported back to Weblate this way.

.. image:: /images/support.png

Data submitted to the Weblate
-----------------------------

* URL where your Weblate instance is configured
* Your site title
* The Weblate version you are running
* Tallies of some objects in your Weblate database (projects, components, languages, source strings and users)
* The public SSH key of your instance

Additionally, when :ref:`discover-weblate` is turned on:

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

Discover Weblate is an opt-in service that makes it easier for users to find
Weblate servers and communities. Users can browse registered services on
<https://weblate.org/discover/>, and find there projects to contribute.

Listing your server in Discover Weblate:

.. hint::

   You can skip the first two steps by activating a support package. The server
   registration was already done during the activation of your support package, see
   :ref:`activate-support`.

1. Register yourself at <https://weblate.org/user/>
2. Register your Weblate server in the discovery database
3. Turn on the discovery listing in your Weblate management page using :guilabel:`Enable discovery` button:

.. image:: /images/support-discovery.png
