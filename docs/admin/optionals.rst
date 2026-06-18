Optional Weblate modules
========================

Several optional modules are available for your setup.

.. _git-exporter:

Git exporter
------------

Provides you read-only access to the underlying Git repository using HTTP(S).

Installation
++++++++++++

1. Add ``weblate.gitexport`` to installed apps in :file:`settings.py`:

   .. code-block:: python

       INSTALLED_APPS += ("weblate.gitexport",)

2. Export existing repositories by migrating your database after installation:

   .. code-block:: sh

       weblate migrate

.. hint::

   Git exporter is turned on in our official Docker image. To turn it of, use:

   .. code-block:: sh

      WEBLATE_REMOVE_APPS=weblate.gitexport

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

.. include:: /snippets/git-export-lfs-note.rst

.. hint::

   By default members of :guilabel:`Users` group and anonymous user have access
   to the repositories for public projects via :guilabel:`Access repository`
   and :guilabel:`Power user` roles.


.. _billing:

Billing
-------

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

Billing plan creation and assignment
++++++++++++++++++++++++++++++++++++

You first need to create a billing plan to activate billing. Navigate to the `Administration` section (represented by the wrench icon) and open the `Tools` screen. From there, proceed to the `Django admin interface`.

In the Django admin interface, locate the `BILLING` section and add a billing plan. For instance, you can add a `Free` plan with no cost.

If you wish to assign a billing plan to an existing project, this can also be done within the `Django admin interface` using the `Customer billings` option.

Lastly, the `Django admin interface` provides an `Invoice` option for logging your customer payments.

Usage
+++++

After installation you can control billing in the admin interface. Users with
billing enabled will get new :guilabel:`Billing` tab in their
:ref:`user-profile`.

The billing module additionally allows users to create new projects and
components without being superusers (see :ref:`adding-projects`). This is
possible when following conditions are met:

* The billing is in its configured limits (any overusage results in blocking
  of project/component creation) and paid (if its price is non zero)
* The user has :guilabel:`Add projects to workspace` permission for the
  workspace covered by the billing plan.

Upon project creation user is able to choose which workspace should contain the
project. Projects created in a workspace with billing count against the billing
plan assigned to that workspace. Users with the :guilabel:`Edit workspace
settings` permission can view and pay the billing plan; billing notification
e-mails are sent to these users. See :ref:`workspace-billing` for details.


.. _legal:

Legal module
------------

This is used on `Hosted Weblate <https://weblate.org/hosting/>`_ to provide required
legal documents. It comes provided with blank documents, and you are expected to fill out the
following templates in the documents:

:file:`legal/documents/tos.html`
   Terms of service document
:file:`legal/documents/privacy.html`
   Privacy policy document
:file:`legal/documents/summary.html`
   Short overview of the terms of service and privacy policy
:file:`legal/documents/contracts.html`
   Subcontractor information

The legal module embeds these templates inside Weblate and uses
:file:`legal/documents/tos.html` for terms of service confirmation. This is
separate from :setting:`LEGAL_URL` and :setting:`PRIVACY_URL`, which are meant
for linking to externally hosted legal documents from the footer when the
legal module is not enabled. When the legal module is enabled, Weblate links to
the internal legal pages by default.

On changing the terms of service documents, please adjust
:setting:`LEGAL_TOS_DATE` so that users are forced to agree with the updated
documents.

.. note::

    Legal documents for the Hosted Weblate service operated by Weblate s.r.o.
    are available in this Git repository:
    <https://github.com/WeblateOrg/wllegal/tree/main/wllegal/templates/legal/documents>.

    The bundled terms of service and related legal documents are specific to
    that service and are not intended for general use. They might still come
    in handy as a starting point if adjusted to meet your needs.

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

.. hint::

   In Docker deployments, enable the legal module using
   :envvar:`WEBLATE_LEGAL_INTEGRATION` instead of editing
   :file:`settings.py`. Use ``tos-confirm`` to enable the legal module and
   terms of service confirmation enforcement, or ``wllegal`` to additionally
   load the hosted legal document templates used by services operated by
   Weblate s.r.o. These templates are not intended for general use. To provide
   your own templates in Docker, place them in
   :file:`/app/data/python/customize/templates/legal/documents`, see
   :ref:`docker-static-override`.

   Recreate the Docker container after changing environment variables, for
   example using :program:`docker compose up -d`. Restarting an existing
   container does not apply changed environment values.

Usage
+++++

After installation and editing, the legal documents are shown in the Weblate UI.

The legal document templates are regular Django templates. Text is translated
only when you use Django translation tags such as ``{% translate %}`` or
``{% blocktranslate %}``; plain HTML text is shown as written.

Legal pages and the sign-in and registration overview provide ``terms_url`` and
``privacy_url`` variables for linking to the terms of service and privacy
policy documents.

By default, legal document wrappers use the ``tos`` CSS class. This class
automatically numbers ``h2`` headings, paragraphs with ``item``, ``subitem``,
or ``subsubitem`` classes, and top-level ordered list items. If your legal
text already contains numbering, set :setting:`LEGAL_DOCUMENT_CSS_CLASS` to an
empty string to disable this styling.

Use :setting:`LEGAL_HIDDEN_DOCUMENTS` to hide optional legal pages such as
subcontractors from the legal menu. Hidden pages return a 404 response when
requested directly. If ``terms`` or ``privacy`` is hidden, links using
``terms_url`` or ``privacy_url`` fall back to :setting:`LEGAL_URL` or
:setting:`PRIVACY_URL` when configured, otherwise the link is omitted.

To use externally hosted legal documents with terms confirmation, configure
:setting:`LEGAL_HIDDEN_DOCUMENTS` to hide ``terms`` and ``privacy`` and set
:setting:`LEGAL_URL` and :setting:`PRIVACY_URL`. The confirmation page then
links to those external documents without requiring a
:file:`legal/documents/tos.html` template override.

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

   * :ref:`production-cache-avatar`
   * :setting:`AVATAR_URL_PREFIX`
   * :setting:`ENABLE_AVATARS`

.. _cdn-server-security:

Localization CDN
----------------

The :ref:`addon-weblate.cdn.cdnjs` and :ref:`addon-weblate.cdn.files` add-ons
write files to :setting:`LOCALIZE_CDN_PATH`; Weblate does not serve them.
Configure the web server or CDN serving :setting:`LOCALIZE_CDN_URL` as a
public, read-only static file host.

Treat every published CDN file as public. The add-on specific UUID in the URL
is not an access-control mechanism. Do not enable CDN add-ons for components
that contain private strings, unreleased product text, customer data, internal
URLs, API examples, repository paths, translator comments, or file-format
metadata that should not be exposed.

The :ref:`addon-weblate.cdn.files` add-on publishes raw translation files in
formats supported by Weblate. Some formats can be interpreted by browsers or
other clients as HTML, SVG, XML, JavaScript, YAML, or application-specific
configuration. Serve the CDN from a dedicated domain that is separate from
Weblate and from the application consuming the translations. Do not share
authentication cookies with the CDN domain.

Recommended server configuration:

* Serve only the directory configured by :setting:`LOCALIZE_CDN_PATH`; do not
  expose Weblate repositories, backups, media, configuration, or the whole data
  directory.
* Disable directory listing.
* Use HTTPS and make the CDN host read-only from the web server.
* Send :http:header:`X-Content-Type-Options` with ``nosniff``.
* Configure conservative MIME types. Serve unknown translation formats as
  :mimetype:`text/plain` or :mimetype:`application/octet-stream`; only serve
  :file:`weblate.js` as JavaScript.
* For raw translation formats that are not intended to be rendered in a
  browser, consider adding :http:header:`Content-Disposition` with
  ``attachment``.
* Configure ``Access-Control-Allow-Origin`` only for sites that need browser
  access to the files.
* Set cache lifetimes that match your update expectations, and purge CDN caches
  when stale translations must disappear quickly.

The following nginx snippet serves only the configured CDN directory and
applies conservative defaults for raw translation files:

.. literalinclude:: ../../weblate/examples/weblate.nginx.cdn.conf
   :language: nginx
   :caption: weblate/examples/weblate.nginx.cdn.conf

.. seealso::

   * :ref:`weblate-cdn`
   * :setting:`LOCALIZE_CDN_URL`
   * :setting:`LOCALIZE_CDN_PATH`

.. _gpg-sign:

Signing Git commits with GnuPG
------------------------------

All commits can be signed by the GnuPG key of the Weblate instance.

* Turn on :setting:`WEBLATE_GPG_IDENTITY`. (Weblate will generate a GnuPG
  key when needed and will use it to sign all translation commits.)

  This feature needs GnuPG 2.1 or newer installed.

  You can find the key in the :setting:`DATA_DIR` and the public key is shown
  on the "About" page:

  .. image:: /screenshots/about-gpg.webp

* Alternatively you can also import existing keys into Weblate, just set
  ``HOME=$DATA_DIR/home`` when invoking gpg.

.. hint::

   The key material is cached by Weblate for a long period. In case you let
   Weblate generate a key with :setting:`WEBLATE_GPG_IDENTITY` and then import
   key with the same identity to use an existing key, purging redis cache is
   recommended to see the effect of such change.


.. note::

   When sharing :setting:`DATA_DIR` between multiple hosts, please follow instructions
   at https://wiki.gnupg.org/NFS to make GnuPG signing work reliably.

.. seealso::

    :setting:`WEBLATE_GPG_IDENTITY`

.. _rate-limit:

Rate limiting
-------------

.. versionchanged:: 4.6

      The rate limiting no longer applies to signed in superusers.

Several operations in Weblate are rate limited. Rate limits are evaluated
independently for each scope. At most :setting:`RATELIMIT_ATTEMPTS` attempts are
allowed within :setting:`RATELIMIT_WINDOW` seconds in one scope. That scope is
then blocked for :setting:`RATELIMIT_LOCKOUT`; Weblate does not turn this into a
sitewide temporary IP ban. Exceeding one scope, such as ``TRANSLATE`` or
``SEARCH``, does not by itself block unrelated scopes such as ``LOGIN`` or
``SECOND_FACTOR``. There are also settings specific to scopes, for example
``RATELIMIT_CONTACT_ATTEMPTS`` or ``RATELIMIT_TRANSLATE_ATTEMPTS``. The table
below is a full list of available scopes.

The following operations are subject to rate limiting:

+-----------------------------------+--------------------+------------------+------------------+----------------+
| Name                              | Scope              | Allowed attempts | Ratelimit window | Lockout period |
+===================================+====================+==================+==================+================+
| Registration                      | ``REGISTRATION``   | 5                | 300              | 600            |
+-----------------------------------+--------------------+------------------+------------------+----------------+
| Sending message to admins         | ``MESSAGE``        | 2                | 300              | 600            |
+-----------------------------------+--------------------+------------------+------------------+----------------+
| Password authentication on sign-in| ``LOGIN``          | 5                | 300              | 600            |
+-----------------------------------+--------------------+------------------+------------------+----------------+
| Second-factor authentication      | ``SECOND_FACTOR``  | 5                | 300              | 600            |
+-----------------------------------+--------------------+------------------+------------------+----------------+
| Sitewide search                   | ``SEARCH``         | 6                | 60               | 60             |
+-----------------------------------+--------------------+------------------+------------------+----------------+
| Translating                       | ``TRANSLATE``      | 30               | 60               | 600            |
+-----------------------------------+--------------------+------------------+------------------+----------------+
| Adding to glossary                | ``GLOSSARY``       | 30               | 60               | 600            |
+-----------------------------------+--------------------+------------------+------------------+----------------+
| Starting translation into a new   | ``LANGUAGE``       | 2                | 300              | 600            |
| language                          |                    |                  |                  |                |
+-----------------------------------+--------------------+------------------+------------------+----------------+
| Creating new project              | ``PROJECT``        | 5                | 600              | 600            |
+-----------------------------------+--------------------+------------------+------------------+----------------+

Within each scope, the rate limiting is based on sessions when user is signed in
and on IP address if not.

If a user fails to sign in :setting:`AUTH_LOCK_ATTEMPTS` times, password authentication will be turned off on the account until having gone through the process of having its password reset.

The settings can be also applied in the Docker container by adding ``WEBLATE_`` prefix to the setting name, for example :setting:`RATELIMIT_ATTEMPTS` becomes :envvar:`WEBLATE_RATELIMIT_ATTEMPTS`.

The API has separate rate limiting settings, see :ref:`api-rate`.

.. seealso::

   * :ref:`user-rate`
   * :ref:`reverse-proxy`
   * :ref:`api-rate`
