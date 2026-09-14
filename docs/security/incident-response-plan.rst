Incident response plan for Weblate
==================================

Scope and objectives
--------------------

This IRP covers incidents impacting the confidentiality, integrity, or
availability of Weblate-operated deployments.

.. note::

    This plan is specifically designed for deployments operated by Weblate
    s.r.o. Other deployments need to adapt provider-specific and organizational
    steps to their own environment.

Handling an incident
--------------------

One team member handles the incident and names an available teammate as a
backup. They coordinate investigation, containment, recovery, reporting, and
user communication, asking other teammates or outside specialists for help
when needed. The backup takes over when the handler is unavailable.

Use :doc:`incident-reporting` for reporting decisions, deadlines, and a private
incident note. No separate management approval is needed to begin responding.

Communication logistics
-----------------------

- **Internal Communication:**
    - Primary channel is **Signal** for human-to-human coordination.
    - Technical alerts remain outside of Signal to avoid noise.
- **External Communication:**
    - **E-mail** is used to reach customers.
    - Customer contact lists are maintained in several locations to ensure access during service outages.
- **Public Disclosure:**
    - If an incident includes a Weblate product vulnerability, follow the
      product vulnerability reporting process and
      :ref:`vulnerability-disclosure-policy` in :doc:`/security/issues`.

Incident categories and severity
--------------------------------

Incident activation
^^^^^^^^^^^^^^^^^^^

- Declare an incident when an event is confirmed or strongly suspected to
  affect the confidentiality, integrity, or availability of the service beyond
  routine operational noise.
- Whoever identifies the incident alerts teammates through Signal. An
  available teammate takes responsibility, records the initial severity, and
  names a backup.
- Reclassify the incident if the scope or impact changes during investigation.

Incident categories
^^^^^^^^^^^^^^^^^^^

- Category 1 – Unauthorized Access
- Category 2 – Data Integrity Violation
- Category 3 – Service Outage or Degradation
- Category 4 – Misconfiguration or Deployment Error

Severity levels and SLAs
^^^^^^^^^^^^^^^^^^^^^^^^

These are operational response targets, not a statement of continuous
staffing. Assess product-security reporting separately using
:doc:`incident-reporting`; these targets do not extend reporting deadlines.

+----------+------------------------------------------------------+---------------------+-----------------------+
| Severity | Definition                                           | Target Acknowledge  | Target Initial Action |
+==========+======================================================+=====================+=======================+
| Critical | Total outage; Admin compromise; Active data breach;  | < 30 Minutes        | < 4 Hours             |
|          | requires immediate containment.                      |                     |                       |
+----------+------------------------------------------------------+---------------------+-----------------------+
| High     | Core feature failure; PII leak of single user.       | < 2 Hours           | 12 Hours              |
+----------+------------------------------------------------------+---------------------+-----------------------+
| Medium   | Performance degradation; Minor security issue.       | 1 Business Day      | 3 Business Days       |
+----------+------------------------------------------------------+---------------------+-----------------------+
| Low      | UI bugs; Staging issues; Non-security errors.        | Best Effort         | Best Effort           |
+----------+------------------------------------------------------+---------------------+-----------------------+

Incident response lifecycle
---------------------------

Preparation
^^^^^^^^^^^

- Ensure regular daily backups of the PostgreSQL database and the data directory using Weblate's built-in backup with rotation, see :ref:`backup`.
- Ensure Weblate uses a properly configured reverse proxy (e.g., NGINX) with HTTPS (TLS 1.2+).
- Enable 2FA for all admin-level accounts.
- Keep the Weblate instance and its dependencies (Python, Django, Celery, database, etc.) up to date.
- Integrate with SIEM systems using the GELF protocol for audit and application log forwarding.
- Complete the preparation checklist in :doc:`incident-reporting` and keep
  private contact and access details current.

Identification
^^^^^^^^^^^^^^

- Monitor system and application logs (``journalctl``, reverse proxy logs, Weblate application and audit logs).
- Analyze login events, webhook executions, and push/pull failures.
- Configure alerting (via Prometheus, Zabbix, or SIEM) for multiple login failures, unexpected restarts, or irregular VCS actions.
- Record awareness times and assess authority and user notifications using
  :doc:`incident-reporting`, without waiting for a complete investigation.
- Assess whether a security incident caused accidental or unlawful
  destruction, loss, or alteration of personal data, or unauthorized disclosure
  or access, and follow :ref:`incident-gdpr-notification`. This includes
  availability or integrity breaches without disclosure, such as accidental
  deletion or ransomware destruction. Seek privacy advice where needed while
  continuing investigation and reporting preparation.

.. _incident-gdpr-notification:

Personal-data breach notifications
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The incident handler determines whether Weblate acts as controller or processor
for the affected processing and records the assessment in the private incident
note. Under `GDPR Article 33
<https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng#art_33>`_:

* As controller, notify the competent supervisory authority without undue
  delay and, where feasible, within 72 hours of becoming aware of the
  personal-data breach, unless the breach is unlikely to result in a risk to
  individuals' rights and freedoms. Record the reason for a decision not to
  notify.
* If notification takes longer than 72 hours, include the reasons for the
  delay. Where information cannot be supplied together, provide it in stages
  without undue further delay.
* As processor, notify the controller without undue delay after becoming
  aware of a personal-data breach; do not wait for the controller's 72-hour
  deadline.

The controller's supervisory-authority notification must include the following
information under Article 33(3):

* The nature of the breach, including, where possible, the categories and
  approximate numbers of affected individuals and personal-data records.
* The name and contact details of the person who can provide further
  information, such as the incident handler or a data protection officer if
  one is appointed.
* The likely consequences of the breach.
* Measures taken or proposed to address the breach, including measures to
  reduce its adverse effects where appropriate.

Identify information that is not yet available and provide it in follow-up
notifications without undue further delay. Do not wait for exact counts
before notifying the authority.

As controller, separately assess communication to affected individuals under
`GDPR Article 34 <https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng#art_34>`_.
If the breach is likely to create a high risk to their rights and freedoms,
inform them without undue delay unless an Article 34(3) exception applies.
This applies even without active exploitation or a severe product-security
incident. Notification to the supervisory authority does not replace this
communication.

Explain the breach in clear language, giving a contact for further information,
likely consequences, measures taken or proposed, and actions individuals can
take. Record the assessment and any exception relied on: effective protection
of the affected data, such as encryption making it unreadable to unauthorized
people, or subsequent measures ensuring the high risk is no longer likely.
If individual communication would involve disproportionate effort, use public
communication or a similar measure that informs individuals equally
effectively. See the `EDPB data-breach guidance
<https://www.edpb.europa.eu/system/files/2023-04/edpb_guidelines_202209_personal_data_breach_notification_v2.0_en.pdf>`_.

Record breach-awareness timestamps, recipients, and deadlines separately from
CRA reporting. A CRA submission does not replace a GDPR notification, and the
two reporting clocks may start at different times.

Containment
^^^^^^^^^^^

- Maintain the private incident note from :doc:`incident-reporting`, including
  timeline updates, reporting deadlines, and submission receipts.
- Coordinate human response in **Signal** and keep technical alerting in the
  existing monitoring systems.
- For Category 1 or 2 incidents, create a manual **Hetzner Cloud Snapshot**
  before taking disruptive action when it is safe to do so.

  - Name format: ``IRP-[CaseID]-[YYYYMMDD]-Evidence``.
  - These are separate from standard rotating backups and must be preserved
    for analysis.

- Isolate the affected host or service as needed (for example by firewall rules
  or service isolation).
- Disable external integrations (Git/webhooks) if they are part of the attack
  vector.
- Suspend affected user accounts immediately.
- Revoke or rotate affected administrative, API, VCS, and webhook credentials
  as applicable.
- Preserve relevant evidence, including system logs, reverse proxy logs,
  Weblate application and audit logs, affected configuration state, and the
  list of impacted credentials or integrations.

Eradication
^^^^^^^^^^^

- Remove any unauthorized code or data.
- Patch known vulnerabilities by upgrading Weblate or server components.
- Validate binary and repository integrity using SHA-256 checksums or Git logs.

Recovery
^^^^^^^^

- Restore affected services or data from the latest known-good Weblate backups.
- Reintroduce services in a phased approach.
- Confirm the root cause has been removed or a compensating control is in
  place before restoring normal traffic.
- Rotate affected credentials and verify integrity of the restored system,
  repositories, and configuration.
- The handler records the decision to return to normal operations, checking
  recovery with the backup or another teammate where practical.
- Monitor logs and system behavior continuously for at least 72 hours post-recovery.

Post-incident review
^^^^^^^^^^^^^^^^^^^^

- **Timeline:** Hold a short team review within **5 business days** of incident closure.
- Compile a full incident timeline and actions taken.
- Perform Root Cause Analysis (RCA) and document it within **10 business days**.
- Update security policies and IRP documentation based on findings.
- Review the effectiveness of detection and containment mechanisms.
- Verify whether escalation, alerting, and external communication followed
  :doc:`/security/issues` as expected.
- Check for outstanding reports, promised updates, and delayed disclosures
  before closing the incident note.
