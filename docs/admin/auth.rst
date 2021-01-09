Authentication
==============

User registration
-----------------

The default setup for Weblate is to use python-social-auth, a form on the website
to handle registration of new users. After confirming their e-mail a new user can
contribute or authenticate by using one of the third party services.

You can also turn off registration of new users using
:setting:`REGISTRATION_OPEN`.

The authentication attempts are subject to :ref:`rate-limit`.


Authentication backends
-----------------------

The built-in solution of Django is used for authentication,
including various social options to do so.
Using it means you can import the user database of other Django-based projects
(see :ref:`pootle-migration`).

Django can additionally be set up to authenticate against other means too.

.. seealso::

   :ref:`docker-auth` describes how to configure authentication in the official
   Docker image.

Social authentication
---------------------

Thanks to :doc:`psa:index`, Weblate support authentication using many third
party services such as GitLab, Ubuntu, Fedora, etc.

Please check their documentation for generic configuration instructions
in :doc:`psa:configuration/django`.

.. note::

    By default, Weblate relies on third-party authentication services to
    provide a validated e-mail address. If some of the services you want to use
    don't support this, please enforce e-mail validation on the Weblate side
    by configuring FORCE_EMAIL_VALIDATION for them. For example:

    .. code-block:: python

        SOCIAL_AUTH_OPENSUSE_FORCE_EMAIL_VALIDATION = True

    .. seealso:: :doc:`psa:pipeline`

Enabling individual backends is quite easy, it's just a matter of adding an entry to
the :setting:`django:AUTHENTICATION_BACKENDS` setting and possibly adding keys needed for a given
authentication method. Please note that some backends do not provide user e-mail by
default, you have to request it explicitly, otherwise Weblate will not be able
to properly credit contributions users make.

.. seealso::

    :doc:`Python Social Auth backend <psa:backends/index>`

OpenID authentication
~~~~~~~~~~~~~~~~~~~~~

For OpenID-based services it's usually just a matter of enabling them. The following
section enables OpenID authentication for OpenSUSE, Fedora and Ubuntu:

.. code-block:: python

    # Authentication configuration
    AUTHENTICATION_BACKENDS = (
        "social_core.backends.email.EmailAuth",
        "social_core.backends.suse.OpenSUSEOpenId",
        "social_core.backends.ubuntu.UbuntuOpenId",
        "social_core.backends.fedora.FedoraOpenId",
        "weblate.accounts.auth.WeblateUserBackend",
    )

.. seealso::

   :doc:`psa:backends/openid`

.. _github_auth:

GitHub authentication
~~~~~~~~~~~~~~~~~~~~~

You need to register an OAuth application on GitHub and then tell Weblate all its secrets:

.. code-block:: python

    # Authentication configuration
    AUTHENTICATION_BACKENDS = (
        "social_core.backends.github.GithubOAuth2",
        "social_core.backends.email.EmailAuth",
        "weblate.accounts.auth.WeblateUserBackend",
    )

    # Social auth backends setup
    SOCIAL_AUTH_GITHUB_KEY = "GitHub Client ID"
    SOCIAL_AUTH_GITHUB_SECRET = "GitHub Client Secret"
    SOCIAL_AUTH_GITHUB_SCOPE = ["user:email"]

The GitHub should be configured to have callback URL as
``https://example.com/accounts/complete/github/``.

.. include:: /snippets/oauth-site.rst

.. seealso::

    :doc:`psa:backends/github`

.. _bitbucket_auth:

Bitbucket authentication
~~~~~~~~~~~~~~~~~~~~~~~~

You need to register an application on Bitbucket and then tell Weblate all its secrets:

.. code-block:: python

    # Authentication configuration
    AUTHENTICATION_BACKENDS = (
        "social_core.backends.bitbucket.BitbucketOAuth",
        "social_core.backends.email.EmailAuth",
        "weblate.accounts.auth.WeblateUserBackend",
    )

    # Social auth backends setup
    SOCIAL_AUTH_BITBUCKET_KEY = "Bitbucket Client ID"
    SOCIAL_AUTH_BITBUCKET_SECRET = "Bitbucket Client Secret"
    SOCIAL_AUTH_BITBUCKET_VERIFIED_EMAILS_ONLY = True

.. include:: /snippets/oauth-site.rst

.. seealso::

   :doc:`psa:backends/bitbucket`

.. _google_auth:

Google OAuth 2
~~~~~~~~~~~~~~

To use Google OAuth 2, you need to register an application on
<https://console.developers.google.com/> and enable the Google+ API.

The redirect URL is ``https://WEBLATE SERVER/accounts/complete/google-oauth2/``

.. code-block:: python

    # Authentication configuration
    AUTHENTICATION_BACKENDS = (
        "social_core.backends.google.GoogleOAuth2",
        "social_core.backends.email.EmailAuth",
        "weblate.accounts.auth.WeblateUserBackend",
    )

    # Social auth backends setup
    SOCIAL_AUTH_GOOGLE_OAUTH2_KEY = "Client ID"
    SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET = "Client secret"

.. include:: /snippets/oauth-site.rst

.. seealso::

   :doc:`psa:backends/google`

.. _facebook_auth:

Facebook OAuth 2
~~~~~~~~~~~~~~~~

As per usual with OAuth 2 services, you need to register your application with
Facebook. Once this is done, you can set up Weblate to use it:

The redirect URL is ``https://WEBLATE SERVER/accounts/complete/facebook/``

.. code-block:: python

    # Authentication configuration
    AUTHENTICATION_BACKENDS = (
        "social_core.backends.facebook.FacebookOAuth2",
        "social_core.backends.email.EmailAuth",
        "weblate.accounts.auth.WeblateUserBackend",
    )

    # Social auth backends setup
    SOCIAL_AUTH_FACEBOOK_KEY = "key"
    SOCIAL_AUTH_FACEBOOK_SECRET = "secret"
    SOCIAL_AUTH_FACEBOOK_SCOPE = ["email", "public_profile"]

.. include:: /snippets/oauth-site.rst

.. seealso::

   :doc:`psa:backends/facebook`


.. _gitlab_auth:

GitLab OAuth 2
~~~~~~~~~~~~~~

For using GitLab OAuth 2, you need to register an application on
<https://gitlab.com/profile/applications>.

The redirect URL is ``https://WEBLATE SERVER/accounts/complete/gitlab/`` and
ensure you mark the `read_user` scope.

.. code-block:: python

    # Authentication configuration
    AUTHENTICATION_BACKENDS = (
        "social_core.backends.gitlab.GitLabOAuth2",
        "social_core.backends.email.EmailAuth",
        "weblate.accounts.auth.WeblateUserBackend",
    )

    # Social auth backends setup
    SOCIAL_AUTH_GITLAB_KEY = "Application ID"
    SOCIAL_AUTH_GITLAB_SECRET = "Secret"
    SOCIAL_AUTH_GITLAB_SCOPE = ["read_user"]

    # If you are using your own GitLab
    # SOCIAL_AUTH_GITLAB_API_URL = 'https://gitlab.example.com/'

.. include:: /snippets/oauth-site.rst

.. seealso::

   :doc:`psa:backends/gitlab`

.. _azure-auth:

Microsoft Azure Active Directory
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Weblate can be configured to use common or specific tenants for authentication.

The redirect URL is ``https://WEBLATE SERVER/accounts/complete/azuread-oauth2/``
for common and ``https://WEBLATE SERVER/accounts/complete/azuread-tenant-oauth2/``
for tenant-specific authentication.

.. code-block:: python

    # Azure AD common

    # Authentication configuration
    AUTHENTICATION_BACKENDS = (
        "social_core.backends.azuread.AzureADOAuth2",
        "social_core.backends.email.EmailAuth",
        "weblate.accounts.auth.WeblateUserBackend",
    )

    # OAuth2 keys
    SOCIAL_AUTH_AZUREAD_OAUTH2_KEY = ""
    SOCIAL_AUTH_AZUREAD_OAUTH2_SECRET = ""

.. code-block:: python

    # Azure AD Tenant

    # Authentication configuration
    AUTHENTICATION_BACKENDS = (
        "social_core.backends.azuread_tenant.AzureADTenantOAuth2",
        "social_core.backends.email.EmailAuth",
        "weblate.accounts.auth.WeblateUserBackend",
    )

    # OAuth2 keys
    SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_KEY = ""
    SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_SECRET = ""
    # Tenant ID
    SOCIAL_AUTH_AZUREAD_TENANT_OAUTH2_TENANT_ID = ""

.. include:: /snippets/oauth-site.rst

.. seealso::

   :doc:`psa:backends/azuread`

.. _slack-auth:

Slack
~~~~~

For using Slack OAuth 2, you need to register an application on
<https://api.slack.com/apps>.

The redirect URL is ``https://WEBLATE SERVER/accounts/complete/slack/``.

.. code-block:: python

    # Authentication configuration
    AUTHENTICATION_BACKENDS = (
        "social_core.backends.slack.SlackOAuth2",
        "social_core.backends.email.EmailAuth",
        "weblate.accounts.auth.WeblateUserBackend",
    )

    # Social auth backends setup
    SOCIAL_AUTH_SLACK_KEY = ""
    SOCIAL_AUTH_SLACK_SECRET = ""

.. include:: /snippets/oauth-site.rst

.. seealso::

   :doc:`psa:backends/slack`

Turning off password authentication
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

E-mail and password authentication can be turned off by removing
``social_core.backends.email.EmailAuth`` from
:setting:`django:AUTHENTICATION_BACKENDS`. Always keep
``weblate.accounts.auth.WeblateUserBackend`` there, it is needed for core
Weblate functionality.

.. tip::

   You can still use password authentication for the admin interface, for users you
   manually create there. Just navigate to ``/admin/``.

For example authentication using only the openSUSE Open ID provider can be achieved
using the following:

.. code-block:: python

    # Authentication configuration
    AUTHENTICATION_BACKENDS = (
        "social_core.backends.suse.OpenSUSEOpenId",
        "weblate.accounts.auth.WeblateUserBackend",
    )

Password authentication
-----------------------

The default :file:`settings.py` comes with a reasonable set of
:setting:`django:AUTH_PASSWORD_VALIDATORS`:

* Passwords can't be too similar to your other personal info.
* Passwords must contain at least 10 characters.
* Passwords can't be a commonly used password.
* Passwords can't be entirely numeric.
* Passwords can't consist of a single character or only whitespace.
* Passwords can't match a password you have used in the past.

You can customize this setting to match your password policy.

Additionally you can also install
`django-zxcvbn-password <https://pypi.org/project/django-zxcvbn-password/>`_
which gives quite realistic estimates of password difficulty and allows rejecting
passwords below a certain threshold.

.. _saml-auth:

SAML authentication
-------------------

.. versionadded:: 4.1.1

Please follow the Python Social Auth instructions for configuration. Notable differences:

* Weblate supports single IDP which has to be called ``weblate`` in
  ``SOCIAL_AUTH_SAML_ENABLED_IDPS``.
* The SAML XML metadata URL is ``/accounts/metadata/saml/``.
* Following settings are automatically filled in:
  ``SOCIAL_AUTH_SAML_SP_ENTITY_ID``, ``SOCIAL_AUTH_SAML_TECHNICAL_CONTACT``,
  ``SOCIAL_AUTH_SAML_SUPPORT_CONTACT``

Example configuration:

.. code-block::

    # Authentication configuration
    AUTHENTICATION_BACKENDS = (
        "social_core.backends.email.EmailAuth",
        "social_core.backends.saml.SAMLAuth",
        "weblate.accounts.auth.WeblateUserBackend",
    )

    # Social auth backends setup
    SOCIAL_AUTH_SAML_SP_PUBLIC_CERT = "-----BEGIN CERTIFICATE-----"
    SOCIAL_AUTH_SAML_SP_PRIVATE_KEY = "-----BEGIN PRIVATE KEY-----"
    SOCIAL_AUTH_SAML_ENABLED_IDPS = {
        "weblate": {
            "entity_id": "https://idp.testshib.org/idp/shibboleth",
            "url": "https://idp.testshib.org/idp/profile/SAML2/Redirect/SSO",
            "x509cert": "MIIEDjCCAvagAwIBAgIBADA ... 8Bbnl+ev0peYzxFyF5sQA==",
            "attr_name": "full_name",
            "attr_username": "username",
            "attr_email": "email",
        }
    }

.. seealso::

   :ref:`Configuring SAML in Docker <docker-saml>`,
   :doc:`psa:backends/saml`

.. _ldap-auth:

LDAP authentication
-------------------

LDAP authentication can be best achieved using the `django-auth-ldap` package. You
can install it via usual means:

.. code-block:: sh

    # Using PyPI
    pip install django-auth-ldap>=1.3.0

    # Using apt-get
    apt-get install python-django-auth-ldap

.. warning::

    With django-auth-ldap older than 1.3.0 the :ref:`autogroup` will not work
    properly for newly created users.

.. note::

   There are some incompatibilities in the Python LDAP 3.1.0 module, which might
   prevent you from using that version. If you get error `AttributeError:
   'module' object has no attribute '_trace_level'
   <https://github.com/python-ldap/python-ldap/issues/226>`_, downgrading
   python-ldap to 3.0.0 might help.

Once you have the package installed, you can hook it into the Django authentication:

.. code-block:: python

    # Add LDAP backed, keep Django one if you want to be able to sign in
    # even without LDAP for admin account
    AUTHENTICATION_BACKENDS = (
        "django_auth_ldap.backend.LDAPBackend",
        "weblate.accounts.auth.WeblateUserBackend",
    )

    # LDAP server address
    AUTH_LDAP_SERVER_URI = "ldaps://ldap.example.net"

    # DN to use for authentication
    AUTH_LDAP_USER_DN_TEMPLATE = "cn=%(user)s,o=Example"
    # Depending on your LDAP server, you might use a different DN
    # like:
    # AUTH_LDAP_USER_DN_TEMPLATE = 'ou=users,dc=example,dc=com'

    # List of attributes to import from LDAP upon sign in
    # Weblate stores full name of the user in the full_name attribute
    AUTH_LDAP_USER_ATTR_MAP = {
        "full_name": "name",
        # Use the following if your LDAP server does not have full name
        # Weblate will merge them later
        # 'first_name': 'givenName',
        # 'last_name': 'sn',
        # Email is required for Weblate (used in VCS commits)
        "email": "mail",
    }

    # Hide the registration form
    REGISTRATION_OPEN = False

.. note::

    You should remove ``'social_core.backends.email.EmailAuth'`` from the
    :setting:`django:AUTHENTICATION_BACKENDS` setting, otherwise users will be able to set
    their password in Weblate, and authenticate using that. Keeping
    ``'weblate.accounts.auth.WeblateUserBackend'`` is still needed in order to
    make permissions and facilitate anonymous users. It will also allow you
    to sign in using a local admin account, if you have created it (e.g. by using
    :djadmin:`createadmin`).

Using bind password
~~~~~~~~~~~~~~~~~~~

If you can not use direct bind for authentication, you will need to use search,
and provide a user to bind for the search. For example:

.. code-block:: python

   import ldap
   from django_auth_ldap.config import LDAPSearch

   AUTH_LDAP_BIND_DN = ""
   AUTH_LDAP_BIND_PASSWORD = ""
   AUTH_LDAP_USER_SEARCH = LDAPSearch(
       "ou=users,dc=example,dc=com", ldap.SCOPE_SUBTREE, "(uid=%(user)s)"
   )

Active Directory integration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    import ldap
    from django_auth_ldap.config import LDAPSearch, NestedActiveDirectoryGroupType

    AUTH_LDAP_BIND_DN = "CN=ldap,CN=Users,DC=example,DC=com"
    AUTH_LDAP_BIND_PASSWORD = "password"

    # User and group search objects and types
    AUTH_LDAP_USER_SEARCH = LDAPSearch(
        "CN=Users,DC=example,DC=com", ldap.SCOPE_SUBTREE, "(sAMAccountName=%(user)s)"
    )

    # Make selected group a superuser in Weblate
    AUTH_LDAP_USER_FLAGS_BY_GROUP = {
        # is_superuser means user has all permissions
        "is_superuser": "CN=weblate_AdminUsers,OU=Groups,DC=example,DC=com",
    }

    # Map groups from AD to Weblate
    AUTH_LDAP_GROUP_SEARCH = LDAPSearch(
        "OU=Groups,DC=example,DC=com", ldap.SCOPE_SUBTREE, "(objectClass=group)"
    )
    AUTH_LDAP_GROUP_TYPE = NestedActiveDirectoryGroupType()
    AUTH_LDAP_FIND_GROUP_PERMS = True

    # Optionally enable group mirroring from LDAP to Weblate
    # AUTH_LDAP_MIRROR_GROUPS = True

.. seealso::

    :doc:`ldap:index`, :doc:`ldap:authentication`


.. _cas-auth:


CAS authentication
------------------

CAS authentication can be achieved using a package such as `django-cas-ng`.

Step one is disclosing the e-mail field of the user via CAS. This has to be
configured on the CAS server itself, and requires you run at least CAS v2 since
CAS v1 doesn't support attributes at all.

Step two is updating Weblate to use your CAS server and attributes.

To install `django-cas-ng`:

.. code-block:: sh

    pip install django-cas-ng

Once you have the package installed you can hook it up to the Django
authentication system by modifying the :file:`settings.py` file:

.. code-block:: python

    # Add CAS backed, keep the Django one if you want to be able to sign in
    # even without LDAP for the admin account
    AUTHENTICATION_BACKENDS = (
        "django_cas_ng.backends.CASBackend",
        "weblate.accounts.auth.WeblateUserBackend",
    )

    # CAS server address
    CAS_SERVER_URL = "https://cas.example.net/cas/"

    # Add django_cas_ng somewhere in the list of INSTALLED_APPS
    INSTALLED_APPS = (..., "django_cas_ng")

Finally, a signal can be used to map the e-mail field to the user object. For
this to work you have to import the signal from the `django-cas-ng` package and
connect your code with this signal. Doing this in settings file can
cause problems, therefore it's suggested to put it:

- In your app config's :py:meth:`django:django.apps.AppConfig.ready` method
- In the project's :file:`urls.py` file (when no models exist)

.. code-block:: python

    from django_cas_ng.signals import cas_user_authenticated
    from django.dispatch import receiver


    @receiver(cas_user_authenticated)
    def update_user_email_address(sender, user=None, attributes=None, **kwargs):
        # If your CAS server does not always include the email attribute
        # you can wrap the next two lines of code in a try/catch block.
        user.email = attributes["email"]
        user.save()

.. seealso::

    `Django CAS NG <https://github.com/django-cas-ng/django-cas-ng>`_

Configuring third party Django authentication
---------------------------------------------

Generally any Django authentication plugin should work with Weblate. Just
follow the instructions for the plugin, just remember to keep the Weblate user backend
installed.

.. seealso::

    :ref:`ldap-auth`,
    :ref:`cas-auth`

Typically the installation will consist of adding an authentication backend to
:setting:`django:AUTHENTICATION_BACKENDS` and installing an authentication app (if
there is any) into :setting:`django:INSTALLED_APPS`:

.. code-block:: python

    AUTHENTICATION_BACKENDS = (
        # Add authentication backend here
        "weblate.accounts.auth.WeblateUserBackend",
    )

    INSTALLED_APPS += (
        # Install authentication app here
    )
