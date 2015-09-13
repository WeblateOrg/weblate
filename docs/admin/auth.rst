Authentication
==============

User registration
-----------------

The default setup for Weblate is to use python-social-auth for handling new
users. This allows them to register using form on the website and after
confirming their email they can contribute or by using some third party service
to authenticate.

You can also completely disable new users registration using
:setting:`REGISTRATION_OPEN`.

Authentication backends
-----------------------

By default Weblate uses Django built-in authentication and includes various
social authentication options. Thanks to using Django authentication, you can
also import user database from other Django based projects (see
:ref:`pootle-migration`).

Django can be additionally configured to authenticate against other means as
well.

Social authentication
+++++++++++++++++++++

Thanks to `python-social-auth <http://psa.matiasaguirre.net/>`_, Weblate
support authentication using many third party services such as Facebook,
GitHub, Google or Bitbucket.

Please check their documentation for generic configuration instructions:

http://psa.matiasaguirre.net/docs/configuration/django.html

.. note::

    By default, Weblate relies on third-party authentication services to
    provide validated email address, in case some of services you want to use
    do not support this, please remove
    ``social.pipeline.social_auth.associate_by_email`` from
    ``SOCIAL_AUTH_PIPELINE`` settings.

Enabling individual backends is quite easy, it's just a matter of adding entry to
``AUTHENTICATION_BACKENDS`` setting and possibly adding keys needed for given
authentication. Please note that some backends do not provide user email by
default, you have to request it explicitly, otherwise Weblate will not be able
to properly credit users contributions.

OpenID authentication
~~~~~~~~~~~~~~~~~~~~~

For OpenID based services it's usually just a matter of enabling them. Following
section enables OpenID authentication for OpenSUSE, Fedora and Ubuntu:

.. code-block:: python

    # Authentication configuration
    AUTHENTICATION_BACKENDS = (
        'social.backends.email.EmailAuth',
        'social.backends.suse.OpenSUSEOpenId',
        'social.backends.ubuntu.UbuntuOpenId',
        'social.backends.fedora.FedoraOpenId',
        'weblate.accounts.auth.WeblateUserBackend',
    )

GitHub authentication
~~~~~~~~~~~~~~~~~~~~~

You need to register application on GitHub and then tell Weblate all the secrets:

.. code-block:: python

    # Authentication configuration
    AUTHENTICATION_BACKENDS = (
        'social.backends.github.GithubOAuth2',
        'social.backends.email.EmailAuth',
        'weblate.accounts.auth.WeblateUserBackend',
    )

    # Social auth backends setup
    SOCIAL_AUTH_GITHUB_KEY = 'GitHub Client ID'
    SOCIAL_AUTH_GITHUB_SECRET = 'GitHub Client Secret'
    SOCIAL_AUTH_GITHUB_SCOPE = ['user:email']

.. seealso:: http://psa.matiasaguirre.net/docs/backends/index.html

Google OAuth2
~~~~~~~~~~~~~

For using Google OAuth2, you need to register application on
<https://console.developers.google.com/> and enable Google+ API.

The redirect URL is ``https://WEBLATE SERVER/accounts/complete/google-oauth2/``

.. code-block:: python

    # Authentication configuration
    AUTHENTICATION_BACKENDS = (
        'social.backends.google.GoogleOAuth2',
        'social.backends.email.EmailAuth',
        'weblate.accounts.auth.WeblateUserBackend',
    )

    # Social auth backends setup
    SOCIAL_AUTH_GOOGLE_OAUTH2_KEY = 'Client ID'
    SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET = 'Client secret'

Facebook OAuth2
~~~~~~~~~~~~~~~

As usual with OAuth2 services, you need to register your application with
Facebook. Once this is done, you can configure Weblate to use it:

.. code-block:: python

    # Authentication configuration
    AUTHENTICATION_BACKENDS = (
        'social.backends.facebook.FacebookOAuth2',
        'social.backends.email.EmailAuth',
        'weblate.accounts.auth.WeblateUserBackend',
    )

    # Social auth backends setup
    SOCIAL_AUTH_FACEBOOK_KEY = 'key'
    SOCIAL_AUTH_FACEBOOK_SECRET = 'secret'
    SOCIAL_AUTH_FACEBOOK_SCOPE = ['email', 'public_profile']


LDAP authentication
+++++++++++++++++++

LDAP authentication can be best achieved using `django-auth-ldap` package. You
can install it by usual means:

.. code-block:: sh

    # Using PyPI
    pip install django-auth-ldap

    # Using apt-get
    apt-get install python-django-auth-ldap

Once you have the package installed, you can hook it to Django authentication:

.. code-block:: python

    # Add LDAP backed, keep Django one if you want to be able to login
    # even without LDAP for admin account
    AUTHENTICATION_BACKENDS = (
        'django_auth_ldap.backend.LDAPBackend',
        'weblate.accounts.auth.WeblateUserBackend',
    )

    # LDAP server address
    AUTH_LDAP_SERVER_URI = 'ldaps://ldap.example.net'

    # DN to use for authentication
    AUTH_LDAP_USER_DN_TEMPLATE = 'cn=%(user)s,o=Example'
    # Depending on your LDAP server, you might use different DN
    # like:
    # AUTH_LDAP_USER_DN_TEMPLATE = 'ou=users,dc=example,dc=com'

    # List of attributes to import from LDAP on login
    # Weblate stores full user name in the first_name attribute
    AUTH_LDAP_USER_ATTR_MAP = {
        'first_name': 'name',
        'email': 'mail',
    }

.. seealso:: http://pythonhosted.org/django-auth-ldap/
