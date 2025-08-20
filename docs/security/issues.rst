Vulnerability and incident handling
===================================

.. _security:

Reporting security issues
-------------------------

.. seealso::

   Please read :ref:`ai-issues` in case you have used AI to discover a security issue in Weblate.

Weblate’s development team is strongly committed to responsible reporting and
disclosure of security-related issues. We have adopted and follow policies that
are geared toward delivering timely security updates to Weblate.

Most normal bugs in Weblate are reported to our public `GitHub issues tracker
<https://github.com/WeblateOrg/weblate/issues>`_, but due to the sensitive
nature of security issues, we ask them not to be publicly reported in this
fashion.

Instead, if you believe you’ve found something in Weblate that has security
implications, please submit a description of the issue to security@weblate.org,
`GitHub <https://github.com/WeblateOrg/weblate/security/advisories/new>`_,
or using `HackerOne <https://hackerone.com/weblate>`_.

A member of the security team will respond to you within 48 hours, and
depending on what action is taken, you may get more follow-up emails.

.. note::

   **Sending encrypted reports**

   If you want to send an encrypted email (*optional*), please use the public
   key for michal@weblate.org with ID ``3CB 1DF1 EF12 CF2A C0EE 5A32 9C27 B313
   42B7 511D``. This public key is available on the most commonly used key servers,
   and from `Keybase <https://keybase.io/nijel>`_.

.. hint::

    Weblate depends on third-party components for many things. In case
    you find a vulnerability affecting one of those components in general,
    please report it directly to the respective project.

    Some of these are:

    * :doc:`Django <django:internals/security>`
    * `Django REST framework <https://www.django-rest-framework.org/#security>`_
    * `Python Social Auth <https://github.com/python-social-auth>`_

.. _vulnerability-disclosure-policy:

Vulnerability disclosure policy
-------------------------------

Within 30 days following a release containing a vulnerability fix, a security
advisory is published at
https://github.com/WeblateOrg/weblate/security/advisories. The advisory is
available immediately with a release when possible.

Any actively exploited vulnerability or severe incidents are notified to CSIRT
within 24 hours, general info is provided to CSIRT within 72 hours, and a full
report is provided within 14 days.

All users of Hosted or Dedicated Weblate impacted by a severe incident
or an actively exploited vulnerability are notified within 7 days.
