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

Additionaly, when :ref:`weblate-discovery` is turned on:

* List of public projects (name, URL and website)

No other data is submitted.

Integration services
--------------------

* See if your support package is still valid
* :ref:`cloudbackup`
* :ref:`weblate-discovery`

.. hint::

   Purchased support packages are already activated upon purchase, and can be used without integrating them.

.. _weblate-discovery:

Weblate discovery
-----------------

.. versionadded:: 4.5.2

.. note::

   This feature is currently in early beta.

Weblate discovery is an opt-in service that makes it easier for users to find
Weblate servers. Users can browse registered services on
<https://weblate.org/discover/>, and find projects to contribute.
