Password security
=================

How Weblate stores passwords
----------------------------

Weblate uses a Django implementation to store hashed passwords; see :ref:`django:auth_password_storage`.

The recommended Weblate configuration uses Argon2 with time_cost = 2, memory_cost = 102400, and parallelism = 8.

.. hint::

   The password hashing can be customized using :setting:`django:PASSWORD_HASHERS`.

Password validation
-------------------

When a user is configuring a password, it is validated to reduce the risk of using weak passwords.

The recommended Weblate configuration verifies:

* The password has to be at least 10 characters long, and at most 72 characters long.
* Password similar to username and other attributes is rejected.
* A common or overly simple password is rejected.
* Any password user used recently is rejected.
* Password strength is optionally checked using the zxcvbn algorithm.

.. hint::

   The password validation can be customized using :setting:`django:AUTH_PASSWORD_VALIDATORS`.

Social or third-party authentication
------------------------------------

Weblate does not store any passwords or enforce any password policy when social
or third-party authentication is configured. The passwords are, in such a case,
fully managed externally.

.. seealso::

   :doc:`/admin/auth`
