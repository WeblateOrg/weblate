Weblate threat model
====================

**Scope:** Core Weblate web application, its interactions with user browsers, backend components (web server, WSGI, database, datastore, Celery), and integration with external VCS.

**Assumptions:** Standard Weblate deployment with typical components (nginx/Apache, granian/Gunicorn/uWSGI, PostgreSQL, datastore, Celery) and user roles (unauthenticated user, authenticated user, reviewer, project manager, administrator, project-scoped API token).

Webhook endpoints for some VCS integrations are intentionally
compatibility-oriented and can accept unauthenticated deliveries from
supported forges. Weblate therefore treats webhook-triggered repository
updates as a deployment-hardened interface rather than a cryptographically
authenticated one by default.

Until native authenticated integrations are available for these platforms,
webhook abuse resistance depends on compensating controls such as reverse-proxy
rate limiting, request size limits, minimizing public exposure, and monitoring.

System description and scope
----------------------------

Weblate is an open-source web-based localization platform built on Django. It
integrates tightly with Git repositories to manage translations and offers
CI/CD-style features for automation, hooks, and VCS synchronization.

Authorization in Weblate is not limited to instance-wide administrator versus
regular user access. Permissions can be delegated per site, project,
component, language, glossary, or other scope, including dedicated VCS,
translation memory, screenshot, review, and project access management
permissions. Project-scoped API tokens can also be granted team memberships and
permissions similar to users.

Assets:

* **Confidentiality:** Translation strings, API keys/credentials for VCS integration, user credentials (passwords, 2FA secrets), user personal data (email, name), session tokens, audit logs, private project data.
* **Integrity:** Translation string content, VCS repository integrity, project and component configurations, user permissions, audit logs.
* **Availability:** Weblate web interface, VCS integration, database access, background task processing.
* **Authenticity/Non-repudiation:** Translation commit history, user attribution for translations, audit logs of administrative actions.

Conceptual data flow diagram
----------------------------

.. graphviz::

   digraph translations {
      graph [fontname = "sans-serif", fontsize=10];
      node [fontname = "sans-serif", fontsize=10, margin=0.1, height=0, style=filled, fillcolor=white, shape=note];
      edge [fontname = "sans-serif", fontsize=10, dir=both];

      "External user (browser)" -> "Web server (nginx/Apache)" [label="HTTPS"];
      "External webhook source" -> "Web server (nginx/Apache)" [label="HTTPS webhook"];
      "Web server (nginx/Apache)" -> "Weblate application (WSGI, Celery)" [label="Internal API"];
      "Weblate application (WSGI, Celery)" -> "Database (PostgreSQL)" [label="Database access"];
      "Weblate application (WSGI, Celery)" -> "Datastore (Valkey/Redis)" [label="Key/value access"];
      "Weblate application (WSGI, Celery)" -> "Internal VCS repository" [label="Filesystem access"];
      "Weblate application (WSGI, Celery)" -> "External VCS repository" [label="Git/API"];
      "Weblate application (WSGI, Celery)" -> "Logging (SIEM)" [label="GELF"];
   }


Trust boundaries
----------------

* **Internet ↔ Web server:** Public internet traffic interacting with the first line of defense.
* **Webhook source ↔ Web server:** External code hosting services or other callers invoking repository hooks, sometimes with unauthenticated endpoints enabled per project.
* **Web server ↔ Weblate application:** Communication between the reverse proxy/web server and the application logic.
* **Weblate application ↔ Database:** Application logic accessing persistent and cached data.
* **Weblate application ↔ Logging:** Application logic creating logs.
* **Weblate application ↔ Internal VCS repository:** Application logic interacting with its local copy of the VCS repository.
* **Weblate application ↔ External VCS repository:** Weblate reaching out to external code hosting platforms.
* **Privileged user configuration ↔ Outbound network:** Project and integration settings can cause Weblate to initiate connections to external VCS hosts or other services.
* **Imported backup archive ↔ Weblate application/filesystem:** Backup restore processes attacker-controlled archive contents, metadata, and VCS state.
* **Unauthenticated caller ↔ Authenticated user/token:** Different privilege levels for browser, API, and webhook access.
* **Authenticated user/token ↔ Project manager/reviewer/VCS manager:** Delegated project- and component-scoped permissions create additional privilege boundaries inside the application.

Threat identification
---------------------

.. list-table::
   :header-rows: 1

   * - Component/Interaction
     - STRIDE threat category
     - Threat description
     - Potential impact
   * - **Web server** (nginx/Apache)
     - **DoS**
     - **Denial of service:** Attacker floods the web server with requests, making Weblate unavailable.
     - Loss of availability for translation.
   * -
     - **Information disclosure**
     - **Configuration exposure:** Misconfigured server exposes sensitive files (e.g., config files, private keys).
     - Exposure of credentials, internal architecture.
   * -
     - **Tampering**
     - **Malicious request injection:** Attacker injects malicious data into HTTP headers or request bodies.
     - Potential for SQL injection, XSS, or other injections if not properly handled by the backend.
   * - **Webhook handling**
     - **Spoofing**
     - **Forged webhook delivery:** An attacker submits a fake webhook payload to trigger repository updates or other automation, especially when unauthenticated hooks are enabled.
     - Unauthorized repository synchronization, noisy task execution, or follow-on abuse of automation paths.
   * -
     - **Tampering**
     - **Payload manipulation or replay:** An attacker replays or modifies webhook payloads so Weblate processes repository states or branches different from the legitimate event.
     - Unexpected updates, repository confusion, or misuse of privileged VCS credentials.
   * -
     - **DoS**
     - **Hook flooding:** An attacker sends excessive webhook requests or oversized payloads, overwhelming request handling or background workers.
     - Weblate slowdown or unavailability.
   * -
     - **Information disclosure**
     - **Repository enumeration via webhook responses:** An attacker probes webhook payloads and learns whether repositories, branches, or components exist based on response metadata.
     - Disclosure of private project structure, enabled hooks, or component identifiers.
   * -
     - **Repudiation**
     - **Limited webhook attribution:** Hook-triggered updates are recorded as coming from a service bot rather than a forge-authenticated principal.
     - Reduced forensic confidence when investigating malicious or disputed hook activity.
   * - **Weblate application**
     - **Spoofing**
     - **User impersonation:** Attacker gains access to a legitimate user's session (e.g., via session hijacking, compromised credentials).
     - Unauthorized translation, repo access.
   * - (WSGI/Celery)
     - **Tampering**
     - **Unauthorized translation modification:** Malicious user or exploited vulnerability allows altering translations, project configs, or VCS integration settings.
     - Incorrect translations, broken build, RCE via VCS hooks.
   * -
     - **Tampering**
     - **VCS integration manipulation:** Attacker manipulates Weblate's interaction with the VCS (e.g., injecting malicious commands via crafted repository URLs if not sanitized, leading to RCE).
     - Code injection in target projects, data exfiltration.
   * -
     - **Repudiation**
     - **Unattributed changes:** Malicious changes are made without proper attribution to the user or system responsible.
     - Difficulty in auditing and accountability.
   * -
     - **Information disclosure**
     - **Sensitive data leakage:** SQL injection, insecure API endpoints, or errors disclose sensitive data (e.g., other users' translations, VCS credentials, server information).
     - Privacy breach, intellectual property theft.
   * -
     - **Information disclosure**
     - **VCS credentials exposure:** Weblate's stored VCS credentials (SSH keys, tokens) are accessed by an attacker.
     - Direct access to integrated code repositories.
   * -
     - **DoS**
     - **Resource exhaustion:** Excessive background tasks or inefficient database queries triggered by an attacker lead to system slowdown or crash.
     - Weblate unavailability.
   * -
     - **Elevation of privilege**
     - **Role escalation:** A regular translator gains administrative privileges.
     - Complete system compromise.
   * -
     - **Elevation of privilege**
     - **Command injection:** Arbitrary code execution due to improper input validation in repository URLs or add-ons.
     - System compromise, data exfiltration.
   * - **Backup import / restore**
     - **DoS**
     - **Archive amplification during restore:** A crafted backup contains many members or a large aggregate uncompressed size, exhausting disk, memory, worker time, or inode capacity.
     - Restore-time denial of service and possible service degradation for the instance.
   * -
     - **Tampering**
     - **Malicious backup metadata or VCS state:** A crafted backup restores misleading project metadata or unsafe repository state despite path validation and schema checks.
     - Corrupted restored projects, unsafe repository state, or administrative confusion.
   * - **Database/Datastore**
     - **Tampering**
     - **Data corruption:** Direct access to the database allows altering translation strings, user data, or configuration.
     - System malfunction, data integrity loss.
   * -
     - **Information disclosure**
     - **Sensitive data access:** Unauthorized access to database/datastore exposes all stored data (credentials, translation memory, user profiles).
     - Major data breach.
   * -
     - **DoS**
     - **Database exhaustion:** Attacker floods the database or datastore with queries, or consumes all memory or available connections.
     - Weblate unavailability.
   * - **VCS integration**
     - **Tampering**
     - **Malicious commits from Weblate:** Compromised Weblate pushes malicious changes to the upstream repository.
     - Introduction of malware/backdoors into target projects.
   * -
     - **Repudiation**
     - **Fake commit attribution:** Weblate commits changes attributed to a wrong user (e.g., an admin forcing a commit in a translator's name without their consent).
     - Accountability issues.
   * - **Outbound integrations / VCS configuration**
     - **Information disclosure**
     - **Server-side request forgery or unintended internal reachability:** A privileged user configures repository or integration endpoints that cause Weblate to connect to internal or otherwise restricted hosts.
     - Exposure of internal services, metadata endpoints, or restricted network paths.
   * - **User interaction**
     - **Spoofing**
     - **Phishing/social engineering:** Attacker tricks users into revealing credentials for Weblate or linked VCS accounts.
     - Account compromise.
   * - (Web UI)
     - **Tampering**
     - **Cross-Site scripting (XSS):** Malicious scripts injected into translations or user profiles execute in other users' browsers.
     - Session hijacking, credential theft, defacement.
   * -
     - **Information disclosure**
     - **Clickjacking/UI redress:** Attacker overlays malicious UI elements over Weblate, tricking users into unintended actions.
     - Unauthorized actions, data manipulation.
   * -
     - **Information disclosure**
     - **Sensitive data in UI:** Unintended exposure of sensitive data (e.g., another user's email) in the UI due to authorization flaws.
     - Privacy breach.

Mitigation strategies
---------------------

* **Authentication & authorization:**
    * Strong password policies, see :doc:`/security/passwords`.
    * Enforced 2FA, see :ref:`2fa`.
    * Robust session management.
    * Role-based access control (RBAC) to enforce the least privilege (for example separating translation, review, VCS, translation memory, screenshot, and project access management permissions), see :doc:`/admin/access`.
    * Integration with external identity providers (SAML, OAuth, LDAP), see :doc:`/admin/auth`.
* **Webhook security:**
    * Current product limitation: webhook authenticity is not uniformly enforced in-app for all supported forge integrations.
    * Treat webhook endpoints as deployment-hardened interfaces and enable them only where necessary, see :ref:`hooks` and :ref:`project-enable_hooks`.
    * Deployment controls required today include reverse-proxy rate limiting, request size limits, optional source-IP filtering, minimizing public exposure, and alerting on webhook spikes.
    * Validate webhook event type and payload before triggering repository updates or tasks.
    * Future product direction is to replace compatibility webhooks with native authenticated integrations that validate source authenticity before scheduling repository updates.
* **Input validation and output encoding:**
    * Strict validation of all user inputs (forms, API requests, VCS URLs) to prevent injection attacks (SQL injection, command injection, XSS).
    * Context-aware output encoding for all user-supplied data displayed on the web UI to prevent XSS.
* **VCS integration security:**
    * Principle of least privilege for VCS credentials (e.g., read-only access where possible, limited scopes for tokens).
    * Secure storage of VCS credentials.
    * Strict sanitization and validation of all data coming from VCS (e.g., filenames, branch names, commit messages that might be displayed).
    * Secure execution of Git/Mercurial commands (avoiding shell execution with user-controlled input).
    * Document and review hostname allowlisting and private-network restrictions for outbound integrations where deployments need to constrain server-initiated connections.
* **Backup import security:**
    * Treat backup archives as untrusted input and validate both metadata and extracted paths.
    * Enforce aggregate archive-size and extraction-budget limits, not only per-entry checks.
    * Monitor restore failures and unusually large imports as potential abuse indicators.
* **Data protection:**
    * Encryption of sensitive data at rest.
    * Encryption of data in transit (TLS/SSL for all HTTP/S and VCS communication).
    * Database hardening (the least privilege for Weblate user, strong passwords).
* **System hardening:**
    * Regular patching of OS, Weblate, and all dependencies.
    * Principle of least privilege for Weblate user account on the OS.
    * Network segmentation (e.g., separating database and datastore from public access).
    * Use of WAF (Web Application Firewall).
* **Logging and monitoring:**
    * Comprehensive audit logging of all security-relevant events (logins, failed logins, permission changes, critical configuration changes, VCS operations).
    * Centralized logging and alerting for security incidents, for example :ref:`graylog`.
* **Secure development practices:**
    * Code reviews with a security focus.
    * Static Application Security Testing (SAST) and Dynamic Application Security Testing (DAST), see :doc:`/contributing/code`.
    * Dependency vulnerability scanning, see :doc:`/security/dependencies`.
    * Regular security audits and penetration testing.
* **Error handling:**
    * Generic error messages that do not reveal sensitive internal information.
