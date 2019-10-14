Optional Weblate modules
========================

Weblate comes with several optional modules which might be useful for your
setup.

.. _git-exporter:

Git exporter
------------

.. versionadded:: 2.10

The Git exporter provides you read only access to the underlying Git repository
using HTTP.

Installation
++++++++++++

To install, simply add ``weblate.gitexport`` to installed applications in
:file:`settings.py`:

.. code-block:: python

    INSTALLED_APPS += (
        'weblate.gitexport',
    )

After installing, you need to migrate your database so that existing
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


.. _billing:

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

The billing module additionally allows project admins to create new projects
and components without being superusers (see :ref:`adding-projects`). This is
possible when following conditions are met:

* The billing is in it's configured limits (any overusage results in blocking
  of project/component creation) and paid (if it's price is non zero)
* The user is admin of existing project with billing or user is owner of
  billing (the latter is necessary when creating new billing for users to be
  able to import new projects).

Upon project creation user is able to choose which billing should be charged
for the project in case he has access to more of them.


.. _legal:

Legal
-----

.. versionadded:: 2.15

Legal module is used on `Hosted Weblate <https://weblate.org/hosting/>`_
and is used to provide required legal documents. It comes with blank documents
and you are expected to provide following templates with the documents:

:file:`legal/documents/tos.html`
   Terms of service document
:file:`legal/documents/privacy.html`
   Privacy policy document
:file:`legal/documents/summary.html`
   Short overview of terms of service and privacy policy

.. note::

    You can find legal documents for the Hosted Weblate service in separate Git repository
    <https://github.com/WeblateOrg/hosted/tree/master/wlhosted/legal/templates/legal/documents>.

    Most likely these will not be directly usable for you, but you might want
    to use them as a starting point and adjust them to match your use case.

Installation
++++++++++++

To install, simply add ``weblate.legal`` to installed applications in
:file:`settings.py`:

.. code-block:: python

    INSTALLED_APPS += (
        'weblate.legal',
    )

    # Optionals:

    # Social auth pipeline to confirm TOS on registration/login
    SOCIAL_AUTH_PIPELINE += (
        'weblate.legal.pipeline.tos_confirm',
    )

    # Middleware to enforce TOS confirmation of logged in users
    MIDDLEWARE += [
        'weblate.legal.middleware.RequireTOSMiddleware',
    ]

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

Weblate comes with built in support for showing user avatars based on e-mails.
This can be disabled using :setting:`ENABLE_AVATARS`. The avatars are
downloaded and cached server side to reduce information leaks to the sites
serving them.

Weblate currently supports single backend:

* `Gravatar <https://gravatar.com/>`_

.. seealso::

   :ref:`production-cache-avatar`,
   :setting:`AVATAR_URL_PREFIX`,
   :setting:`ENABLE_AVATARS`

Spam protection
---------------

Optionally Weblate can be protected against suggestion spamming by
unauthenticated users through `akismet.com <https://akismet.com/>`_
service.

To enable this, you need to install `akismet` Python module and configure
Akismet API key.

.. seealso::

    :setting:`AKISMET_API_KEY`


.. _gpg-sign:

Signing Git commits by GnuPG
----------------------------

.. versionadded:: 3.1

Weblate allows you to sign all commits by it's GnuPG key. To configure this,
you need to enable :setting:`WEBLATE_GPG_IDENTITY`. Weblate will generate GnuPG
key when needed and will use it to sign all translation commits.

This feature needs GnuPG 2.1 or newer installed.

You can find the key in the :setting:`DATA_DIR` and the public key is shown on
the about page:

.. image:: /images/about-gpg.png

Alternatively you can also import existing keys into Weblate, just set
``HOME=$DATA_DIR/home`` when invoking gpg.

.. seealso::

    :setting:`WEBLATE_GPG_IDENTITY`

.. _rate-limit:

Rate limiting
-------------

.. versionchanged:: 3.2

      The rate limiting now accepts more fine grained configuration.

Several operations in Weblate are rate limited. At most
:setting:`RATELIMIT_ATTEMPTS` attempts are allowed within
:setting:`RATELIMIT_WINDOW` seconds. The user is then blocked
for :setting:`RATELIMIT_LOCKOUT`. There are also per scope variants of those
settings, eg. ``RATELIMIT_CONTACT_ATTEMPTS`` or
``RATELIMIT_TRANSLATE_ATTEMPTS``, see table below for full list of available
scopes.

Following operations are subject to rate limiting:

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

Additionally if there are more than :setting:`AUTH_LOCK_ATTEMPTS` failed
authentication attempts on one account, this account password authentication is
disabled and it's not possible to login until user asks for password reset.

.. seealso::

   :ref:`user-rate`

.. _rate-ip:

IP address for rate limiting
++++++++++++++++++++++++++++

The rate limiting is based on client IP address. This is obtained from HTTP
headers and you will have to change configuration in the event Weblate is
running behind reverse proxy to work it properly.

.. seealso::

    :setting:`IP_BEHIND_REVERSE_PROXY`,
    :setting:`IP_PROXY_HEADER`,
    :setting:`IP_PROXY_OFFSET`
