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

.. _support-data:

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

Getting listed
++++++++++++++

.. hint::

   Participating in Discover Weblate makes Weblate submit some information
   about your server, please see :ref:`support-data`.


To list your server with an active support subscription (see
:ref:`activate-support`) in Discover Weblate all you need to do is turn this on
in the management panel:

.. image:: /images/support-discovery.png

Listing your server without a support subsription in Discover Weblate:

1. Register yourself at <https://weblate.org/user/>
2. Register your Weblate server in the discovery database at <https://weblate.org/subscription/discovery/>
3. Confirm the service activation in your Weblate and turn on the discovery listing in your Weblate management page using :guilabel:`Enable discovery` button:

.. image:: /images/support-discovery.png

.. _customize-discover:

Customizing listing
+++++++++++++++++++

You can customize the listing by providing a text and image (570 x 260 pixels)
at <https://weblate.org/user/>.
