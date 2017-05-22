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

After installing you need to migrate your database, so that existing
repositories are properly exported:

.. code-block:: sh

    ./manage.py migrate

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

This module includes additional database structures, to have them installed you
should run the database migration:

.. code-block:: sh

    ./manage.py migrate

Usage
+++++

After installation you can control billing in the admin interface. Users with
billing enabled will get new :guilabel:`Billing` tab in their
:ref:`user-profile`.

Legal
-----

.. versionadded:: 2.15

Legal module is used on `Hosted Weblate <https://weblate.org/hosting/>`_
and is used to provide required legal documents.

.. note::

    The module ships legal documents for Hosted Weblate service. You are
    required to adjust the templates to match your use case.

Installation
++++++++++++

To install, simply add ``weblate.legal`` to installed applications in
:file:`settings.py`:

.. code-block:: python

    INSTALLED_APPS += (
        'weblate.legal',
    )

This module includes additional database structures, to have them installed you
should run the database migration:

.. code-block:: sh

    ./manage.py migrate

Now you should edit the legal documents to match your service. You can
find them in the :file:`weblate/legal/templates/legal/` folder.

Usage
+++++

After installation the legal documents are shown in Weblate UI.

.. _avatars:

Avatars
-------

Weblate comes with built in support for showing user avatars based on emails.
This can be disabled using :setting:`ENABLE_AVATARS`. The avatars are
downloaded and cached server side to reduce information leaks to the sites
serving them.

Weblate currently supports two backends:

* `Libravatar <https://www.libravatar.org/>`_, what is federated avatar service
  with fallback to `Gravatar`_. Libravatar is used automatically when 
  `pyLibravatar <https://pypi.python.org/pypi/pyLibravatar>`_ is installed.
* `Gravatar`_ can be also used directly by Weblate, that is used if the
  pyLibravatar library is not found.

.. _Gravatar: https://gravatar.com/

.. seealso:: 
   
   :ref:`production-cache-avatar`,
   :setting:`ENABLE_AVATARS`
