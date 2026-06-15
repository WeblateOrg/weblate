Vulnerability and incident handling
===================================

.. _security:

Product vulnerability reports
-----------------------------

.. seealso::

   Please read :ref:`ai-issues` in case you have used AI to discover a security issue in Weblate.

Weblate’s development team is strongly committed to responsible reporting and
disclosure of security-related issues. We have adopted and follow policies that
are geared toward delivering timely security updates to Weblate.

Product vulnerability reports cover security issues in Weblate source code,
release artifacts, and documented Weblate security properties. They do not
replace operational incident response for a particular deployment.

Most normal bugs in Weblate are reported to our public `GitHub issues tracker
<https://github.com/WeblateOrg/weblate/issues>`_, but due to the sensitive
nature of security issues, we ask them not to be publicly reported in this
fashion.

Instead, if you believe you’ve found something in Weblate that has security
implications, please submit a description of the issue to security@weblate.org,
`GitHub <https://github.com/WeblateOrg/weblate/security/advisories/new>`_,
or using `HackerOne <https://hackerone.com/weblate>`_.

Self-hosted operators should use this process when they believe an incident in
their own deployment is caused by a Weblate product vulnerability. Local
containment, recovery, customer notification, provider escalation, and other
deployment-specific incident response remain the operator's responsibility.

A member of the security team will respond to you within 48 hours, and
depending on what action is taken, you may get more follow-up emails.

.. note::

   **Sending encrypted reports**

   If you want to send an encrypted email (*optional*), please use the public
   key for security@weblate.org with ID ``8EA7 6E43 0976 3323 C2E3 D5A0 C472 9F23 8A80 EA93``.

   This public key is available on the most commonly used key servers, using
   WKD or `directly from weblate.org
   <https://weblate.org/.well-known/openpgpkey/hu/t5s8ztdbon8yzntexy6oz5y48etqsnbb?l=security>`_.

.. hint::

    Weblate depends on third-party components for many things. In case
    you find a vulnerability affecting one of those components in general,
    please report it directly to the respective project.

    Some of these are:

    * :doc:`Django <django:internals/security>`
    * `Django REST framework <https://www.django-rest-framework.org/#security>`_
    * `Python Social Auth <https://github.com/python-social-auth>`_

.. seealso::

   * :doc:`/contributing/issues`

Weblate-operated service incidents
----------------------------------

Operational incidents affecting Hosted Weblate, Dedicated Weblate, or other
deployments operated by Weblate s.r.o. are handled using
:doc:`/security/incident-response-plan`.

When such an incident also involves a Weblate product vulnerability, the
vulnerability report and public advisory follow the product vulnerability
reporting process and :ref:`vulnerability-disclosure-policy` on this page.

Self-hosted deployment incidents
--------------------------------

Operators of self-hosted Weblate deployments are responsible for their local
incident response process, including containment, recovery, notification, and
provider-specific escalation. The Weblate-operated
:doc:`/security/incident-response-plan` can be used as a reference, but it is
not a maintained incident response plan for third-party deployments.

If a self-hosted incident appears to be caused by a Weblate product
vulnerability, report it using the product vulnerability reporting process
above.

.. _vulnerability-disclosure-policy:

Vulnerability disclosure policy
-------------------------------

For Weblate product vulnerabilities, within 30 days following a release
containing a vulnerability fix, a security advisory is published at
https://github.com/WeblateOrg/weblate/security/advisories. The advisory is
available immediately with a release when possible.

Any actively exploited Weblate vulnerability, or any severe incident affecting
Weblate-operated services, is notified to CSIRT within 24 hours, general info
is provided to CSIRT within 72 hours, and a full report is provided within 14
days.

All users of Hosted or Dedicated Weblate impacted by a severe incident
or an actively exploited vulnerability are notified within 7 days.
