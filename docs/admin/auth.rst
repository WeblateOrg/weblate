Authentication
==============

User registration
-----------------

The default setup for Weblate is to use python-social-auth for handling new
users. This allows them to register using a form on the website and after
confirming their email they can contribute or authenticate by using some
third party service.

You can also completely disable new users registration using
:setting:`REGISTRATION_OPEN`.

.. _rate-limit:

Rate limiting
-------------

.. versionadded:: 2.14

The password based authentication is subject to rate limiting. At most
:setting:`AUTH_MAX_ATTEMPTS` attempts are allowed within
:setting:`AUTH_CHECK_WINDOW` seconds. The user is then blocked
for :setting:`AUTH_LOCKOUT_TIME`.

If there are more than :setting:`AUTH_LOCK_ATTEMPTS` failed authentication
attempts on one account, this account password authentication is disabled and
it's not possible to login until user asks for password reset.

.. _rate-ip:

IP address for rate limiting
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The rate limiting is based on client IP address. This is obtained from HTTP
headers and you will have to change configuration in the event Weblate is running
behind reverse proxy to work it properly.

.. seealso::

    :setting:`IP_BEHIND_REVERSE_PROXY`,
    :setting:`IP_PROXY_HEADER`,
    :setting:`IP_PROXY_OFFSET`

Authentication backends
-----------------------

By default Weblate uses the Django built-in authentication and includes various
social authentication options. Thanks to using Django authentication, you can
also import user database from other Django based projects (see
:ref:`pootle-migration`).

Django can be additionally configured to authenticate against other means as
well.

Social authentication
---------------------

Thanks to `python-social-auth <https://python-social-auth.readthedocs.io/>`_, Weblate
support authentication using many third party services such as Facebook,
GitHub, Google or Bitbucket.

Please check their documentation for generic configuration instructions
in :doc:`psa:configuration/django`.

.. note::

    By default, Weblate relies on third-party authentication services to
    provide a validated email address, in case some of the services you want to use
    do not support this, please enforce email validation on Weblate side
    by configuring FORCE_EMAIL_VALIDATION for them. For example:

    .. code-block:: python

        SOCIAL_AUTH_OPENSUSE_FORCE_EMAIL_VALIDATION = True

    .. seealso:: :doc:`psa:pipeline`

Enabling individual backends is quite easy, it's just a matter of adding an entry to
the ``AUTHENTICATION_BACKENDS`` setting and possibly adding keys needed for given
authentication. Please note that some backends do not provide user email by
default, you have to request it explicitly, otherwise Weblate will not be able
to properly credit users contributions.

OpenID authentication
~~~~~~~~~~~~~~~~~~~~~

For OpenID based services it's usually just a matter of enabling them. The following
section enables OpenID authentication for OpenSUSE, Fedora and Ubuntu:

.. code-block:: python

    # Authentication configuration
    AUTHENTICATION_BACKENDS = (
        'social_core.backends.email.EmailAuth',
        'social_core.backends.suse.OpenSUSEOpenId',
        'social_core.backends.ubuntu.UbuntuOpenId',
        'social_core.backends.fedora.FedoraOpenId',
        'weblate.accounts.auth.WeblateUserBackend',
    )

.. _github_auth:

GitHub authentication
~~~~~~~~~~~~~~~~~~~~~

You need to register an application on GitHub and then tell Weblate all the secrets:

.. code-block:: python

    # Authentication configuration
    AUTHENTICATION_BACKENDS = (
        'social_core.backends.github.GithubOAuth2',
        'social_core.backends.email.EmailAuth',
        'weblate.accounts.auth.WeblateUserBackend',
    )

    # Social auth backends setup
    SOCIAL_AUTH_GITHUB_KEY = 'GitHub Client ID'
    SOCIAL_AUTH_GITHUB_SECRET = 'GitHub Client Secret'
    SOCIAL_AUTH_GITHUB_SCOPE = ['user:email']

.. seealso::

    :doc:`Python Social Auth backend <psa:backends/index>`

.. _bitbucket_auth:

Bitbucket authentication
~~~~~~~~~~~~~~~~~~~~~~~~

You need to register an application on Bitbucket and then tell Weblate all the secrets:

.. code-block:: python

    # Authentication configuration
    AUTHENTICATION_BACKENDS = (
        'social_core.backends.bitbucket.BitbucketOAuth',
        'social_core.backends.email.EmailAuth',
        'weblate.accounts.auth.WeblateUserBackend',
    )

    # Social auth backends setup
    SOCIAL_AUTH_BITBUCKET_KEY = 'Bitbucket Client ID'
    SOCIAL_AUTH_BITBUCKET_SECRET = 'Bitbucket Client Secret'
    SOCIAL_AUTH_BITBUCKET_VERIFIED_EMAILS_ONLY = True

.. seealso::

    :doc:`Python Social Auth backend <psa:backends/index>`

.. _google_auth:

Google OAuth2
~~~~~~~~~~~~~

For using Google OAuth2, you need to register an application on
<https://console.developers.google.com/> and enable Google+ API.

The redirect URL is ``https://WEBLATE SERVER/accounts/complete/google-oauth2/``

.. code-block:: python

    # Authentication configuration
    AUTHENTICATION_BACKENDS = (
        'social_core.backends.google.GoogleOAuth2',
        'social_core.backends.email.EmailAuth',
        'weblate.accounts.auth.WeblateUserBackend',
    )

    # Social auth backends setup
    SOCIAL_AUTH_GOOGLE_OAUTH2_KEY = 'Client ID'
    SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET = 'Client secret'

.. _facebook_auth:

Facebook OAuth2
~~~~~~~~~~~~~~~

As usual with OAuth2 services, you need to register your application with
Facebook. Once this is done, you can configure Weblate to use it:

.. code-block:: python

    # Authentication configuration
    AUTHENTICATION_BACKENDS = (
        'social_core.backends.facebook.FacebookOAuth2',
        'social_core.backends.email.EmailAuth',
        'weblate.accounts.auth.WeblateUserBackend',
    )

    # Social auth backends setup
    SOCIAL_AUTH_FACEBOOK_KEY = 'key'
    SOCIAL_AUTH_FACEBOOK_SECRET = 'secret'
    SOCIAL_AUTH_FACEBOOK_SCOPE = ['email', 'public_profile']


.. _gitlab_auth:

Gitlab OAuth2
~~~~~~~~~~~~~

For using Gitlab OAuth2, you need to register application on
<https://gitlab.com/profile/applications>.

The redirect URL is ``https://WEBLATE SERVER/accounts/complete/gitlab/`` and
ensure to mark the `read_user` scope.

.. code-block:: python

    # Authentication configuration
    AUTHENTICATION_BACKENDS = (
        'social_core.backends.gitlab.GitLabOAuth2',
        'social_core.backends.email.EmailAuth',
        'weblate.accounts.auth.WeblateUserBackend',
    )

    # Social auth backends setup
    SOCIAL_AUTH_GITLAB_KEY = 'Application ID'
    SOCIAL_AUTH_GITLAB_SECRET = 'Secret'
    SOCIAL_AUTH_GITLAB_SCOPE = ['api']

Password authentication
-----------------------

The default :file:`settings.py` comes with reasonable set of
:setting:`django:AUTH_PASSWORD_VALIDATORS`:

* Password can't be too similar to your other personal information.
* Password must contain at least 6 characters.
* Password can't be a commonly used password.
* Password can't be entirely numeric.
* Password can't consist of single character or whitespace only.
* Password can't match password you have used in the past.

You can customize this setting to match your password policy.

Additionally you can also install
`django-zxcvbn-password <https://pypi.python.org/pypi/django-zxcvbn-password/>`_
which gives quite realistic estimates of password difficulty and allows to reject
passwords below certain threshold.

.. _ldap-auth:

LDAP authentication
-------------------

LDAP authentication can be best achieved using `django-auth-ldap` package. You
can install it by usual means:

.. code-block:: sh

    # Using PyPI
    pip install django-auth-ldap>=1.3.0

    # Using apt-get
    apt-get install python-django-auth-ldap

.. warning::

    With django-auth-ldap older than 1.3.0 the :ref:`autogroup` will not work
    properly for newly created users.

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
        # Use following if your LDAP server does not have full name
        # Weblate will merge them later
        # 'first_name': 'givenName',
        # 'last_name': 'sn',
        'email': 'mail',
    }

.. note::

    You should remove ``'social_core.backends.email.EmailAuth'`` from the
    ``AUTHENTICATION_BACKENDS`` setting, otherwise users will be able to set
    their password in Weblate and authenticate using that. Keeping
    ``'weblate.accounts.auth.WeblateUserBackend'`` is still needed in order to
    make permissions and anonymous user work correctly. It will also allow you
    to login using local admin account if you have created it (eg. by using
    :djadmin:`createadmin`).

.. seealso::

    :doc:`ldap:index`


CAS authentication
------------------

CAS authentication can be achieved using a package such as `django-cas-ng`.

Step one is disclosing the email field of the user via CAS. This has to be
configured on the CAS server itself and requires you run at least CAS v2 since
CAS v1 doesn't support attributes at all.

Step two is updating Weblate to use your CAS server and attributes.

To install `django-cas-ng`:

.. code-block:: sh

    pip install django-cas-ng

Once you have the package installed you can hook it up to the Django
authentication system by modifying the :file:`settings.py` file:

.. code-block:: python

    # Add CAS backed, keep Django one if you want to be able to login
    # even without LDAP for admin account
    AUTHENTICATION_BACKENDS = (
        'django_cas_ng.backends.CASBackend',
        'weblate.accounts.auth.WeblateUserBackend',
    )

    # CAS server address
    CAS_SERVER_URL = 'https://cas.example.net/cas/'

    # Add django_cas_ng somewhere in the list of INSTALLED_APPS
    INSTALLED_APPS = (
        ...,
        'django_cas_ng'
    )

Finally, a signal can be used to map the email field to the user object. For
this to work you have to import the signal from the `django-cas-ng` package and
connect your code with this signal. Doing this inside your settings file can
cause problems, therefore it's suggested to put it:

- in your app config's :py:meth:`django:django.apps.AppConfig.ready` method (Django 1.7 and higher)
- at the end of your :file:`models.py` file (Django 1.6 and lower)
- in the project's :file:`urls.py` file (when no models exist)

.. code-block:: python

    from django_cas_ng.signals import cas_user_authenticated
    from django.dispatch import receiver
    @receiver(cas_user_authenticated)
    def update_user_email_address(sender, user=None, attributes=None, **kwargs):
        # If your CAS server does not always include the email attribute
        # you can wrap the next two lines of code in a try/catch block.
        user.email = attributes['email']
        user.save()

.. seealso::

    `Django CAS NG <https://github.com/mingchen/django-cas-ng>`_
