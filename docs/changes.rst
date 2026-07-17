Weblate 2026.8
--------------

*Not yet released.*

.. rubric:: New features

* Added API endpoints for listing, adding, accepting, rejecting, and voting on translation suggestions.
* :doc:`Translation reports </devel/reporting>` are now generated in the background, stored for later download, available at workspace scope, and include translator work analysis.
* Added :guilabel:`Use keywords exclusively` option to :ref:`addon-weblate.gettext.xgettext`, allowing projects to disable xgettext default keywords and rely only on a custom keyword.

.. rubric:: Improvements

* Added grouped project and workspace :guilabel:`Diagnostics` views with state, severity, category, and actionable-by-user filters.
* Component diagnostics now record dismissal ownership, reopen after relevant changes, and notify only project maintainers who can act on warnings and errors.
* :ref:`Add-on activity logs <addon-activity-logging>` now distinguish pending, successful, failed, and skipped executions and explain why an add-on was skipped.
* Expanded :ref:`change-actions` documentation with detailed event semantics and improved OpenAPI schema accuracy.
* Improved matrix view loading performance when displaying multiple languages.
* Translation memory management pages now load origin summaries with a single database aggregation.
* Dashboard component list tabs now load without processing unrelated component lists.
* Static assets now use content-hashed filenames, and CAPTCHA JavaScript is loaded only when needed.
* :ref:`Empty workspaces <workspace-removal>` not associated with billing can now be removed from the workspace :guilabel:`Operations` menu.
* :ref:`mt-aws` machine translation now supports configuring formality, brevity, and profanity masking.
* Improved :ref:`screenshots` OCR reliability and error reporting when downloading recognition data.
* Celery workers now prefetch fewer tasks by default to reduce memory usage and improve task distribution.
* Improved the recommended :ref:`running-granian` configuration and Docker container worker resilience for Weblate's WSGI workload.
* Deployment checks now detect corrupted PostgreSQL relation statistics.
* :ref:`Community diagnostics <alerts>` now show source-string screenshot coverage, recommend key translation-instruction topics, and distinguish inbound from outbound repository automation.

.. rubric:: Bug fixes

* Self-service REST API e-mail changes are now restricted to verified addresses.
* REST API authorization now consistently protects internal accounts, restricted components, add-on configuration, component sharing, repository links, and review states.
* Suggestion submission and rejection now reject excessively long suggestion text and rejection reasons.
* Restricted components are now available on Hosted Weblate when the billing plan permits private projects.
* Machine translation and translation memory AJAX lookups no longer disclose whether inaccessible unit IDs exist.
* :ref:`RSS feeds <rss>` no longer disclose change history from inaccessible projects or restricted components.

.. rubric:: Compatibility

* django-compressor is no longer used, and the ``COMPRESS_*`` settings have been removed.
* Legal document styling is now provided through an overridable template instead of Weblate's global stylesheet. See :ref:`legal-customization`.
* The project and component ``credits`` REST API endpoints and their ``credits_url`` response fields have been replaced by scoped ``reports`` endpoints and ``reports_url``. Credits report generation is now asynchronous; clients need to submit a ``credits`` report, follow the returned task URL, and fetch the completed report. See :http:post:`/api/reports/`.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

* There are changes in :file:`settings_example.py`, most notably the new ``STORAGES`` configuration and removal of the ``COMPRESS_*`` settings; please adjust your settings accordingly.
* Running :program:`weblate compress` is no longer necessary; :program:`weblate collectstatic --noinput` now prepares versioned static assets without clearing the static storage.

.. rubric:: Contributors

.. include:: /changes/contributors/2026.8.rst

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/167?closed=1>`__.

Weblate 2026.7.1
----------------

*Released on July 10th 2026.*

.. rubric:: New features

* Added :setting:`INTERNAL_BOT_EMAIL_TEMPLATE` to customize internal bot e-mail addresses.

.. rubric:: Improvements

* Restricted components now show a status icon in component listings.
* Permission checks now reuse materialized team membership data from lightweight relation lookups.
* Documented that intermediate language files are hidden from language listings and can make target strings read-only.
* Component diagnostics now warn when regular :ref:`gettext` PO files are configured as monolingual PO files.
* Translation memory fuzzy lookups are now faster on large translation memories.
* Permission denied messages when saving translations, editing glossaries, or voting on suggestions now show more specific reasons.
* Comment notifications for strings you translated now also include strings you previously commented on or suggested translations for.
* Comments and suggestions now auto-watch the project when :guilabel:`Automatically watch projects on contribution` is enabled.
* Clarified Hosted Weblate repository access guidance in :doc:`/admin/code-hosting`.
* :ref:`search-strings` now includes filters for comments by the current user and separate source string comment lookups.
* Code-hosting account pages now consistently use :guilabel:`Code-hosting connections` and provider-neutral connected account wording.
* :ref:`discover-weblate` registration can now be started from the management interface without manually copying the activation token.
* :ref:`discover-weblate` can now be managed from a dedicated management panel, registration starts with discovery enabled, and protected projects are included in the listing.
* Updated the :ref:`mt-openai`, :ref:`mt-mistral`, and :ref:`mt-anthropic` model lists for currently supported models.

.. rubric:: Bug fixes

* Filtered translation and zen navigation now reuse a stable session result list, keeping positions and counts stable after translated strings leave the filter.
* Component priority icons are no longer shown on translation listings.
* :ref:`check-punctuation-spacing` no longer flags Markdown image markers as French punctuation and now shows which punctuation marks triggered the check.
* :ref:`addon-weblate.fedora_messaging.publish` received several reliability fixes.
* The :guilabel:`Things to check` panel no longer uses error highlighting for suggestions and other non-error translation states.
* Translation workflow customization now makes it clearer when per-language workflow settings are disabled until customization is enabled.
* Anonymous user permission caches are now isolated between requests.
* GitHub App setup now explains that a workspace is required instead of showing a permission error when no workspace exists.
* LLM automatic suggestion settings no longer show ``null`` for empty language-specific instructions.
* File format feature tables now better match actual format support, including descriptions, context, plural metadata, obsolete string removal, specialized file extensions, and merged variants.
* Accepting a project invitation now automatically adds the project to the user's watched projects.
* Dismissing a failing check no longer shows a JSON parsing error in the translation editor.
* Screenshot searches without an explicit field now match screenshot names only, and the search box links to the full screenshot search documentation.
* Anonymous and internal bot accounts can no longer be edited through generic user management.
* LLM machine translation suggestions now recover from more malformed structured JSON replies.
* Azure AI Translator settings now reject malformed region names before validating service connectivity.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

* Weblate now requires the PostgreSQL ``btree_gist`` extension for translation memory lookups. The migration installs it automatically when the database user has sufficient privileges. Installations using a non-superuser database user should pre-create it before upgrading; see :ref:`dbsetup-postgres`.

.. rubric:: Contributors

.. include:: /changes/contributors/2026.7.1.rst

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/170?closed=1>`__.

Weblate 2026.7
--------------

*Released on July 1st 2026.*

.. rubric:: New features

* Added :ref:`check-safe-mdx`, :ref:`check-source-max-length`, and :ref:`check-accelerator` quality checks for :ref:`mdx` JSX expressions, source length limits, and accelerator key consistency.
* Added :ref:`mt-mistral` machinery integration for Mistral LLM automatic suggestions.
* Added :ref:`code-hosting-github-app-register` for connecting GitHub repositories through a Weblate GitHub App.
* :ref:`projectbackup` backups can now be created and downloaded via the :ref:`api`.
* Added file format parameters for translating individual YAML front matter values in :ref:`markdown` and :ref:`mdx` files and escaping formula-like values in :ref:`csv` files.
* Added an option to capitalize the text in status badge widgets.
* Added :ref:`workspace translation memory <memory-scopes>` with asynchronous scope backfill for existing translation memory entries.
* Added :wladmin:`analyze_translator_work` to estimate realistic daily translator throughput from change history.

.. rubric:: Improvements

* RTL editing and translation display now handle bidirectional text better, including Unicode isolate controls in the :ref:`visual-keyboard`.
* Management interface access control is now more fine-grained with dedicated site-wide permissions.
* Default commit and merge request message templates now use Conventional Commits, settings forms can restore installation defaults, and pull request messages use a compact language progress matrix.
* Documented :ref:`legal` customizations and added options to hide legal pages or disable document numbering.
* Expanded :doc:`security documentation </security/index>` for data residency, EU cloud sovereignty, release artifacts, supported versions, release verification, SBOMs, dependency handling, vulnerability reporting, hosted-service incident response, and self-hosted operator responsibilities.
* :ref:`addon-weblate.gettext.linguas` better detects ``LINGUAS`` file presence.
* :ref:`addon-weblate.gettext.xgettext` can now leave the xgettext language blank to let xgettext guess it from source file extensions.
* :ref:`addon-weblate.gettext.xgettext`, :ref:`addon-weblate.gettext.meson`, :ref:`addon-weblate.gettext.django`, and :ref:`addon-weblate.gettext.sphinx` can now keep source locations in generated POT files even when translated PO files omit locations.
* Add-ons installed at higher scopes are now shown on lower-scope add-on pages, and broad-scope add-ons can list affected components with compatibility details.
* :envvar:`WEBLATE_ALLOWED_ASSET_SIZE` is now available in Docker container.
* LLM automatic suggestions now use translated examples, language-specific instructions, richer glossary context, and structured placeholder context for more reliable output.
* Meta descriptions now better match single-project and self-hosted installations.
* Zen mode, filtered searches, nearby strings, translation form submissions, and add-on management pages now load more efficiently on large sites.
* Added :ref:`distribution-packaging` guidance for distribution maintainers.
* Large component imports now avoid duplicate translation-memory processing.
* :ref:`gettext` files can now be configured to remove obsolete strings on save, including during repository maintenance.
* :ref:`Bulk accepting suggestions <suggestions>` now confirms the number of affected suggestions, can approve them for reviewers, and processes the acceptance in the background.
* Committing large numbers of pending translations now queues browser requests in the background and avoids duplicate repository commit tasks.
* Change-event notification add-ons can now use presets for translation content events, all events, or selected individual events.
* :ref:`addon-weblate.fedora_messaging.publish` now validates secure broker connections and exposes delivery timing and topic prefix settings.
* Component diagnostics now sort entries by severity, color-code severity badges, and show the error count on the :guilabel:`Diagnostics` tab.
* :ref:`manage-performance` now shows PostgreSQL database disk usage next to server disk usage and warns when the database usage cannot be collected.
* :ref:`manage-performance` now shows PostgreSQL database disk usage next to server disk usage and warns when the database usage cannot be collected or there is not enough free space in the backup destination to store a database dump.
* The :ref:`search-replace` preview now keeps the search parameters editable so the query can be refined before applying replacements.

.. rubric:: Bug fixes

* :ref:`check-regex` and :ref:`check-placeholders` now enforce regular expression timeouts when evaluating source-string flags (:cve:`2026-62326`, :ghsa:`r52j-4vjp-q949`).
* Restricted component changes are no longer exposed through nested project, component, or translation API change endpoints (:cve:`2026-62249`, :ghsa:`92m8-wv36-prmx`).
* ZIP downloads, including :ref:`appstore` translation bundles, no longer follow child symbolic links outside the downloaded tree (:cve:`2026-61792`, :ghsa:`xwj4-fp82-r2rj`).
* Teams enforcing two-factor authentication now also withhold site-wide permissions from human members without 2FA configured (:cve:`2026-61790`, :ghsa:`x86c-ff69-cr2m`).
* Globally scoped HTML and AJAX object lookups no longer disclose object existence in private projects (:cve:`2026-55227`, :ghsa:`2p9g-x3cv-5hh4`).
* Team API access checks now prevent project managers from reading private-project team data or expanding scoped team assignments outside their allowed projects (:cve:`2026-55228`, :ghsa:`2q2q-jr9g-v9rf`).
* Malformed ``replacements`` flags no longer abort source length checks.
* Empty component lists are no longer exposed to users without component list management permission.
* Glossary handling no longer duplicates TBX terms or shows source-language terms in both translation columns.
* Duplicate string alerts now offer a cleanup action to remove repeated strings from translation files.
* :ref:`code-hosting-gerrit` review pushes can again include Gerrit push options in the target branch.
* Webhook target fallback matching is now stricter and reported in component diagnostics.
* Creating components linked with ``weblate://`` no longer waits on the shared repository lock during the request.
* Project and workspace translation license defaults now follow component and project licenses more closely.
* Component and category API ``PATCH`` requests no longer remove the category when the field is omitted.
* Document and translation-memory uploads now enforce :setting:`TRANSLATION_UPLOAD_MAX_SIZE`, and API document uploads validate file extensions.
* :ref:`check-rst-syntax` now detects inline roles wrapped in stray backticks.
* :ref:`check-safe-html` now efficiently detects changed placeholder-only HTML attribute values in translations.
* :ref:`check-max-size` no longer wraps text configured to fit on one line, checks source strings, and refreshes rendered previews after source edits.
* Bitmap widgets and :ref:`check-max-size` previews now use Matplotlib and no longer require Pango, Cairo, librsvg, or GObject Introspection.
* Repository reset and update history now keeps attribution, records remote update failures, and includes follow-up translation-file reconciliation.
* Updating repository URLs now validates compatible Git history without requiring an immediate successful merge.
* :ref:`auto-translation` no longer validates hidden component fields when using machine translation.
* :guilabel:`Strings marked for edit` links now include all strings needing editing, checking, or rewriting.
* Anonymous permission checks no longer fail when loading teams scoped to projects or workspaces.
* API project creation can again use the user's only eligible workspace when no explicit workspace is supplied.
* Git auto-maintenance is now disabled for Weblate-managed repositories to avoid concurrent detached maintenance jobs.
* Interrupted Git repository operations are now either recovered and recorded or surfaced as a repository alert.
* Watched translations on the dashboard now include category path segments.
* Unsupported upload levels now show an upload placeholder pointing to individual translations.
* Component API responses no longer expose repository export, push branch, or repository browser links to users without repository access.

.. rubric:: Compatibility

* :ref:`mt-deepl` now handles DeepL API versions internally, uses v3 for glossary management and language discovery, and no longer supports DeepL API v1.
* :ref:`addon-weblate.fedora_messaging.publish` topics now include category path segments, and broker settings are stored as an AMQP URL with existing host and SSL settings migrated automatically.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

* There are changes in :file:`settings_example.py`, most notably in ``SOCIAL_AUTH_PIPELINE`` and ``SOCIAL_AUTH_DISCONNECT_PIPELINE``; please adjust your settings accordingly.
* Existing translation-memory entries are moved to scoped storage by a periodic Celery background task. Keep Celery running after the upgrade; translation-memory suggestions can be incomplete until the backfill finishes.

.. rubric:: Contributors

.. include:: /changes/contributors/2026.7.rst

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/166?closed=1>`__.

Weblate 2026.6.1
----------------

*Released on June 1st 2026.*

.. rubric:: Bug fixes

* Language-wide :doc:`/admin/announcements` no longer break language overview pages.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

.. rubric:: Contributors

.. include:: /changes/contributors/2026.6.1.rst

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/169?closed=1>`__.

Weblate 2026.6
--------------

*Released on June 1st 2026.*

.. rubric:: New features

* :doc:`/admin/announcements` can now also be managed via the :ref:`api` for specific project languages.
* Team memberships can now be limited to selected languages for per-user translation permissions.
* Added :ref:`cost estimates <cost-estimate>` to translation reports.
* Added optional :ref:`OpenTelemetry tracing <collecting-errors>` for backend requests and tasks, and :ref:`Google Cloud Error Reporting <collecting-errors>` for handled server errors.
* Added :doc:`/admin/workspaces` to group related projects, with workspace project listings, workspace-scoped teams and project creation permissions, inherited workspace, project, and category defaults for selected component settings, and billing details when available.

.. rubric:: Improvements

* Docker containers can now configure :envvar:`WEBLATE_SAML_SECURITY_CONFIG` to customize SAML security settings, and adjust :setting:`WEBLATE_FORMATS` using :envvar:`WEBLATE_ADD_FORMATS` and :envvar:`WEBLATE_REMOVE_FORMATS`.
* Improved performance of the :ref:`check-inconsistent` check on large projects.
* Translation flag fields now use a tag-based editor with autocompletion and grouped suggestions for all known flags.
* :ref:`Contributor stats <stats>` now de-duplicate repeated work on the same string by default, with an option to count all changes.
* :doc:`/admin/code-hosting` now documents HTTPS access-token URLs and dedicated-user SSH URLs for accessing repositories, and :doc:`/admin/continuous` now explains why squash merging Weblate conflict-resolution pull requests can require a repository reset.
* :ref:`alerts` now include dismissible component diagnostics for community localization.
* :ref:`screenshots` now support bulk assignment from search or image text recognition results, make finding strings in uploaded images easier to discover, show source string coverage counts, and include advanced listing search.
* :ref:`sbom` release artifacts now include CISA 2025 document-level metadata.

.. rubric:: Bug fixes

* Outbound URL validation now rejects additional non-public targets (:cve:`2026-50127`, :ghsa:`vmfc-9982-2m45`).
* Project-language :doc:`/admin/announcements` no longer appear across the whole project.
* Hardened :http:post:`/api/screenshots/` access checks against private project enumeration.
* Registration-attempt account activity e-mails now link to password reset to help users finish account setup.
* :ref:`invite-user` links now work for signed-in users whose account owns the invited e-mail address.
* Searching for strings with content changes without a recorded author now supports ``changed_by:""``, and combined change filters now apply to the same change event.
* Gitea and Forgejo pull requests no longer reconfigure existing fork remotes to point to the source repository.
* Project and category language translation sessions now keep strings grouped by component priority and show component switch warnings reliably.
* Engage page task links now stay centered and show the target translation language.
* Gettext POT update add-ons now rescan translations after committing updated POT and PO files.
* Git repositories now update branches correctly when the remote also has a tag with the same name.
* Conflicting repository setup alerts now allow same-branch direct pushes.
* Obsolete cleanup schedules are now removed from Celery beat during upgrade.
* Translation pages for workspace projects no longer crash when workspace fields are deferred.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

* There is a change in :setting:`django:INSTALLED_APPS`; ``weblate.workspaces`` should be added.
* The database migrations might take longer on larger instances.

.. rubric:: Contributors

.. include:: /changes/contributors/2026.6.rst

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/165?closed=1>`__.

Weblate 2026.5
--------------

*Released on May 15th 2026.*

.. rubric:: New features

* Added :ref:`mdx` support for translating Markdown text while preserving JSX syntax, with :ref:`file_format_params` shared with :ref:`markdown` for line wrapping, code blocks, front matter, and placeholder handling.
* Added extended :ref:`LLM translation context <llm-translation-context>` for automatic suggestions, covering string context, explanations, secondary-language translations, plurals, failing checks, and placeholders.
* Added a digest-only translation activity summary notification, see :ref:`notifications`.
* :ref:`CSV <csv>` and :ref:`XLSX <xlsx>` downloads in :ref:`download` now export plural strings as separate plural-form rows that can be imported back.
* Added Gettext PO and POT :ref:`file_format_params` to control whether Weblate updates the ``Language-Team``, ``Last-Translator``, ``X-Generator``, and ``Report-Msgid-Bugs-To`` headers.
* Added a :ref:`backup-management-command` to run configured backup services synchronously.
* The translation memory lookup API can now skip fuzzy matching with the ``exact`` query parameter.
* Added :ref:`addon-weblate.cdn.files` to publish translation files to the configured CDN.

.. rubric:: Improvements

* Using DOS line endings can now be configured using the ``dos_eol`` :ref:`file_format_params`.
* :ref:`mt-openai` and :ref:`mt-alibaba` no longer require their vendor Python SDKs.
* Audited project and component setting changes are now recorded in history.
* Gerrit review pushes now use :ref:`component-push_branch` as the target branch.
* Weblate now checks whether :setting:`CACHE_DIR` allows executing generated helper files.
* The :ref:`sbom` is now generated during release and published as a versioned release asset instead of being stored in the source repository.
* The translating page now separates screenshots from string information, collapses rarely used string details, and groups glossary and screenshot actions more consistently.
* Project access management now paginates users and better explains site-wide automatic team assignments.
* Added provider-oriented code-hosting documentation and Gettext-style :ref:`plural-formula` guidance.
* The Python wheel no longer ships source translation catalogs, test files, or deployment example files, reducing the installed package size.
* The engage page now highlights actionable translation task buckets for newcomers.
* :ref:`RSS feeds <rss>` can now use the same filters as the changes browsing page.
* :ref:`addon-weblate.gettext.django` now supports gettext PO files used as templates when they are excluded by the language filter.
* Reworked :doc:`/security/threat-model` into a contract-style document.

.. rubric:: Bug fixes

* Hardened search previews and :ref:`machine-translation` suggestion origins against XSS, and stopped exposing database error details in upload failures (:cve:`2026-45106` / :ghsa:`6wxc-8mgq-w26m`).
* Screenshot URL uploads, remote HTML extraction in :ref:`addon-weblate.cdn.cdnjs`, and URL health-check redirects now reject internal or non-public targets by default.
* Gerrit review pushes now reject target branches containing push options, track the target branch before invoking ``git-review``, and suggest short branch names when full refs are supplied.
* Category :doc:`/admin/announcements` no longer appear across the whole project, and translation announcement deletion now honors language-scoped permissions.
* Merge request pushes now refresh stale fork remotes after changing repository hosting.
* Plural counts parsed from translation file headers are now bounded, and plural formulas are rejected when they can evaluate outside the configured plural form range.
* :ref:`project-api` expiring today now remain valid until the end of the day.
* Malformed ALTCHA CAPTCHA submissions and repository URLs in webhook payloads no longer cause server errors.
* :ref:`check-placeholders` now merges overlapping non-nested spans from multiple flags.
* :ref:`backup` logs no longer include OpenSSH post-quantum key exchange warnings from remote Borg connections.
* Category repository paths are now handled more safely during cleanup and moves.
* Locked component pages now show an unsubscribe action after subscribing to unlock notifications.
* :ref:`projectbackup` imports now restore in the background to avoid web worker memory limits.

.. rubric:: Compatibility

* The ``dos-eol`` flag is no longer supported. Use the ``dos_eol`` :ref:`file_format_params` instead.
* The registration CAPTCHA now uses the ALTCHA widget v3 protocol with Argon2id proof-of-work.
* The ``set_language_team`` project attribute has been replaced with the ``po_set_language_team`` file format parameter at the component level; see :ref:`file_format_params`.
* Weblate now uses calendar versioning for releases, see :ref:`release-cycle`.
* Weblate now uses stricter dependency version constraints to better control runtime environment.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

* The ``ALTCHA_MAX_NUMBER`` setting has been replaced by :setting:`ALTCHA_COST`, :setting:`ALTCHA_MEMORY_COST`, and :setting:`ALTCHA_PARALLELISM`; please adjust your settings accordingly.
* The upgrading policy was changed, and upgrades are only supported from the current or previous calendar year.
* The ``COMMENT_CLEANUP_DAYS`` and ``SUGGESTION_CLEANUP_DAYS`` settings are migrated once to site-wide :ref:`addon-weblate.removal.comments` and :ref:`addon-weblate.removal.suggestions` add-ons; configure those add-ons instead.

.. rubric:: Contributors

.. include:: /changes/contributors/2026.5.rst

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/162?closed=1>`__.
