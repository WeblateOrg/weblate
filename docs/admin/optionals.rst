Optional Weblate modules
========================

Several optional modules are available for your setup.

.. _git-exporter:

Git exporter
------------

.. versionadded:: 2.10

Provides you read-only access to the underlying Git repository using HTTP(S).

Installation
++++++++++++

1. Add ``weblate.gitexport`` to installed apps in :file:`settings.py`:

.. code-block:: python

    INSTALLED_APPS += ("weblate.gitexport",)

2. Export existing repositories by migrating your database after installation:

.. code-block:: sh

    weblate migrate

Usage
+++++

The module automatically hooks into Weblate and sets the exported repository URL in
the :ref:`component`.
The repositories are accessible under the ``/git/`` part of the Weblate URL, for example
``https://example.org/git/weblate/main/``.

Repositories for publicly available projects can be cloned without authentication:

.. code-block:: sh

    git clone 'https://example.org/git/weblate/main/'

Access to browse the repositories with restricted access (with `Private`
:ref:`access control <acl>` or when :setting:`REQUIRE_LOGIN` is enabled)
requires an API token which can be obtained in your
:ref:`user profile <user-profile>`:

.. code-block:: sh

    git clone 'https://user:KEY@example.org/git/weblate/main/'

.. hint::

   By default members or :guilabel:`Users` group and anonymous user have access
   to the repositories for public projects via :guilabel:`Access repository`
   and :guilabel:`Power user` roles.


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

    INSTALLED_APPS += ("weblate.billing",)

2. Run the database migration to optionally install additional database structures for the module:

.. code-block:: sh

    weblate migrate

Usage
+++++

After installation you can control billing in the admin interface. Users with
billing enabled will get new :guilabel:`Billing` tab in their
:ref:`user-profile`.

The billing module additionally allows project admins to create new projects
and components without being superusers (see :ref:`adding-projects`). This is
possible when following conditions are met:

* The billing is in its configured limits (any overusage results in blocking
  of project/component creation) and paid (if its price is non zero)
* The user is admin of existing project with billing or user is owner of
  billing (the latter is necessary when creating new billing for users to be
  able to import new projects).

Upon project creation user is able to choose which billing should be charged
for the project in case he has access to more of them.


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

    Legal documents for the Hosted Weblate service are available in this Git repository
    <https://github.com/WeblateOrg/wllegal/tree/main/wllegal/templates/legal/documents>.

    Most likely these will not be directly usable to you, but might come in handy
    as a starting point if adjusted to meet your needs.

Installation
++++++++++++

1. Add ``weblate.legal`` to installed apps in
:file:`settings.py`:

.. code-block:: python

    INSTALLED_APPS += ("weblate.legal",)

    # Optional:

    # Social auth pipeline to confirm TOS upon registration/subsequent sign in
    SOCIAL_AUTH_PIPELINE += ("weblate.legal.pipeline.tos_confirm",)

    # Middleware to enforce TOS confirmation of signed in users
    MIDDLEWARE += [
        "weblate.legal.middleware.RequireTOSMiddleware",
    ]

2. Run the database migration to optionally install additional database structures for the module:

.. code-block:: sh

    weblate migrate

3. Edit the legal documents in the :file:`weblate/legal/templates/legal/` folder to match your service.

Usage
+++++

After installation and editing, the legal documents are shown in the Weblate UI.

.. _avatars:

Avatars
-------

Avatars are downloaded and cached server-side to reduce information leaks to the sites serving them
by default. The built-in support for fetching avatars from e-mails addresses configured for it can be
turned off using :setting:`ENABLE_AVATARS`.

Weblate currently supports:

* `Gravatar <https://gravatar.com/>`_
* `Libravatar <https://www.libravatar.org/>`_

.. seealso::

   :ref:`production-cache-avatar`,
   :setting:`AVATAR_URL_PREFIX`,
   :setting:`ENABLE_AVATARS`

.. _spam-protection:

Spam protection
---------------

You can protect against spamming by users by using the `Akismet
<https://akismet.com/>`_ service.

1. Install the `akismet` Python module (this is already included in the official Docker image).
2. Obtain the Akismet API key.
3. Store it as :setting:`AKISMET_API_KEY` or :envvar:`WEBLATE_AKISMET_API_KEY` in Docker.

Following content is sent to Akismet for checking:

* Suggestions from unauthenticated users
* Project and component descriptions and links

.. note::

   This (among other things) relies on IP address of the client, please see
   :ref:`reverse-proxy` for properly configuring that.

.. seealso::

    :ref:`reverse-proxy`,
    :setting:`AKISMET_API_KEY`,
    :envvar:`WEBLATE_AKISMET_API_KEY`


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

.. versionchanged:: 4.6

      The rate limiting no longer applies to superusers.

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
| Password authentication on sign in| ``LOGIN``          |                5 |              300 |            600 |
+-----------------------------------+--------------------+------------------+------------------+----------------+
| Sitewide search                   | ``SEARCH``         |                6 |               60 |             60 |
+-----------------------------------+--------------------+------------------+------------------+----------------+
| Translating                       | ``TRANSLATE``      |               30 |               60 |            600 |
+-----------------------------------+--------------------+------------------+------------------+----------------+
| Adding to glossary                | ``GLOSSARY``       |               30 |               60 |            600 |
+-----------------------------------+--------------------+------------------+------------------+----------------+
| Starting translation into a new   | ``LANGUAGE``       |                2 |              300 |            600 |
| language                          |                    |                  |                  |                |
+-----------------------------------+--------------------+------------------+------------------+----------------+

If a user fails to log in :setting:`AUTH_LOCK_ATTEMPTS` times, password authentication will be turned off on the account until having gone through the process of having its password reset.

The settings can be also applied in the Docker container by adding ``WEBLATE_`` prefix to the setting name, for example :setting:`RATELIMIT_ATTEMPTS` becomes :envvar:`WEBLATE_RATELIMIT_ATTEMPTS`.

The API has separate rate limiting settings, see :ref:`api-rate`.

.. seealso::

   :ref:`user-rate`,
   :ref:`reverse-proxy`,
   :ref:`api-rate`

Fedora Messaging integration
----------------------------

Fedora Messaging is AMQP-based publisher for all changes happening in Weblate.
You can hook additional services on changes happening in Weblate using this.

The Fedora Messaging integration is available as a separate Python module
``weblate-fedora-messaging``. Please see
<https://github.com/WeblateOrg/fedora_messaging/> for setup instructions.
