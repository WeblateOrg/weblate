Weblate 2026.5
--------------

*Not yet released.*

.. rubric:: New features

* Added :ref:`file_format_params` for :ref:`markdown`, including ``line_max_length``, ``md_extract_code_blocks``, ``md_extract_frontmatter``, and ``md_no_placeholders``.
* Added :ref:`mdx` support for translating Markdown text while preserving JSX syntax.
* :ref:`CSV <csv>` and :ref:`XLSX <xlsx>` downloads in :ref:`download` now export plural strings as separate plural-form rows that can be imported back.
* :ref:`file_format_params` now include ``po_set_language_team``, ``po_set_last_translator``, ``po_set_x_generator``, and ``po_report_msgid_bugs_to`` to control whether Weblate updates the ``Language-Team``, ``Last-Translator``, ``X-Generator``, and ``Report-Msgid-Bugs-To`` headers in Gettext PO and POT files.
* Added a :ref:`backup-management-command` to run configured backup services synchronously.

.. rubric:: Improvements

* Using DOS line endings can now be configured using the ``dos_eol`` :ref:`file_format_params`.
* Improved :ref:`LLM translation context <llm-translation-context>` for automatic suggestions.
* :ref:`mt-openai` no longer requires the OpenAI Python SDK.
* :ref:`mt-alibaba` no longer requires the Aliyun Python SDK.
* Audited project and component setting changes are now recorded in history.
* :ref:`vcs-gerrit` now uses :ref:`component-push_branch` as the target branch for review pushes.
* Weblate now checks whether :setting:`CACHE_DIR` allows executing generated helper files.
* The :ref:`sbom` is now generated during release and published as a versioned release asset instead of being stored in the source repository.
* :ref:`code-hosting-gerrit` now uses :ref:`component-push_branch` as the target branch for review pushes.
* Added :doc:`/admin/code-hosting` with provider-oriented setup guidance for code hosting integrations.
* The translating page now separates screenshots from string information, collapses rarely used string details, and groups glossary and screenshot actions more consistently.
* Project access management now paginates users and better explains site-wide automatic team assignments.
* Documented Gettext-style :ref:`plural-formula` syntax and linked to the upstream GNU gettext references.
* The Python wheel no longer ships source translation catalogs, test files, or deployment example files, reducing the installed package size.
* The engage page now highlights actionable translation task buckets for newcomers.
* :ref:`RSS feeds <rss>` can now use the same filters as the changes browsing page.

.. rubric:: Bug fixes

* Hardened search previews and :ref:`machine-translation` suggestion origins against XSS.
* Screenshot URL uploads and remote HTML extraction in :ref:`addon-weblate.cdn.cdnjs` now reject internal or non-public asset URLs by default.
* Database error details are no longer exposed in upload failure messages.
* :ref:`vcs-gerrit` now rejects review target branches containing Gerrit push options.
* Category :doc:`/admin/announcements` no longer appear across the whole project.
* Translation announcement deletion now honors language-scoped permissions.
* Merge request pushes now refresh stale fork remotes after changing repository hosting.
* Plural counts parsed from translation file headers are now bounded.
* Plural formulas are now rejected when they can evaluate outside the configured plural form range.
* :ref:`project-api` expiring today now remain valid until the end of the day.
* :ref:`vcs-gerrit` now tracks the target branch on its Gerrit remote before invoking ``git-review``.
* :ref:`vcs-gerrit` branch validation now suggests short branch names when full refs are supplied.
* URL health checks now validate redirect targets using the configured private-target restrictions.
* :ref:`code-hosting-gerrit` now tracks the target branch on its Gerrit remote before invoking ``git-review``.
* :ref:`code-hosting-gerrit` branch validation now suggests short branch names when full refs are supplied.
* Malformed ALTCHA CAPTCHA submissions no longer cause server errors.
* Malformed repository URLs in webhook payloads no longer trigger server errors during fallback matching.
* :ref:`backup` logs no longer include OpenSSH post-quantum key exchange warnings from remote Borg connections.
* Locked component pages now show an unsubscribe action after subscribing to unlock notifications.

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
