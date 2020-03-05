Optional Weblate modules
========================

Several optional modules are available for your setup.

.. _git-exporter:

Git exporter
------------

.. versionadded:: 2.10

Provides you read-only access to the underlying Git repository using HTTPS.

Installation
++++++++++++

1. Add ``weblate.gitexport`` to installed apps in :file:`settings.py`:

.. code-block:: python

    INSTALLED_APPS += (
        'weblate.gitexport',
    )

2. Migrate your database after installation to export existing repositories:

.. code-block:: sh

    ./manage.py migrate

Usage
+++++

The module automatically hooks into Weblate and sets the exported repository URL in
the :ref:`component`.
The repositories are accessible under the ``/git/`` part of the Weblate URL, for example
``https://example.org/git/weblate/master/``:

.. code-block:: sh

    git clone 'https://example.org/git/weblate/master/'

Repositories are available anonymously unless :ref:`acl` is turned on.
This requires authenticate using your API token (it can be obtained in your
:ref:`user-profile`):

.. code-block:: sh

    git clone 'https://user:KEY@example.org/git/weblate/master/'


.. _billing:

Billing
-------

.. versionadded:: 2.4

This is used on `Hosted Weblate <https://weblate.org/hosting/>`_ to define
billing plans, track invoices and usage limits.

Installation
++++++++++++

1. Add ``weblate.billing`` to installed apps in
:file:`settings.py`:

.. code-block:: python

    INSTALLED_APPS += (
        'weblate.billing',
    )

2. Run the database migration to optinally install additional database structures for the module:

.. code-block:: sh

    ./manage.py migrate

Usage
+++++

Installation lets you control billing and create/import new components and projects from your admin interface
if the billing is within its configured limits (any overusage prevents project/component creation)
  and paid (if its price is non zero).

Admins can create new components for their projects without escalating to superuser status (see :ref:`adding-projects`).

:ref:`integrating-support` lets users in charge of billing create new projects from the :guilabel:`Billing` tab in their :ref:`user-profile`. A choice for which billing account to charged will be presented if more than one is available.


.. _legal:

Legal
-----

.. versionadded:: 2.15

This is used on `Hosted Weblate <https://weblate.org/hosting/>`_ to provide required
legal documents. It comes provided with blank documents, and you are expected to fill out the
following templates in the documents:

:file:`legal/documents/tos.html`
   Terms of service document
:file:`legal/documents/privacy.html`
   Privacy policy document
:file:`legal/documents/summary.html`
   Short overview of the terms of service and privacy policy

.. note::

    Legal documents for the Hosted Weblate service is availalbe in this Git repository
    <https://github.com/WeblateOrg/hosted/tree/master/wlhosted/legal/templates/legal/documents>.

    Most likely these will not be directly usable to you, but might come in handy
    as a starting point if adjusted to meet your needs.

Installation
++++++++++++

1. Add ``weblate.legal`` to installed apps in
:file:`settings.py`:

.. code-block:: python

    INSTALLED_APPS += (
        'weblate.legal',
    )

    # Optional:

    # Social auth pipeline to confirm TOS upon registration/login
    SOCIAL_AUTH_PIPELINE += (
        'weblate.legal.pipeline.tos_confirm',
    )

    # Middleware to enforce TOS confirmation of logged in users
    MIDDLEWARE += [
        'weblate.legal.middleware.RequireTOSMiddleware',
    ]

2. Run the database migration to optinally install additional database structures for the module:

.. code-block:: sh

    ./manage.py migrate

3. Edit the legal documents in the :file:`weblate/legal/templates/legal/` folder to match your service.

Usage
+++++

After installation the legal documents are shown in the Weblate UI.

.. _avatars:

Avatars
-------

Avatars are downloaded and cached server-side to reduce information leaks to the sites serving them
by default. The built-in support for fetching avatars from e-mails addresses configured for it can be
turned off using :setting:`ENABLE_AVATARS`. 

Weblate currently supports:

* `Gravatar <https://gravatar.com/>`_

.. seealso::

   :ref:`production-cache-avatar`,
   :setting:`AVATAR_URL_PREFIX`,
   :setting:`ENABLE_AVATARS`

Spam protection
---------------

You can protect against suggestion spamming by unauthenticated users by using
the `akismet.com <https://akismet.com/>`_ service.

1. Install the `akismet` Python module
2. Configure the Akismet API key.

.. seealso::

    :setting:`AKISMET_API_KEY`


.. _gpg-sign:

Signing Git commits with GnuPG
------------------------------

.. versionadded:: 3.1

All commits can be signed by the GnuPG key of the Weblate instance.

1. Turn on :setting:`WEBLATE_GPG_IDENTITY`. (Weblate will generate a GnuPG
key when needed and will use it to sign all translation commits.)

This feature needs GnuPG 2.1 or newer installed.

You can find the key in the :setting:`DATA_DIR` and the public key is shown on
the "About" page:

.. image:: /images/about-gpg.png

2. Alternatively you can also import existing keys into Weblate, just set
``HOME=$DATA_DIR/home`` when invoking gpg.

.. seealso::

    :setting:`WEBLATE_GPG_IDENTITY`

.. _rate-limit:

Rate limiting
-------------

.. versionchanged:: 3.2

      The rate limiting now accepts more fine-grained configuration.

Several operations in Weblate are rate limited. At most
:setting:`RATELIMIT_ATTEMPTS` attempts are allowed within :setting:`RATELIMIT_WINDOW` seconds.
The user is then blocked for :setting:`RATELIMIT_LOCKOUT`. There are also settings specific to scopes, for example ``RATELIMIT_CONTACT_ATTEMPTS`` or ``RATELIMIT_TRANSLATE_ATTEMPTS``. The table below is a full list of available scopes.

The following operations are subject to rate limiting:

+-----------------------------------+--------------------+------------------+------------------+----------------+
| Name                              | Scope              | Allowed attempts | Ratelimit window | Lockout period |
+===================================+====================+==================+==================+================+
| Registration                      | ``REGISTRATION``   |                5 |              300 |            600 |
+-----------------------------------+--------------------+------------------+------------------+----------------+
| Sending message to admins         | ``MESSAGE``        |                5 |              300 |            600 |
+-----------------------------------+--------------------+------------------+------------------+----------------+
| Password authentication on login  | ``LOGIN``          |                5 |              300 |            600 |
+-----------------------------------+--------------------+------------------+------------------+----------------+
| Sitewide search                   | ``SEARCH``         |                6 |               60 |             60 |
+-----------------------------------+--------------------+------------------+------------------+----------------+
| Translating                       | ``TRANSLATE``      |               30 |               60 |            600 |
+-----------------------------------+--------------------+------------------+------------------+----------------+
| Adding to glossary                | ``GLOSSARY``       |               30 |               60 |            600 |
+-----------------------------------+--------------------+------------------+------------------+----------------+

If a user fails to log in :setting:`AUTH_LOCK_ATTEMPTS` times, password authentication will be turned off on the account until having gone through the process of having its password reset.

.. seealso::

   :ref:`user-rate`

.. _rate-ip:

IP address for rate limiting
++++++++++++++++++++++++++++

The rate limiting is based on the client IP address, obtained from HTTP headers.
Change them if your Weblate instance is running behind a reverse proxy to make it work.

.. seealso::

    :setting:`IP_BEHIND_REVERSE_PROXY`,
    :setting:`IP_PROXY_HEADER`,
    :setting:`IP_PROXY_OFFSET`
