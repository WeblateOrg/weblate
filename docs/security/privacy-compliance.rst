Privacy regulations compliance
++++++++++++++++++++++++++++++

.. include:: /snippets/compliance-warning.rst

.. tip::

   Weblate provides features that help organizations operate within privacy
   frameworks such as GDPR, DPDPA, PIPL, and others. Hosting, legal basis,
   retention, notices, and compliance responsibilities remain under the
   deploying organization's control.

This document outlines Weblate features that can support compliance with:

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

Weblate processes account and activity data needed to provide translation
workflows, authentication, notifications, access control, and auditability.
Depending on enabled features, the following personal data can be stored or
processed:

- Account identifiers such as username, full name, primary e-mail address,
  verified e-mail addresses, and social-authentication associations.
- Optional profile fields such as public e-mail, website, profile links,
  location, company, language preferences, and dashboard preferences.
- Translation activity, suggestions, comments, watched projects,
  notification settings, and contribution statistics.
- Operational records such as audit-log entries, IP addresses, user agents,
  timestamps, and security-related events.

External analytics, crash reporting, remote logging, and avatar providers are
optional integrations controlled by the site operator.

User consent and transparency
-----------------------------

- Users can review and update their account and profile data in
  :ref:`user-profile`.
- Administrators can publish privacy policy, terms, cookie information, and
  subcontractor information using :ref:`legal`, or link externally using
  :setting:`LEGAL_URL` and :setting:`PRIVACY_URL`.
- Terms of service confirmation can be enforced using the legal app, and
  :setting:`LEGAL_TOS_DATE` can require users to accept updated terms.
- Data processing depends on user interaction and on integrations enabled by
  the site operator.

Data access and portability
---------------------------

- Users can download a JSON export of their user data from the
  :guilabel:`Account` tab in :ref:`user-profile`; the export format is
  documented in :ref:`schema-userdata`.
- Administrators can export active non-bot user data with
  :wladmin:`dumpuserdata`.
- Project translations and translation files can be exported separately using
  Weblate's project and file export features.

Right to erasure and correction
-------------------------------

- Users can correct account and profile information from the profile
  interface.
- Users can request account removal from the :guilabel:`Account` tab. The
  removal flow requires confirmation and then deactivates and anonymizes the
  account.
- Account removal clears private profile fields, API tokens, social-auth
  associations, group memberships, notification subscriptions, watched
  projects, and user translation memory.
- Historical project records can remain associated with an anonymized deleted
  account where needed to preserve translation history and auditability.

Data retention and deletion
---------------------------

- Audit-log retention is configured using :setting:`AUDITLOG_EXPIRY`.
- Backups, reverse-proxy logs, mail server logs, and database retention are
  controlled by the site operator.
- Third-party services receive data only when configured or used by the
  operator, for example external authentication providers, avatar providers,
  Matomo, Sentry, remote logging, machine translation services, or repository
  integrations.

Security and confidentiality
----------------------------

- Weblate supports HTTPS deployments and secure cookie settings; operators
  should configure TLS and trusted proxy headers correctly.
- Failed sign-ins, permission changes, two-factor changes, account removal
  requests, and other security events are recorded in the audit log.
- Optional GELF logging can forward logs to systems such as Graylog.
- Access control is enforced through users, teams, roles, project access
  settings, and component permissions.
- Commit identity privacy can be improved with
  :setting:`PRIVATE_COMMIT_EMAIL_OPT_IN`,
  :setting:`PRIVATE_COMMIT_EMAIL_TEMPLATE`,
  :setting:`PRIVATE_COMMIT_NAME_OPT_IN`, and
  :setting:`PRIVATE_COMMIT_NAME_TEMPLATE`.
- Avatar fetching can be disabled with :setting:`ENABLE_AVATARS`; when enabled,
  avatars are downloaded and cached server-side as described in :ref:`avatars`.

International transfers
-----------------------

- Weblate itself does not require a specific hosting region.
- Hosting location, backups, e-mail delivery, repository hosting, external
  authentication, analytics, error reporting, and machine translation services
  determine where data is processed.
- Organizations can self-host Weblate in the required jurisdiction, or use a
  dedicated deployment with suitable infrastructure controls.

Regulatory mapping
==================

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Framework
     - Supporting Weblate features
   * - GDPR (EU)
     - Data export, correction, account removal, audit logs, privacy notices,
       configurable retention, self-hosting
   * - CCPA (California)
     - Data access, deletion workflow, user control, no built-in sale of
       personal data
   * - LGPD (Brazil)
     - Transparency, access, correction, deletion workflow, operator-defined
       legal basis
   * - nFADP (Switzerland)
     - Transparency, purpose limitation by configuration, account controls,
       auditability
   * - PIPEDA (Canada)
     - Notice, consent workflow, access, correction, deletion
   * - DPDPA (India)
     - Notice, consent workflow, user rights handling, hosting locality
       controlled by operator
   * - PIPL (China)
     - Purpose limitation by configuration, data minimization, self-hosted
       locality controls

Recommendations for compliance
==============================

- **Notices and consent:** Provide privacy, cookie, subcontractor, and terms
  information through :ref:`legal`, and update :setting:`LEGAL_TOS_DATE` when
  users must accept changed terms.
- **Policy links:** Link external privacy and legal documents with
  :setting:`PRIVACY_URL` and :setting:`LEGAL_URL` when the documents are hosted
  outside Weblate.
- **Data subject requests:** Define an operational process for user-data
  export, correction, account removal, backup handling, and historical
  contribution review.
- **Retention:** Configure :setting:`AUDITLOG_EXPIRY` and document retention
  periods for database backups, log aggregation, mail systems, repositories,
  and external integrations.
- **External services:** Review configured authentication providers, avatar
  providers, analytics, Sentry, GELF logging, machine translation, e-mail, and
  repository integrations for transfer and processor obligations.
- **Locality:** Ensure application hosting, backups, logs, repositories, and
  external processors are located in permitted jurisdictions.
