Optional Weblate modules
========================

Weblate comes with several optional modules which might be useful for your
setup.

.. _git-exporter:

Git exporter
------------

.. versionadded:: 2.10

The Git exporter provides you read only access to underlaying Git repository
using http.

Installation
++++++++++++

To install, simply add ``weblate.gitexport`` to installed applications in
:file:`settings.py`:

.. code-block:: python

    INSTALLED_APPS += (
        'weblate.gitexport',
    )

Usage
+++++

The module automatically hooks into Weblate and sets exported repository URL in
the :ref:`component`.

The repositories are accessible under ``/git/`` path of the Weblate, for example
``https://example.org/git/weblate/master/``:

.. code-block:: sh

    git clone 'https://example.org/git/weblate/master/'

Repositories are available anonymously unless :ref:`acl` is enabled. In that
case you need to authenticate using your API token (you can obtain it in your
:ref:`user-profile`):

.. code-block:: sh

    git clone 'https://user:KEY@example.org/git/weblate/master/'

Billing
-------

.. versionadded:: 2.4

Billing module is used on `Hosted Weblate <https://weblate.org/hosting/>`_
and is used to define billing plans, track invoices and usage limits.

Installation
++++++++++++

To install, simply add ``weblate.billing`` to installed applications in
:file:`settings.py`:

.. code-block:: python

    INSTALLED_APPS += (
        'weblate.billing',
    )

Usage
+++++

After installation you can control billing in the admin interface. Users with
billing enabled will get new :guilabel:`Billing` tab in their
:ref:`user-profile`.
