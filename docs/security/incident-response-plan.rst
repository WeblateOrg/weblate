Incident response plan for Weblate
==================================

Scope and objectives
--------------------

- This IRP covers incidents impacting the confidentiality, integrity, or availability of a Weblate deployment.
- It applies to self-hosted Weblate instances, whether on-premise or in cloud infrastructure.

Roles and responsibilities
--------------------------

- **Incident Response Lead (IRL):** Coordinates all phases of the response process.
- **System Administrator:** Executes containment and recovery measures.
- **Security Officer:** Evaluates security impact and regulatory consequences.
- **Communications Lead:** Manages notifications to internal stakeholders and external parties if required.

Incident categories
-------------------

- Category 1 – Unauthorized Access
- Category 2 – Data Integrity Violation
- Category 3 – Service Outage or Degradation
- Category 4 – Misconfiguration or Deployment Error

Incident response lifecycle
---------------------------

Preparation
^^^^^^^^^^^

- Ensure regular daily backups of the PostgreSQL database and the data directory.
- Protect Weblate with reverse proxy (e.g., NGINX or Apache) and HTTPS (TLS 1.2+).
- Enable 2FA for admin-level accounts.
- Keep the Weblate instance and its dependencies (Python, Django, Celery, database, etc.) up to date.
- Integrate with SIEM systems using the GELF protocol for audit and application log forwarding.

Identification
^^^^^^^^^^^^^^

- Monitor system and application logs (``journalctl``, reverse proxy logs, Weblate application and audit logs).
- Analyze login events, webhook executions, and push/pull failures.
- Configure alerting (e.g., via Prometheus, Zabbix, or SIEM) for:
  - Multiple login failures
  - Unexpected service restarts or memory usage spikes
  - Irregular push/pull actions from version control systems

Containment
^^^^^^^^^^^

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

- Restore affected services or data from the latest known-good backups.
- Reintroduce services in a phased approach.
- Monitor logs and system behavior continuously for at least 72 hours post-recovery.

Post-incident review
^^^^^^^^^^^^^^^^^^^^

- Compile a full incident timeline and actions taken.
- Perform Root Cause Analysis (RCA).
- Update security policies and IRP documentation.
- Review the effectiveness of detection and containment mechanisms.
