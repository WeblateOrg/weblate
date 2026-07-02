Weblate threat model
====================

Project: Weblate

Last reviewed for Weblate |release| at commit ``491e79010b2``.

Date: 2026-05-14.

Status: Accepted, 2026-05-14.

Version binding: This model is versioned with Weblate releases. A report
against Weblate version N is triaged against the model published for version N,
not against the latest development branch. *(maintainer)*

Reporting cross-reference: Reports that violate a property Weblate claims in
`Security properties Weblate provides`_ are reported through :file:`SECURITY.md`
and :doc:`/security/issues`. Reports that fall under `Out of scope`_ or
`Security properties Weblate does not provide`_ can be closed by citing this
document unless this model routes them to ``VALID-HARDENING``. *(documented)*
(source: :doc:`/security/issues`)

Provenance legend: ``*(documented)*`` means the claim is stated in Weblate
documentation; ``*(maintainer)*`` means it was stated by a maintainer during
this threat-model process; ``*(inferred)*`` means it was reasoned from the
current project shape and needs maintainer confirmation.

Provenance summary: 103 documented / 64 maintainer / 0 inferred claims.

Weblate is a Django-based web localization platform. It accepts work from
browser users, API clients, project-scoped tokens, repository webhooks, VCS
repositories, backup archives, background workers, and configured external
services, then stores and synchronizes translation projects through a database,
datastore, local filesystem repositories, and external code-hosting systems.
*(documented)* (source: :doc:`/index`, :doc:`/api`, :doc:`/admin/continuous`)

Scope and intended use
----------------------

.. list-table::
   :header-rows: 1

   * - Component family
     - Representative surface
     - Outside-process effects
     - Model status
   * - Web UI and REST API
     - Browser views, forms, session endpoints, :doc:`/api`
     - Database, datastore, e-mail, logs, uploaded files
     - In scope. *(documented)* (source: :doc:`/api`, :doc:`/admin/install`)
   * - Authentication, sessions, and authorization
     - Login, 2FA, SSO, teams, permissions, project access, API tokens
     - Database, identity providers, browser cookies
     - In scope. *(documented)* (source: :doc:`/admin/auth`, :doc:`/admin/access`)
   * - Project-scoped API tokens
     - Tokens created in project :guilabel:`API access`
     - Same application effects as the token permissions allow
     - In scope as authenticated actors with delegated project scope.
       *(documented)* (source: :doc:`/api`, :doc:`/admin/access`)
   * - Webhooks
     - :ref:`hooks`, project :ref:`project-enable_hooks`,
       :ref:`code-hosting-github-app-webhook`
     - Background task scheduling and VCS repository updates
     - In scope as a public, deployment-hardened interface. *(documented)* (source: :ref:`hooks`, :ref:`project-enable_hooks`, :ref:`code-hosting-github-app-webhook`)
   * - VCS integration
     - Repository URLs, branches, pushes, pulls, merge requests, local clones
     - Filesystem, child VCS commands, SSH/HTTPS network connections
     - In scope when reachable through Weblate configuration or project
       content. *(documented)* (source: :doc:`/admin/continuous`,
       :doc:`/admin/code-hosting`)
   * - Background tasks
     - Celery queues for repository updates, notifications, translation memory,
       translation, and backups
     - Database, datastore, filesystem, outbound network
     - In scope as Weblate-controlled execution of user or operator actions.
       *(documented)* (source: :doc:`/admin/install`)
   * - Project backup import/export
     - :ref:`projectbackup`, :doc:`/api` project backup endpoints,
       :wladmin:`import_projectbackup`
     - Uploaded ZIP archives, generated backup archives, filesystem restore,
       repository state
     - In scope. *(documented)* (source: :doc:`/admin/backup`, :doc:`/api`,
       :doc:`/admin/management`)
   * - Service backup
     - BorgBackup configuration and :wladmin:`backup`
     - Local or remote backup storage over filesystem or SSH
     - In scope for Weblate's handling of configured backup jobs; Borg itself
       is out of scope. *(documented)* (source: :doc:`/admin/backup`,
       :doc:`/admin/management`)
   * - Machine translation and outbound integrations
     - Machine translation, avatars, status reporting, telemetry, error
       reporting, VCS hosts, GitHub App connections, CDN add-on, Fedora
       Messaging add-on
     - Outbound HTTP(S), AMQP(S), provider APIs, logs
     - In scope for Weblate's enforcement of configured access and network
       restrictions. Provider behavior is out of scope. *(documented)* (source: :doc:`/admin/config`, :doc:`/admin/code-hosting`, :doc:`/admin/addons`)
   * - Add-ons
     - Built-in add-ons and administrator-configured add-on execution
     - Varies by add-on; can mutate repositories or contact services
     - Built-in add-ons are in scope when enabled. Third-party add-ons are out
       of scope except for Weblate's permission and installation gates.
       *(maintainer)*
   * - Management commands
     - :program:`weblate` commands run by an operator
     - Database, filesystem, VCS, backup storage
     - In scope when processing untrusted Weblate data; the local operator
       shell is trusted. *(maintainer)*
   * - Tests, generated docs, screenshots, development fixtures
     - :file:`docs/_build/`, :file:`docs/screenshots/`, tests, local fixtures
     - Development-only files and generated artifacts
     - Out of scope for product security claims. *(maintainer)*

The intended deployment is a server-side Weblate installation behind a web
server or reverse proxy, with a WSGI application server, PostgreSQL database,
datastore, Celery workers, a writable data directory, and optional outbound VCS,
backup, identity-provider, and machine-translation integrations. *(documented)* (source: :doc:`/admin/install`)

The relevant actors are split by trust level: unauthenticated clients,
authenticated users, reviewers, project managers, administrators,
project-scoped API tokens, webhook senders, external VCS providers, configured
external services, and local operators. *(documented)* (source: :doc:`/admin/access`,
:doc:`/api`)

Weblate is not intended to be embedded as an in-process security library, used
as a sandbox for untrusted code, or exposed without the deployment controls
documented for production use. *(maintainer)*

Out of scope
------------

The following are explicit non-goals for this model:

* A compromised operating system account, container runtime, database server,
  datastore, reverse proxy, or administrator shell. Weblate runs inside those
  boundaries and does not claim to protect itself from an already-compromised
  host. *(maintainer)*
* A malicious Weblate site administrator or local operator with unrestricted
  server access. Such an actor can change settings, credentials, data, or code.
  *(maintainer)*
* Vulnerabilities in third-party dependencies as independent projects. General
  Django, Django REST framework, Python Social Auth, BorgBackup, VCS, database,
  and provider vulnerabilities are reported upstream unless the issue is in
  Weblate's use of them. *(documented)* (source: :doc:`/security/issues`)
* Build and release hygiene, including action pinning, artifact signing,
  dependency freshness, and repository branch protection. These affect project
  operations but are not threat-model claims about Weblate runtime behavior.
  *(maintainer)*
* General security of external VCS providers, identity providers, mail servers,
  machine-translation services, avatar services, CDN storage, or backup
  storage. Weblate models only its configured interactions with them.
  *(maintainer)*
* User organizations' translation-supply-chain choices outside Weblate.
  Outsourced or crowdsourced translator risks are described separately in
  :doc:`/security/localization-threat`. *(documented)* (source: :doc:`/security/localization-threat`)
* Third-party add-on code, local customization code, development fixtures,
  generated documentation output, test-only code, and demo or example data.
  *(maintainer)*

Trust boundaries and data flow
------------------------------

Weblate's primary trust boundary is the network-facing application surface:
browser views, API endpoints, webhook endpoints, and upload endpoints accept
data from less-trusted actors and translate it into database rows, local
repository state, background tasks, outbound requests, and rendered UI.
*(maintainer)*

.. list-table::
   :header-rows: 1

   * - Boundary
     - Trust transition
   * - Client browser/API client to Weblate
     - Untrusted or authenticated requests become permission-checked
       application actions. *(documented)* (source: :doc:`/api`, :doc:`/admin/access`)
   * - Webhook sender to Weblate
     - Public forge notifications can schedule repository synchronization
       where hooks are enabled. GitHub App webhooks additionally authenticate
       with a per-App URL token and GitHub signature
       verification before processing. *(documented)* (source: :ref:`hooks`,
       :ref:`project-enable_hooks`, :ref:`code-hosting-github-app-webhook`)
   * - Weblate to database/datastore
     - Permission-checked application state becomes persistent data and queued
       work. *(documented)* (source: :doc:`/admin/install`)
   * - Weblate to local VCS repositories
     - Project configuration and repository content drive filesystem and VCS
       operations. *(documented)* (source: :doc:`/admin/continuous`)
   * - Weblate to external services
     - Configured URLs, credentials, and provider settings drive outbound
       network connections. *(documented)* (source: :doc:`/admin/code-hosting`,
       :doc:`/admin/config`)
   * - Project backup archives and Weblate filesystem
     - Uploaded ZIP members and metadata become restored project state;
       generated project backups are written to and read from local backup
       storage. *(documented)* (source: :doc:`/admin/backup`, :doc:`/api`,
       :ref:`projectbackup`)

Reachability preconditions:

* A web UI or API finding is in model only when reachable by an unauthenticated
  client, authenticated user, or project-scoped token through documented
  routes, forms, or API endpoints. *(maintainer)*
* An authorization finding is in model only when it crosses a documented
  permission, team, project, component, language, glossary, token, or site-wide
  boundary. *(documented)* (source: :doc:`/admin/access`)
* A webhook finding is in model only when a request can reach an enabled hook
  endpoint and affect repository update scheduling, task volume, or information
  returned to the caller. *(documented)* (source: :ref:`hooks`,
  :ref:`project-enable_hooks`)
* A VCS finding is in model only when attacker-controlled or less-trusted
  repository data, branch names, URLs, file names, commit metadata, or project
  configuration can influence Weblate's VCS operations. *(maintainer)*
* A backup import finding is in model only when reachable from a project backup
  uploaded through Weblate or supplied to :wladmin:`import_projectbackup`.
  *(documented)* (source: :ref:`projectbackup`, :wladmin:`import_projectbackup`)
* A backup export finding is in model only when reachable from documented
  project backup creation or download routes, including the REST API for users
  or project-scoped tokens with project edit permission.
  *(documented)* (source: :doc:`/api`, :ref:`projectbackup`, :doc:`/admin/access`)
* A background-task finding is in model only when the task can be queued from
  an in-scope Weblate surface or scheduled Weblate maintenance path.
  *(documented)* (source: :doc:`/admin/install`)
* A management-command finding is in model only when untrusted Weblate data is
  processed by the command; arbitrary local shell access is not an attacker
  capability. *(maintainer)*

Environment assumptions
-----------------------

Weblate assumes a supported Python and Django runtime, a correctly configured
database, a datastore, a writable data directory, and running workers for
features that require background processing. *(documented)* (source: :doc:`/admin/install`)

Production deployments are expected to configure the external web server or
reverse proxy consistently with Weblate's HTTPS, host header, body-size, and
proxy-header settings. *(documented)* (source: :doc:`/admin/install`,
:setting:`ENABLE_HTTPS`, :setting:`ALLOWED_HOSTS`)

The database, datastore, and internal service ports are assumed not to be
directly exposed to untrusted networks. *(maintainer)*

Filesystem permissions are assumed to prevent unrelated local users from
modifying Weblate's data directory, configuration, VCS repositories, generated
SSH wrappers, backups, and secret material. *(documented)* (source: :doc:`/admin/backup`,
:doc:`/admin/install`)

Celery workers are trusted components of the same Weblate instance. A malicious
or compromised worker is equivalent to a compromised application process.
*(maintainer)*

VCS command execution, SSH, and HTTPS clients are assumed to execute as the
Weblate service user with the credentials configured for the relevant project
or integration, including database-stored GitHub App credentials used for
installation tokens and webhook signature verification. *(documented)* (source: :doc:`/admin/code-hosting`,
:setting:`SSH_EXTRA_ARGS`)

What Weblate does to its host:

* It opens outbound network connections for configured VCS, identity-provider,
  avatar, machine-translation, backup, status-reporting, telemetry,
  error-reporting, and add-on features such as outbound webhooks and Fedora
  Messaging AMQP delivery.
  *(documented)* (source: :doc:`/admin/config`, :doc:`/admin/code-hosting`,
  :doc:`/admin/backup`)
* It runs VCS and backup-related helper commands as part of repository and
  backup workflows. *(documented)* (source: :doc:`/admin/continuous`,
  :doc:`/admin/backup`)
* It writes to the configured data directory, repository storage, media/fonts,
  backup dumps, logs, and cache locations. *(documented)* (source: :doc:`/admin/config`,
  :doc:`/admin/backup`)
* It sends e-mail and notifications when configured to do so. *(documented)* (source: :doc:`/admin/config`)
* It does not claim to be free of process-wide side effects such as logging,
  cache writes, subprocess execution, or outbound network access. *(maintainer)*

Build-time and configuration variants
-------------------------------------

.. list-table::
   :header-rows: 1

   * - Knob
     - Default or documented posture
     - Effect on the model
     - Maintainer stance
   * - :setting:`ENABLE_HOOKS` and :ref:`project-enable_hooks`
     - Anonymous remote hooks are configurable and must also be enabled for a
       project. *(documented)*
     - Exposes webhook endpoints as a public scheduling interface. Abuse
       resistance depends on deployment controls. *(documented)* (source: :ref:`hooks`, :ref:`project-enable_hooks`)
     - Production deployments exposing hooks use reverse-proxy rate limits,
       body-size limits, monitoring, and minimal public exposure. *(maintainer)*
   * - :setting:`ENABLE_HTTPS`, proxy SSL headers, and HSTS settings
     - HTTPS affects secure cookies, redirects, HSTS, WebAuthn, and generated
       URLs. *(documented)* (source: :setting:`ENABLE_HTTPS`)
     - Disabling or misconfiguring HTTPS removes transport and cookie
       protections that Weblate relies on for browser security. *(documented)* (source: :setting:`ENABLE_HTTPS`)
     - The documented production posture is HTTPS with correct proxy headers.
       *(documented)*
   * - :setting:`ALLOWED_HOSTS`
     - Configures accepted HTTP hostnames. *(documented)* (source: :setting:`ALLOWED_HOSTS`)
     - Broad host acceptance can weaken host-header based protections and URL
       generation assumptions. *(maintainer)*
     - Production deployments restrict this to instance hostnames. *(maintainer)*
   * - :envvar:`WEBLATE_API_RATELIMIT_ANON`,
       :envvar:`WEBLATE_API_RATELIMIT_USER`, :setting:`RATELIMIT_ATTEMPTS`,
       and ``RATELIMIT_GITHUB_SETUP_ATTEMPTS``
     - Rate limits are configurable. *(documented)* (source: :doc:`/api`,
       :doc:`/admin/config`)
     - Availability claims assume rate limits appropriate to deployment size
       and exposure. *(maintainer)*
     - Disabling rate limits changes DoS triage from Weblate bug to deployment
       posture unless a single request violates a claimed property.
       *(maintainer)*
   * - :setting:`CSP_SCRIPT_SRC`, :setting:`CSP_IMG_SRC`,
       :setting:`CSP_CONNECT_SRC`, :setting:`CSP_STYLE_SRC`,
       :setting:`CSP_FONT_SRC`, :setting:`CSP_FORM_SRC`
     - Content Security Policy sources are configurable. *(documented)* (source: :doc:`/admin/config`)
     - Broadening sources can reduce browser-side containment for XSS or
       third-party content. *(maintainer)*
     - Deployments adding third-party sources accept that expanded browser
       trust. *(maintainer)*
   * - :setting:`PROJECT_BACKUP_UPLOAD_MAX_SIZE`,
       :setting:`PROJECT_BACKUP_IMPORT_MAX_MEMBERS`,
       :setting:`PROJECT_BACKUP_IMPORT_MAX_TOTAL_UNCOMPRESSED_SIZE`,
       :setting:`PROJECT_BACKUP_IMPORT_MAX_COMPRESSED_ENTRY_SIZE`,
       :setting:`PROJECT_BACKUP_IMPORT_MIN_RATIO_SIZE`,
       :setting:`PROJECT_BACKUP_IMPORT_MAX_COMPRESSED_ENTRY_RATIO`
     - Defaults bound project backup upload and import size, member count, and
       suspicious compression ratios. *(documented)* (source: :doc:`/admin/config`)
     - Raising or disabling these limits expands restore-time resource exposure.
       *(documented)* (source: :doc:`/admin/config`)
     - The defaults documented above are part of backup-import resource guarantees.
       *(documented)*
   * - Private-target restrictions and allowlists for outbound URLs
     - User-configurable outbound URL surfaces documented with private-target
       restriction settings, including Fedora Messaging AMQP broker URLs,
       reject internal or non-public targets by default. *(documented)*
       (source: :setting:`ASSET_RESTRICT_PRIVATE`,
       :setting:`PROJECT_WEB_RESTRICT_PRIVATE`,
       :setting:`WEBHOOK_RESTRICT_PRIVATE`, :setting:`VCS_RESTRICT_PRIVATE`)
     - Allowlist settings and privileged configuration can intentionally expand
       reachability. *(documented)* (source: :setting:`ASSET_PRIVATE_ALLOWLIST`,
       :setting:`PROJECT_WEB_RESTRICT_ALLOWLIST`,
       :setting:`WEBHOOK_PRIVATE_ALLOWLIST`, :setting:`VCS_ALLOW_HOSTS`)
     - Default private-target rejection is an application-level security
       property for the documented user-configurable URL surfaces.
       *(maintainer)*
   * - :setting:`SSH_EXTRA_ARGS`
     - Allows custom SSH options. *(documented)* (source: :setting:`SSH_EXTRA_ARGS`)
     - Weakening SSH algorithms or host verification changes VCS transport
       assumptions. *(maintainer)*
     - Operators own the security impact of custom SSH options. *(maintainer)*
   * - Third-party add-ons and local customization
     - Administrators can extend behavior. *(documented)* (source: :doc:`/admin/addons`)
     - Custom code can add new trust boundaries and security properties outside
       this model. *(maintainer)*
     - Third-party code is modeled separately. *(maintainer)*

Input assumptions
-----------------

.. list-table::
   :header-rows: 1

   * - Surface
     - Input
     - Attacker-controllable?
     - Caller or operator must enforce
   * - Browser forms and REST API
     - Request bodies, query strings, uploaded files, headers, cookies
     - Yes, within the actor's authentication state. *(documented)* (source: :doc:`/api`)
     - HTTPS, correct host/proxy configuration, rate limits, and permission
       assignment. *(documented)* (source: :doc:`/admin/install`,
       :doc:`/admin/access`)
   * - Authentication endpoints
     - Passwords, WebAuthn data, SSO callbacks, reset tokens
     - Yes. *(documented)* (source: :doc:`/admin/auth`)
     - Correct identity-provider configuration and HTTPS. *(documented)* (source: :doc:`/admin/auth`, :setting:`ENABLE_HTTPS`)
   * - Project-scoped tokens
     - API requests authenticated by token
     - Yes, by whoever holds the token. *(documented)* (source: :doc:`/api`)
     - Token storage, rotation, and least-privilege team membership.
       *(maintainer)*
   * - Translation content
     - Source strings, translations, comments, suggestions, glossary entries
     - Yes, from users with relevant permissions or imported repositories.
       *(documented)* (source: :doc:`/user/translating`, :doc:`/admin/access`)
     - Review workflows for project-specific content integrity. *(documented)* (source: :doc:`/workflows`)
   * - Webhook endpoints
     - Headers, event type, body, repository and branch metadata
     - Yes, where endpoint is reachable. *(documented)* (source: :ref:`hooks`)
     - Hook enablement only where needed, request limits, and monitoring.
       *(maintainer)*
   * - GitHub App connection callbacks
     - GitHub OAuth code, signed Weblate state, installation ID, account metadata
     - Yes, from authenticated Weblate users and GitHub redirect query strings.
       *(documented)* (source: :ref:`code-hosting-github-app-register`)
     - Weblate requires workspace management rights and verifies that the
       GitHub user owns the personal installation or can administer the
       organization installation before saving it. *(documented)* (source:
       :ref:`code-hosting-github-app-register`)
   * - Repository configuration
     - Repository URLs, branches, push URLs, credentials, Gerrit review push
       options, add-on settings
     - Trusted to users with corresponding management permissions.
       *(documented)* (source: :doc:`/admin/access`, :doc:`/admin/continuous`)
     - Assign VCS and project management permissions only to trusted users.
       *(documented)* (source: :doc:`/admin/access`)
   * - External repository content
     - Translation files, paths, branch names, commit metadata
     - Yes, if the upstream repository is controlled by another actor.
       *(maintainer)*
     - Trust the configured upstream repository or review imported changes.
       *(maintainer)*
   * - Project backup import
     - ZIP archive members, metadata, translation files, repository state
     - Yes, for whoever can upload or provide the backup. *(documented)* (source: :ref:`projectbackup`)
     - Keep import limits at values appropriate for the instance. *(documented)* (source: :doc:`/admin/config`)
   * - Project backup export
     - Backup creation requests and requested backup file names
     - Yes, for users or project-scoped tokens with project edit permission.
       *(documented)* (source: :doc:`/api`, :ref:`projectbackup`, :doc:`/admin/access`)
     - Grant project edit permission only to trusted project administrators.
       *(documented)* (source: :doc:`/admin/access`)
   * - Machine translation and external service configuration
     - Provider URLs, credentials, model or service settings
     - Trusted to administrators or users granted configuration permissions.
       *(documented)* (source: :doc:`/admin/machine`, :doc:`/admin/access`)
     - Treat configured providers as recipients of the data sent to them; the
       submitted content varies by provider and enabled feature. *(maintainer)*
   * - Management commands
     - Command-line arguments and files supplied by the local operator
     - Trusted local input unless processing Weblate data or project backups.
       *(maintainer)*
     - Restrict shell access to trusted operators. *(maintainer)*

Size and rate assumptions:

* Weblate relies on application and reverse-proxy upload limits for large HTTP
  requests. *(documented)* (source: :setting:`PROJECT_BACKUP_UPLOAD_MAX_SIZE`)
* Project backup imports are bounded by member count, aggregate uncompressed
  size, compressed entry size, minimum ratio size, and compression ratio
  settings. *(documented)* (source: :doc:`/admin/config`)
* API and selected web actions are expected to be protected by configured rate
  limits. *(documented)* (source: :doc:`/api`, :doc:`/admin/config`)
* Repository size, number of projects, number of components, and worker
  capacity are deployment-sizing concerns unless a single in-scope input
  bypasses documented limits or permissions. *(maintainer)*

Adversary model
---------------

.. list-table::
   :header-rows: 1

   * - Actor
     - In-scope capabilities
     - Out-of-scope capabilities
   * - Unauthenticated internet client
     - Send HTTP(S) requests to public pages, registration, login, API, and
       reachable webhook endpoints. *(documented)* (source: :doc:`/api`)
     - Read server memory, bypass reverse proxy controls, or access internal
       services directly. *(maintainer)*
   * - Authenticated user
     - Perform actions allowed by assigned teams, permissions, and workflow.
       *(documented)* (source: :doc:`/admin/access`)
     - Act outside assigned permissions without exploiting a Weblate flaw.
       *(documented)* (source: :doc:`/admin/access`)
   * - Reviewer or project manager
     - Exercise delegated project, component, language, review, VCS,
       translation memory, screenshot, or access-management permissions.
       *(documented)* (source: :doc:`/admin/access`)
     - Become a site administrator unless granted that role or exploiting a
       Weblate flaw. *(maintainer)*
   * - Project-scoped API token holder
     - Use API permissions assigned to the token's team memberships, including
       project backup creation and download where project edit permission is
       granted. *(documented)* (source: :doc:`/api`, :doc:`/admin/access`,
       :ref:`projectbackup`)
     - Access projects, components, or site-wide functions outside its scope.
       *(documented)* (source: :doc:`/admin/access`)
   * - Webhook sender
     - Send forged, replayed, malformed, or high-volume webhook requests to
       enabled hook endpoints. *(documented)* (source: :ref:`hooks`)
     - Obtain forge-authenticated identity where Weblate does not verify it.
       *(maintainer)*
   * - External VCS or service provider
     - Return repository data, API responses, redirects, or errors according
       to the configured integration. *(documented)* (source: :doc:`/admin/code-hosting`)
     - Compromise the Weblate host except through data or protocol behavior
       Weblate processes. *(maintainer)*
   * - Translator or localization contributor
     - Submit translation content that downstream applications might consume.
       *(documented)* (source: :doc:`/security/localization-threat`)
     - Control downstream application escaping, rendering, or review policy
       outside Weblate. *(documented)* (source: :doc:`/security/localization-threat`)
   * - Local operator
     - Run management commands, change configuration, and access backups.
       *(documented)* (source: :doc:`/admin/management`, :doc:`/admin/backup`)
     - Local malicious operators are trusted for this model. *(maintainer)*

The modeled attacker tries to bypass authorization, modify translation or
repository data without permission, disclose private project or user data,
forge or abuse repository synchronization, trigger unsafe outbound requests,
execute commands through Weblate-controlled workflows, or exhaust bounded
application resources. *(maintainer)*

Security properties Weblate provides
------------------------------------

.. list-table::
   :header-rows: 1

   * - Property
     - Conditions
     - Violation symptom
     - Severity tier
   * - Web authorization separates site, project, component, language,
       glossary, VCS, translation memory, screenshot, review, and access
       management permissions. *(documented)* (source: :doc:`/admin/access`,
       :doc:`/admin/auth`)
     - Permission assignments match the intended trust relationship.
       Team-level enforced 2FA is satisfied by human users before
       team-derived permissions apply.
     - User or token can read or mutate data outside assigned scope.
     - Security-critical when private data or privileged mutation is exposed.
   * - Project-scoped API tokens are limited by assigned project/team
       permissions. *(documented)* (source: :doc:`/api`, :doc:`/admin/access`)
     - Token is created and stored by a trusted actor.
     - Token can act outside project or team scope.
     - Security-critical.
   * - Authentication and session controls protect browser sessions when HTTPS
       and proxy settings are correct. *(documented)* (source: :doc:`/admin/auth`,
       :setting:`ENABLE_HTTPS`)
     - Production HTTPS and secure-cookie settings are enabled.
     - Session fixation, credential bypass, or cross-user session confusion.
     - Security-critical.
   * - User-supplied content rendered by Weblate is expected not to execute
       script in other users' browsers. *(maintainer)*
     - Content is displayed through Weblate UI templates and standard escaping.
     - Stored or reflected XSS in the Weblate origin.
     - Security-critical.
   * - Repository, branch, path, and VCS inputs processed by Weblate must not
       become shell command execution. *(maintainer)*
     - VCS operations are invoked through Weblate-supported repository
       workflows and configured credentials.
     - Command injection or arbitrary code execution as the Weblate user.
     - Security-critical.
   * - Private project data, user data, credentials, tokens, SSH keys, and 2FA
       secrets are not disclosed to actors lacking permission. *(documented)* (source: :doc:`/admin/access`, :doc:`/security/privacy-compliance`)
     - Host, database, and storage permissions are intact.
     - Cross-project data leak, credential exposure, or unauthorized export.
     - Security-critical.
   * - Backup import rejects archives exceeding documented upload, member,
       aggregate size, and suspicious compression thresholds. *(documented)* (source: :doc:`/admin/config`, :ref:`projectbackup`)
     - Defaults or stricter limits remain configured.
     - Oversized or highly amplified archive is accepted past configured
       thresholds.
     - Security-critical for single-request DoS; otherwise availability bug.
   * - Documented user-configurable outbound URL surfaces reject internal or
       non-public targets by default. *(documented)* (source:
       :setting:`ASSET_RESTRICT_PRIVATE`,
       :setting:`PROJECT_WEB_RESTRICT_PRIVATE`,
       :setting:`WEBHOOK_RESTRICT_PRIVATE`, :setting:`VCS_RESTRICT_PRIVATE`)
     - Default private-target checks are enabled and no trusted allowlist
       exemption applies.
     - A user-configurable screenshot URL, remote HTML URL, project website or
       repository browser URL, outbound webhook URL, Fedora Messaging AMQP
       broker URL, or VCS URL reaches an internal or non-public target despite
       default controls.
     - Security-critical when it exposes internal services or metadata.
   * - Weblate records security-relevant account, permission, and project or
       component setting changes in audit logs or history. *(documented)*
       (source: :doc:`/security/privacy-compliance`, :doc:`/changes`)
     - Logging is configured and storage is available.
     - Missing audit trail for an action Weblate claims to log.
     - Security-critical when it blocks investigation of privileged changes;
       correctness-only for minor event gaps.
   * - Rate-limited API and web actions enforce configured rate limits.
       *(documented)* (source: :doc:`/api`, :doc:`/admin/config`)
     - Rate limiting is enabled and backed by a working datastore.
     - Requests exceeding configured thresholds continue to be processed.
     - Availability/security hardening depending on endpoint sensitivity.
   * - Weblate does not intentionally expose database, datastore, backup
       storage, or raw internal storage directly through the public web
       interface; exported VCS repositories are intentionally exposed by
       :ref:`git-exporter` when that optional module is enabled; authorized
       project backup downloads are intentionally exposed through documented
       project backup routes. *(documented)* (source: :doc:`/api`,
       :ref:`projectbackup`) *(maintainer)*
     - Deployment does not serve internal storage paths as static files except
       for documented export features.
     - Public request retrieves raw internal storage, configuration, or
       non-exported repository data.
     - Security-critical.

Resource thresholds in this model are the documented configuration defaults
where they exist, especially backup import limits and rate limits. For
repository size, project count, component count, and translation volume, Weblate
does not claim a fixed universal resource ceiling independent of deployment
capacity. *(maintainer)*

Security properties Weblate does not provide
--------------------------------------------

Weblate does not authenticate every webhook delivery cryptographically for all
supported forge integrations. Hook endpoints are compatibility-oriented and
deployment-hardened rather than uniformly forge-authenticated. Reports that
show only unauthenticated triggering within modeled effects are
``VALID-HARDENING`` rather than ``BY-DESIGN``. *(maintainer)*

Weblate does not make an unauthenticated webhook equivalent to a trusted forge
identity. Hook processing can trigger update workflows, but attribution and
authenticity are weaker than for an authenticated user or token. *(maintainer)*

Weblate is not a sandbox for malicious administrators, malicious local
operators, third-party add-ons, custom deployment code, VCS clients, or backup
tools. *(maintainer)*

Weblate does not guarantee that translation content is safe when copied into a
downstream product without that product's own escaping, validation, or review.
Translation checks and review workflows help manage localization quality and
risk; they are not a complete downstream application security boundary.
*(documented)* (source: :doc:`/security/localization-threat`, :doc:`/user/checks`)

False friends:

* Weblate permissions are application authorization, not a host sandbox. A user
  granted VCS or project management permissions can intentionally configure
  integrations within that role's power. *(maintainer)*
* Webhook project matching and event parsing are not proof that the sender is
  the legitimate forge when the integration does not authenticate the delivery.
  *(maintainer)*
* Translation checks detect common quality and format problems; they are not a
  guarantee that translated strings are safe for every downstream renderer.
  *(documented)* (source: :doc:`/user/checks`,
  :doc:`/security/localization-threat`)
* BorgBackup encryption protects backup archives according to Borg's design;
  Weblate does not add a separate cryptographic guarantee for Borg internals.
  *(documented)* (source: :doc:`/admin/backup`)
* Rate limits reduce abuse of configured endpoints; they are not a guarantee of
  availability under volumetric network attacks. *(maintainer)*

Well-known attack classes left partly or wholly to deployment or downstream
systems:

* Phishing and credential reuse are mitigated by authentication policy and 2FA,
  but Weblate cannot prevent users from disclosing credentials outside the
  service. *(maintainer)*
* Malicious translations can become XSS, format-string, command, or policy
  problems in downstream applications that render them unsafely. *(documented)* (source: :doc:`/security/localization-threat`)
* User-configurable outbound URL surfaces with documented private-target
  restrictions reject internal or non-public targets by default; privileged
  allowlists, proxies, and administrator-controlled configuration can
  intentionally expand reachability. *(maintainer)*
* Large repository histories, project scale, and background task volume require
  deployment sizing and operational limits beyond Weblate's single-input
  validation. *(maintainer)*

Downstream responsibilities
---------------------------

Operators must deploy Weblate behind production-grade HTTPS with correct proxy
headers, hostnames, request-size limits, and secure-cookie behavior.
*(documented)* (source: :doc:`/admin/install`, :setting:`ENABLE_HTTPS`,
:setting:`ALLOWED_HOSTS`)

Operators must assign teams, roles, project-scoped tokens, VCS credentials, and
project management permissions according to least privilege for their
organization. *(documented)* (source: :doc:`/admin/access`, :doc:`/api`)

Operators exposing :ref:`hooks` must enable them only where needed and provide
deployment controls such as reverse-proxy rate limits, body-size limits,
monitoring, and optional source restrictions. *(maintainer)*

Operators must treat private-target allowlists, proxies, and privileged
outbound integration settings as intentional expansion of Weblate's default
network reachability limits. *(maintainer)*

Operators must keep backup import limits, API rate limits, and web rate limits
at values that match instance capacity and exposure. *(documented)* (source: :doc:`/admin/config`)

Operators must protect the Weblate data directory, configuration, backup
credentials, generated keys, database, datastore, and local shell access as
trusted infrastructure. *(documented)* (source: :doc:`/admin/backup`,
:doc:`/admin/install`)

Downstream product teams must treat translated strings as untrusted content in
their own applications unless they have separately reviewed, escaped, and
validated them for the target renderer. *(documented)* (source: :doc:`/security/localization-threat`)

Known misuse patterns
---------------------

* Exposing webhook endpoints broadly, enabling project hooks, and relying on
  webhook payloads as authenticated forge identity. This is unsafe because some
  supported hooks are compatibility-oriented. Use deployment controls and prefer
  authenticated integrations where available. *(maintainer)*
* Granting project management, VCS, or access-management permissions to users
  who are trusted only as translators. This is unsafe because those permissions
  can affect repositories, credentials, or other users. Assign narrower roles.
  *(documented)* (source: :doc:`/admin/access`)
* Sending sensitive source strings or private customer content to machine
  translation providers without treating the provider as a data recipient. This
  is unsafe because Weblate must transmit content to the configured service, and
  the submitted content varies by provider and enabled feature. Configure
  providers according to the data policy for the project. *(maintainer)*
* Importing project backups from untrusted sources as an administrative
  convenience. This is unsafe because backups carry project metadata,
  translation content, and repository state. Keep import limits enabled and
  import only backups appropriate for the target instance. *(documented)* (source: :doc:`/admin/backup`)
* Treating Weblate translation checks as proof that downstream applications
  cannot be attacked through translated strings. This is unsafe because the
  downstream renderer defines the final execution context. Review and escape
  translations in the consuming application. *(documented)* (source: :doc:`/security/localization-threat`)

Known non-findings
------------------

* A report that a reachable webhook can be called without forge authentication
  and only triggers modeled update scheduling is not ``VALID`` by itself. It is
  routed to ``VALID-HARDENING`` unless it bypasses documented limits, leaks
  data, or causes effects beyond modeled scheduling. *(maintainer)*
* A report that a project manager can change repository settings, VCS
  credentials, or project configuration is not a vulnerability when the actor
  has the documented permission for that action. *(documented)* (source: :doc:`/admin/access`)
* A report that a project manager can configure Gerrit review push options is
  not a vulnerability by itself. Gerrit interprets these options as the
  configured Weblate Gerrit account and enforces Gerrit-side permissions.
  *(documented)* (source: :ref:`component-push_branch`)
* A report against third-party add-on behavior is not a Weblate core
  vulnerability unless the report shows Weblate's permission or installation
  boundaries are bypassed. *(maintainer)*
* A report that a malicious local operator can read configuration, run
  management commands, or alter files is out of model because local operators
  are trusted infrastructure. *(maintainer)*
* A report that a downstream application renders a dangerous translation is not
  a Weblate vulnerability unless Weblate itself violates a claimed property
  while storing, checking, reviewing, or displaying that translation.
  *(documented)* (source: :doc:`/security/localization-threat`)

Conditions that change this model
---------------------------------

Revise this model when Weblate adds a new public endpoint family, a new
authentication or token mode, a new default deployment mode, a new backup or
import format, a new VCS execution path, a new outbound integration class, a
new add-on execution capability, or a change to defaults for hooks, HTTPS,
rate limits, CSP, private-network access, or backup import limits. *(maintainer)*

Revise this model when an unsupported component becomes supported product
surface, when a documented security property is removed or narrowed, or when
maintainers accept a vulnerability report that cannot be routed to a triage
disposition below. *(maintainer)*

Triage dispositions
-------------------

.. list-table::
   :header-rows: 1

   * - Disposition
     - Meaning
     - Licensed by
   * - ``VALID``
     - Violates a property Weblate claims, through an in-scope actor and input.
     - `Security properties Weblate provides`_, `Input assumptions`_,
       `Adversary model`_
   * - ``VALID-HARDENING``
     - No claimed property is violated, but Weblate chooses to reduce a known
       misuse risk, such as compatibility webhook triggering that stays within
       modeled effects.
     - `Known misuse patterns`_, `Security properties Weblate does not provide`_
   * - ``OUT-OF-MODEL: trusted-input``
     - Requires attacker control of input this model marks trusted.
     - `Input assumptions`_
   * - ``OUT-OF-MODEL: adversary-not-in-scope``
     - Requires a capability this model excludes.
     - `Adversary model`_
   * - ``OUT-OF-MODEL: unsupported-component``
     - Lands in third-party add-ons, generated docs, tests, local
       customization, or another component marked out of scope.
     - `Out of scope`_
   * - ``OUT-OF-MODEL: non-default-build``
     - Manifests only after deployment choices that knowingly remove a claimed
       property.
     - `Build-time and configuration variants`_
   * - ``BY-DESIGN: property-disclaimed``
     - Concerns a property Weblate explicitly does not provide.
     - `Security properties Weblate does not provide`_
   * - ``KNOWN-NON-FINDING``
     - Matches a documented recurring false positive.
     - `Known non-findings`_
   * - ``MODEL-GAP``
     - Cannot be cleanly routed to any disposition above.
     - `Conditions that change this model`_
