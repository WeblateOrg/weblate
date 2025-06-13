Disaster recovery plan
======================

Scope and objectives
--------------------

This plan addresses recovery from catastrophic events impacting Weblate service availability, data integrity, or operational continuity.

.. note::

    The plan is specifically designed for deployments of Weblate by Weblate s.r.o., but it can be applied to other deployments similarly.

Definitions
-----------

- **Disaster:** Any unplanned event causing complete or significant loss of service, data, or system functionality. Examples include hardware failure, data corruption, infrastructure outage, or malicious attack.
- **Recovery Point Objective (RPO):** Maximum acceptable data loss interval: **24 hours**.
- **Recovery Time Objective (RTO):** Maximum acceptable time to restore full service: **8 hours**.

Critical components
-------------------

- **Application Layer:** Weblate Python/Django application, background workers (Celery), and scheduled tasks.
- **Data Layer:** PostgreSQL database, translation repositories (Git), and logs.
- **Infrastructure:** Web server (NGINX/Apache), reverse proxy, storage volumes, SSL/TLS configuration, and optional SIEM logging system.

Backup policy
-------------

:ref:`automated-backup` process guarantees that all essential components
(database, data, and configuration) are backed up daily. The backups are stored
in two geographically different locations. The backup retention policy ensures
that recent backups are available daily and keeps six months of backups.

Recovery Procedures
----------------------

.. _drp-host:

Failure scenario: full host/system loss
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

1. Provision new host.
2. Bootstrap Weblate using provisioning software.
3. Restore Weblate backup following :ref:`restore-borg`.
4. Restart Weblate container.
5. Verify functionality and perform consistency checks.

Failure scenario: database corruption or data volume loss
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

1. Stop Weblate to prevent further write operations.
2. Restore Weblate backup following :ref:`restore-borg`.
3. Restart services and verify translation and user data consistency.

Failure scenario: malicious tampering or ransomware
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

1. Isolate affected host from the network.
2. Identify last known-good backup (pre-infection).
3. Follow steps from :ref:`drp-host` to deploy the system on a new host.

Validation and testing
----------------------

- **Backup Verification:** Monthly restore test of Weblate backups.
- **Disaster Recovery Drill:** Conduct at least annually, involving full restoration to a staging environment.
- **Automated Integrity Checks:** BorgBackup ensures integrity of backup archives.

Post-recovery steps
-------------------

- Confirm all services are operational and accessible.
- Notify users and stakeholders of the recovery status.
- Document timeline, root cause, and lessons learned.
- Apply updates or infrastructure changes to prevent recurrence.
- Follow :ref:`vulnerability-disclosure-policy` in case vulnerability was involved.
