Privacy regulations compliance
++++++++++++++++++++++++++++++

.. tip::

   Weblate enables organizations to operate within privacy frameworks such as
   GDPR, DPDPA, PIPL, and others by offering strict data minimization, full
   data ownership, and fine-grained access control. All hosting and compliance
   responsibilities remain fully within the deploying organization’s control.

This document outlines how Weblate supports compliance with:

- EU General Data Protection Regulation (GDPR)
- California Consumer Privacy Act (CCPA)
- Brazilian Lei Geral de Proteção de Dados (LGPD)
- Swiss Federal Act on Data Protection (nFADP)
- Canadian Personal Information Protection and Electronic Documents Act (PIPEDA)
- Indian Digital Personal Data Protection Act (DPDPA)
- China’s Personal Information Protection Law (PIPL)

Privacy principles
==================

Data minimization
-----------------

Weblate collects only data strictly necessary for the operation of the platform. By default, the following personal data may be processed:

- Username or real name (user-supplied)
- Email address (required for notifications and access control)
- Optional profile metadata (avatar, bio)

No telemetry, analytics, or third-party tracking is embedded by default.

User consent and transparency
-----------------------------

- Weblate interfaces allow full transparency into collected personal data.
- Administrators may provide custom privacy policy and consent requests at user registration.
- Data collection occurs only as a result of direct user interaction or administrator-defined configuration.

Data access and portability
---------------------------

- Users may export their personal data and translation contributions using the user interface or API.
- Administrators can support data portability upon user request, fulfilling legal obligations for access.

Right to erasure and correction
-------------------------------

- Weblate allows full deletion of user accounts via the user and admin interface.
- Deleted users are removed or anonymized across the system.
- Users may update or correct personal information directly via the profile interface.

Data retention and deletion
---------------------------

- No automatic data persistence beyond system necessity.
- Logs and backups are locally controlled; deletion policies are operator-configurable.
- No third-party data sharing unless explicitly configured by administrators.

Security and confidentiality
----------------------------

- Encrypted TLS is required for all user interactions (HTTPS).
- Failed logins, permission changes, and other security events are logged.
- Optional SIEM integration (via GELF) enables compliance with audit requirements.
- Role-based access controls enforce data access separation.

International transfers
-----------------------

- Weblate itself performs no automatic data transfers.
- All hosting and data residency is controlled by the system operator.
- Organizations may host Weblate within specific jurisdictions (e.g., EU, India, China) to ensure compliance with data localization laws.

Regulatory mapping
==================

+-----------------------------+------------------------------------------------------------+
| Framework                   | Weblate support                                            |
+=============================+============================================================+
| GDPR (EU)                   | Minimization, consent, erasure, auditability, locality     |
+-----------------------------+------------------------------------------------------------+
| CCPA (California)           | Access, deletion, no sale, user control                    |
+-----------------------------+------------------------------------------------------------+
| LGPD (Brazil)               | Legal basis, access, correction, deletion                  |
+-----------------------------+------------------------------------------------------------+
| nFADP (Switzerland)         | Purpose limitation, consent, transparency                  |
+-----------------------------+------------------------------------------------------------+
| PIPEDA (Canada)             | Consent, access, individual rights                         |
+-----------------------------+------------------------------------------------------------+
| DPDPA (India)               | Lawful processing, consent, notice, user rights            |
+-----------------------------+------------------------------------------------------------+
| PIPL (China)                | Purpose limitation, data minimization, locality            |
+-----------------------------+------------------------------------------------------------+

Recommendations for compliance
==============================

- **Consent capture:** Provide a notice and/or explicit consent checkbox during registration, via :ref:`legal`.
- **Policy display:** Link to privacy and retention policies directly in Weblate’s user interface, either via :ref:`legal` or :setting:`PRIVACY_URL`.
- **Audit integration:** Use the built-in audit log and GELF forwarding to meet logging mandates.
- **Data subject requests:** Define a manual or automated procedure to fulfill access/erasure requests.
- **Locality:** Ensure infrastructure is physically located within the target jurisdiction as required.
