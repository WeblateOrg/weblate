.. _report-issue:

Reporting issues in Weblate
===========================

Our `issue tracker <https://github.com/WeblateOrg/weblate/issues>`_ is hosted at GitHub:

Feel welcome to report any issues with, or suggest improvement of Weblate there.
If what you have found is a security issue in Weblate, please consult the "Security
issues" section below.

.. _security:

Security issues
---------------

In order to give the community time to respond and upgrade you are strongly urged to
report all security issues privately. HackerOne is used to handle
security issues, and can be reported directly at `HackerOne <https://hackerone.com/weblate>`_.

Alternatively, report to security@weblate.org, which ends up on
HackerOne as well.

If you don't want to use HackerOne, for whatever reason, you can send the report
by e-mail to michal@cihar.com. You can choose to encrypt it using this PGP key
`3CB 1DF1 EF12 CF2A C0EE  5A32 9C27 B313 42B7 511D`.

.. note::

    Weblate depends on third party components for many things.  In case
    you find a vulnerability affecting one of those components in general,
    please report it directly to the respective project.

    Some of these are:

    * :doc:`Django <django:internals/security>`
    * `Django REST framework <https://www.django-rest-framework.org/#security>`_
    * `Python Social Auth <https://github.com/python-social-auth>`_
