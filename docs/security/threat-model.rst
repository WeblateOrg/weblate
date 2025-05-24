Weblate threat model
====================

**Scope:** Core Weblate web application, its interactions with user browsers, backend components (web server, WSGI, database, Redis, Celery), and integration with external VCS.
**Assumptions:** Standard Weblate deployment with typical components (nginx/Apache, Gunicorn/uWSGI, PostgreSQL, Redis, Celery) and user roles (Unauthenticated, Translator, Project Manager, Administrator).

System description and scope
----------------------------

Weblate is an open-source web-based localization platform built on Django. It
integrates tightly with Git repositories to manage translations and offers
CI/CD-style features for automation, hooks, and VCS synchronization.

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
      "Web server (nginx/Apache)" -> "Weblate application (WSGI, Celery)" [label="Internal API"];
      "Weblate application (WSGI, Celery)" -> "Database (PostgreSQL, Redis)" [label="Database access"];
      "Weblate application (WSGI, Celery)" -> "Internal VCS repository" [label="Filesystem access"];
      "Weblate application (WSGI, Celery)" -> "External VCS repository" [label="Git/API"];
      "Weblate application (WSGI, Celery)" -> "Logging (SIEM)" [label="GELF"];
   }


Trust boundaries
----------------

* **Internet ↔ Web server:** Public internet traffic interacting with the first line of defense.
* **Web server ↔ Weblate application:** Communication between the reverse proxy/web server and the application logic.
* **Weblate application ↔ Database** Application logic accessing persistent and cached data.
* **Weblate application ↔ Logging:** Application logic creating logs.
* **Weblate application ↔ Internal VCS repository:** Application logic interacting with its local copy of the VCS repository.
* **Weblate application ↔ External VCS repository:** Weblate reaching out to external code hosting platforms.
* **Authenticated User ↔ Unauthenticated User:** Different privilege levels within the web application.

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
   * - **Database/Redis**
     - **Tampering**
     - **Data corruption:** Direct access to the database allows altering translation strings, user data, or configuration.
     - System malfunction, data integrity loss.
   * -
     - **Information disclosure**
     - **Sensitive data access:** Unauthorized access to database/Redis exposes all stored data (credentials, translation memory, user profiles).
     - Major data breach.
   * -
     - **DoS**
     - **Database exhaustion:** Attacker floods the database with queries, or consumes all Redis memory/connections.
     - Weblate unavailability.
   * - **VCS integration**
     - **Tampering**
     - **Malicious commits from Weblate:** Compromised Weblate pushes malicious changes to the upstream repository.
     - Introduction of malware/backdoors into target projects.
   * -
     - **Repudiation**
     - **Fake commit attribution:** Weblate commits changes attributed to a wrong user (e.g., an admin forcing a commit in a translator's name without their consent).
     - Accountability issues.
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
    * Role-based access control (RBAC) to enforce the least privilege (e.g., translators can only edit translations, not change project configs), see :doc:`/admin/access`.
    * Integration with external identity providers (SAML, OAuth, LDAP), see :doc:`/admin/auth`.
* **Input validation and output encoding:**
    * Strict validation of all user inputs (forms, API requests, VCS URLs) to prevent injection attacks (SQL injection, command injection, XSS).
    * Context-aware output encoding for all user-supplied data displayed on the web UI to prevent XSS.
* **VCS integration security:**
    * Principle of least privilege for VCS credentials (e.g., read-only access where possible, limited scopes for tokens).
    * Secure storage of VCS credentials.
    * Strict sanitization and validation of all data coming from VCS (e.g., filenames, branch names, commit messages that might be displayed).
    * Secure execution of Git/Mercurial commands (avoiding shell execution with user-controlled input).
* **Data protection:**
    * Encryption of sensitive data at rest.
    * Encryption of data in transit (TLS/SSL for all HTTP/S and VCS communication).
    * Database hardening (the least privilege for Weblate user, strong passwords).
* **System hardening:**
    * Regular patching of OS, Weblate, and all dependencies.
    * Principle of least privilege for Weblate user account on the OS.
    * Network segmentation (e.g., separating database/Redis from public access).
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
