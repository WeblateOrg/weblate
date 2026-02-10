Incident response plan for Weblate
==================================

Scope and objectives
--------------------

This IRP covers incidents impacting the confidentiality, integrity, or availability of a Weblate deployment.

.. note::

    The plan is specifically designed for deployments of Weblate by Weblate s.r.o., but it can be applied to other deployments similarly.

Roles and responsibilities
--------------------------

- **Incident Response Lead (IRL):** Coordinates all phases of the response process.
- **System Administrator:** Executes containment and recovery measures.
- **Security Officer:** Evaluates security impact and regulatory consequences.
- **Data Protection Officer (DPO):** Evaluates if personal data (PII) was compromised and manages mandatory GDPR notifications.
- **Communications Lead:** Manages notifications to internal stakeholders and external parties if required.

Communication logistics
-----------------------

- **Internal Communication:**
    - Primary channel is **Signal** for human-to-human coordination.
    - Technical alerts remain outside of Signal to avoid noise.
- **External Communication:**
    - **E-mail** is used to reach customers.
    - Customer contact lists are maintained in several locations to ensure access during service outages.
- **Public Disclosure:**
    - If a security vulnerability is discovered, follow :doc:`/security/issues`.

Incident categories and severity
--------------------------------

Incident categories
^^^^^^^^^^^^^^^^^^^

- Category 1 – Unauthorized Access
- Category 2 – Data Integrity Violation
- Category 3 – Service Outage or Degradation
- Category 4 – Misconfiguration or Deployment Error

Severity levels and SLAs
^^^^^^^^^^^^^^^^^^^^^^^^

+----------+------------------------------------------------------+---------------------+-----------------------+
| Severity | Definition                                           | Target Acknowledge  | Target Initial Action |
+==========+======================================================+=====================+=======================+
| Critical | Total outage; Admin compromise; Active data breach.  | < 30 Minutes        | 4 Hours               |
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

Identification
^^^^^^^^^^^^^^

- Monitor system and application logs (``journalctl``, reverse proxy logs, Weblate application and audit logs).
- Analyze login events, webhook executions, and push/pull failures.
- Configure alerting (via Prometheus, Zabbix, or SIEM) for multiple login failures, unexpected restarts, or irregular VCS actions.

Containment
^^^^^^^^^^^

- **Forensic Preservation:** For Category 1 or 2 incidents, create a manual **Hetzner Cloud Snapshot** before taking disruptive action.
    - Name format: ``IRP-[CaseID]-[YYYYMMDD]-Evidence``.
    - These are separate from standard rotating backups and must be preserved for analysis.
- Temporarily restrict access (e.g., via firewall rules or service isolation).
- Disable external integrations (Git/webhooks) if they are part of the attack vector.
- Suspend affected user accounts immediately.

Eradication
^^^^^^^^^^^

- Remove any unauthorized code or data.
- Patch known vulnerabilities by upgrading Weblate or server components.
- Validate binary and repository integrity using SHA-256 checksums or Git logs.

Recovery
^^^^^^^^

- Restore affected services or data from the latest known-good Weblate backups.
- **PII Assessment:** DPO determines if the breach requires a 72-hour GDPR notification.
- Reintroduce services in a phased approach.
- Monitor logs and system behavior continuously for at least 72 hours post-recovery.

Post-incident review
^^^^^^^^^^^^^^^^^^^^

- **Timeline:** Hold a review meeting within **5 business days** of incident closure.
- Compile a full incident timeline and actions taken.
- Perform Root Cause Analysis (RCA) and document it within **10 business days**.
- Update security policies and IRP documentation based on findings.
- Review the effectiveness of detection and containment mechanisms.
