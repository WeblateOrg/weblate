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

Reports concerning the separately distributed Weblate Client (``wlc``) are
evaluated against the `wlc threat model
<https://github.com/WeblateOrg/wlc/blob/main/THREAT_MODEL.md>`_, which documents
its intended trust boundaries, supported security properties, and explicit
non-goals.

Report low and medium severity security issues in our public `GitHub issues
tracker <https://github.com/WeblateOrg/weblate/issues>`_. These reports are
discussed and fixed publicly through the normal development process.

Report high and critical severity vulnerabilities privately to
security@weblate.org, through
`GitHub <https://github.com/WeblateOrg/weblate/security/advisories/new>`_,
or using `HackerOne <https://hackerone.com/weblate>`_. Do not open public
issues for these vulnerabilities. Please describe the issue, affected
versions, and steps to reproduce it, if known.

If you are unsure of the severity, you may start through a private channel.
If the security team assesses a privately reported issue as low or medium
severity, we will ask you to continue in a public GitHub issue. Redirecting a
report does not itself confirm that the issue is a vulnerability.

Public discussion allows the community to help review and fix low and medium
severity issues. Private coordination focuses on vulnerabilities with serious
impact, reducing the risk to users while a fix is prepared. This approach is
similar to the `curl vulnerability disclosure policy
<https://curl.se/dev/vuln-disclosure.html>`_.

Self-hosted operators should use this process when they believe an incident in
their own deployment is caused by a Weblate product vulnerability. Local
containment, recovery, customer notification, provider escalation, and other
deployment-specific incident response remain the operator's responsibility.

A member of the security team will respond to private reports within 48 hours,
and depending on what action is taken, you may get more follow-up emails.
Suspected active exploitation and severe security incidents receive immediate
internal attention under :doc:`incident-reporting`. Acknowledging a report or
completing an investigation does not postpone reporting deadlines.

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
    If it also affects a shipped Weblate artifact or a Weblate deployment,
    report that impact to Weblate using the severity-based process above.

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
vulnerability report and any public advisory follow the severity-based product
vulnerability reporting process and :ref:`vulnerability-disclosure-policy` on
this page.

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

Weblate publishes security advisories only for high and critical severity
vulnerabilities. These vulnerabilities are handled privately until coordinated
disclosure, with an advisory published alongside a release containing the fix
at https://github.com/WeblateOrg/weblate/security/advisories.
Advisories identify affected versions, impact, severity, and steps users can
take to remediate the vulnerability.

Weblate does not publish security advisories for low or medium severity issues.
Their fixes follow the normal public development process and are documented in
the release notes.

Technical details may be delayed when publishing them would create greater
security risks than benefits while users apply the fix. The incident handler
records the reason and a review date in the private incident note. This does
not delay authority reports or protective advice users need.

.. _incident-authority-reporting:

Authority reporting
-------------------

Weblate adopts the following reporting timelines as a voluntary policy
baseline for actively exploited Weblate product vulnerabilities and severe
product-security incidents. This includes affected shipped dependencies and
incidents learned about through self-hosted deployments. Severe security
incidents affecting Weblate-operated services also follow this baseline.

.. list-table::
   :header-rows: 1

   * - Report
     - Deadline
   * - Early warning
     - Without undue delay, within 24 hours of awareness.
   * - Main notification
     - Without undue delay, within 72 hours of awareness.
   * - Final report for an actively exploited vulnerability
     - Within 14 days after a corrective or mitigating measure becomes
       available.
   * - Final report for a severe incident
     - Within one calendar month after the main incident notification.

Hours include weekends and holidays. Acknowledgment, incident declaration,
handover, or completion of an investigation does not restart these clocks.
When an event involves both active exploitation and a severe incident, track
both reporting obligations and final-report deadlines.

These timelines follow the `European Commission reporting guidance
<https://digital-strategy.ec.europa.eu/en/policies/cra-reporting>`_. The
incident handler records whether mandatory or voluntary reporting applies and
uses the corresponding route. For CRA reporting, the Single Reporting
Platform routes notifications to the coordinating CSIRT and ENISA. This policy
does not determine Weblate's regulatory role or claim compliance; see
:doc:`product-information`.

For classification, submission steps, and private incident records, see
:doc:`incident-reporting`.

User notifications
------------------

Weblate informs impacted users of active exploitation or severe security
incidents without undue delay, including available mitigations and corrective
actions. Where appropriate, warnings address all users. Known affected contacts,
including Hosted and Dedicated Weblate customers, receive e-mail notifications.
For high and critical severity vulnerabilities, public GitHub security
advisories provide warnings and updates for self-hosted users whose contact
details are not known. Low and medium severity issues are tracked in public
GitHub issues and release notes. The severity-based reporting and advisory
policy does not delay required authority reports or protective advice to users.

Initial warnings can provide protective advice before a fix or detailed
vulnerability disclosure is ready. Authority reporting, user warnings, and
publication of technical details proceed separately as needed.

Personal-data breaches also require a separate assessment of
:ref:`notifications to affected individuals <incident-gdpr-notification>`,
even when there is no active exploitation or severe product-security incident.
