Weblate 2026.7
--------------

*Not yet released.*

.. rubric:: New features

* Added :ref:`check-safe-mdx` check to ensure that the target string contains the same JSX expressions as the source string for :ref:`mdx` files.

.. rubric:: Improvements

* Management interface access control is now more fine-grained with dedicated site-wide permissions.
* Default commit and merge request message templates now use Conventional Commits, and settings forms can restore installation defaults for individual message templates.
* Documented :ref:`legal` customizations and added options to hide legal pages or disable document numbering.
* :ref:`addon-weblate.gettext.linguas` better detects ``LINGUAS`` file presence.
* :ref:`addon-weblate.gettext.xgettext` can now leave the xgettext language blank to let xgettext guess it from source file extensions.
* :envvar:`WEBLATE_ALLOWED_ASSET_SIZE` is now available in Docker container.
* LLM automatic suggestions now use translated examples, language-specific instructions, and richer glossary context for more reliable output.

.. rubric:: Bug fixes

* TBX glossary files no longer duplicate terms when repeated pending add operations are saved.
* :ref:`code-hosting-gerrit` review pushes can again include Gerrit push options in the target branch.
* Webhook target fallback matching is now stricter and reported in component diagnostics.
* Creating components linked with ``weblate://`` no longer waits on the shared repository lock during the request.
* Project and workspace translation license defaults now follow component and project licenses more closely.

.. rubric:: Compatibility

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

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

* Outbound URL validation now rejects additional non-public targets (:ghsa:`vmfc-9982-2m45`).
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
* Added provider-oriented code hosting documentation and Gettext-style :ref:`plural-formula` guidance.
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
