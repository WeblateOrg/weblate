Weblate 5.11.4
--------------

*Released on May 7th 2025.*

.. rubric:: Improvements

* :ref:`addon-weblate.webhook.webhook` logs requests and responses.

.. rubric:: Bug fixes

* :ref:`addon-weblate.webhook.webhook` was not triggered in some situations.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

.. rubric:: Contributors

.. include:: changes/contributors/5.11.4.rst

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/146?closed=1>`__.

Weblate 5.11.3
--------------

*Released on May 3rd 2025.*

.. rubric:: Bug fixes

* Fixed release publishing.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

.. rubric:: Contributors

.. include:: changes/contributors/5.11.3.rst

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/145?closed=1>`__.

Weblate 5.11.2
--------------

*Released on May 3rd 2025.*

.. rubric:: Improvements

* Glossary performance in zen mode and automatic suggestions.
* Extended supported formats for :ref:`addon-weblate.json.customize`.

.. rubric:: Bug fixes

* XML export no longer crashes on locations with special characters.
* Improved error handling on ZIP upload.
* Django 5.2 compatibility.
* Avoid repeated glossary synchronizations.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

.. rubric:: Contributors

.. include:: changes/contributors/5.11.2.rst

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/144?closed=1>`__.

Weblate 5.11.1
--------------

*Released on April 25th 2025.*

.. rubric:: Improvements

* :ref:`projectbackup` now include teams and categories.
* Docker health check is now supported in non-web service containers.

.. rubric:: Bug fixes

* :ref:`vcs-gitlab` integration now detects merge‑request conflicts more robustly.
* :ref:`addon-weblate.webhook.webhook` is now enabled in Docker.
* Removing pending glossary terms.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

.. rubric:: Contributors

.. include:: changes/contributors/5.11.1.rst

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/142?closed=1>`__.

Weblate 5.11
------------

*Released on April 15th 2025.*

.. rubric:: New features

* Added :http:get:`/api/units/(int:id)/translations/` to retrieve a list of all target translation units for the given source translation unit.
* Added :http:delete:`/api/groups/(int:id)/roles/(int:role_id)` to delete a role from a group.
* :ref:`addon-weblate.webhook.webhook` is now available as an add-on.
* :ref:`check-automattic-components-format` check to validate placeholders in Automattic components.
* Inherited flags can now be discarded, see :ref:`custom-checks`.
* :ref:`secondary-languages` can now be specified in :ref:`project` and :ref:`component`.
* :ref:`mt-sources` can now be customized.

.. rubric:: Improvements

* Weblate now uses OpenAPI Specification 3.1.1 to generate the schema for :ref:`api`.
* :ref:`credits` and :ref:`stats` include translator's join date. Additionally, both reports can be sorted either by the join date or the number of strings translated.
* Widgets show more precise stats.
* :ref:`upload` is now tracked in history with details.
* :ref:`check-c-sharp-format` now supports ``csharp-format`` flag for compatibility with GNU gettext.
* Changes in string flags are now tracked in history.
* :doc:`/admin/machine` documentation extended.
* :ref:`addon-weblate.discovery.discovery` better handles hundreds of matches.
* Dismissing :ref:`checks` automatically updates propagated strings.
* :ref:`project-check_flags` can now also be configured on the project level.
* Improved rendering of :ref:`additional-flags` and :ref:`additional-explanation` changes in history.
* :ref:`mt-cyrtranslit` now automatically transliterates from a matching translation instead of the source strings.
* Errors from creating a duplicate glossary and failure to delete a glossary are now handled gracefully.

.. rubric:: Bug fixes

* **Security:** Cloning a component could leak component configuration into the URL (CVE-2025-32021).
* Fixed captcha verification when some time zone was configured.
* Improved translation propagation performance.
* Leading and trailing whitespace are now correctly stripped in glossary strings that also contain a :ref:`check-prohibited-initial-character`.
* Fixed background parsing of newly added translation files.

.. rubric:: Compatibility

* Registration now disallows disposable e-mail domains.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

* The database migration updates indexes and this might take considerable time.

.. rubric:: Contributors

.. include:: changes/contributors/5.11.rst

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/136?closed=1>`__.

Weblate 5.10.4
--------------

*Released on March 19th 2025.*

.. rubric:: Bug fixes

* Fixed dismissing of checks.
* Reduced overhead of rendering other strings while translating.
* Improved performance of some :ref:`api` endpoints.
* Fixed :ref:`language-parsing-codes` in some corner cases.
* :ref:`search-strings` now properly finds exact match on the component.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

.. rubric:: Contributors

.. include:: changes/contributors/5.10.4.rst

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/140?closed=1>`__.

Weblate 5.10.3
--------------

*Released on March 13th 2025.*

.. rubric:: Improvements

* Captcha is not shown for registrations via :ref:`invite-user`.

.. rubric:: Bug fixes

* Improved performance of API download endpoints.
* Optimized fetching other translations while translating.
* Reduced notifications overhead.
* Improved handling of components using :ref:`internal-urls`.
* Fixed authenticating with some Git servers.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

.. rubric:: Contributors

.. include:: changes/contributors/5.10.3.rst

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/139?closed=1>`__.

Weblate 5.10.2
--------------

*Released on February 28th 2025.*

.. rubric:: Improvements

* Improved :ref:`translation-memory` matching.
* Visual diff now better highlights whitespace additions.
* Improved performance on large projects.

.. rubric:: Bug fixes

* Consistency of :ref:`search-boolean` in :doc:`/user/search`.
* Fixed some :ref:`addons` trigger upon installation.
* Fixed restoring of Git repositories from :ref:`projectbackup`.

.. rubric:: Compatibility

* Weblate has switched to a different library for zxcvbn integration, as the old one is no longer maintained, see :ref:`password-authentication`.
* Weblate uses proactive authentication with Git 2.46.0 and newer when HTTP credentials are supplied.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

* There are several changes in :file:`settings_example.py`, most notable are changed settings ``AUTH_PASSWORD_VALIDATORS`` and ``INSTALLED_APPS``; please adjust your settings accordingly.

.. rubric:: Contributors

.. include:: changes/contributors/5.10.2.rst

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/138?closed=1>`__.

Weblate 5.10.1
--------------

*Released on February 21st 2025.*

.. rubric:: Improvements

* :ref:`check-multiple-failures` better shows failing checks including links to the strings.
* Detailed overview of locked components on project repository management.
* :ref:`search-strings` supports searching by source string state.

.. rubric:: Bug fixes

* :ref:`download` performs faster on project and language scopes.
* :ref:`zen-mode` does not display the source string twice when editing it.
* Fixed :ref:`glossary` terms highlighting.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

.. rubric:: Contributors

.. include:: changes/contributors/5.10.1.rst

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/137?closed=1>`__.

Weblate 5.10
------------

*Released on February 14th 2025.*

.. rubric:: New features

* :ref:`check-rst-references` check to validate reStructuredText references.
* :ref:`check-rst-syntax` check to validate reStructuredText syntax.
* API can now produce CSV output.
* New management command :wladmin:`import_projectbackup` to import :ref:`projectbackup`.

.. rubric:: Improvements

* Improved error handling in :ref:`machine-translation-setup`.
* :envvar:`WEBLATE_REGISTRATION_CAPTCHA` is now available in Docker container.
* :guilabel:`Synchronize` on shared repository now operates on all its components.
* :ref:`check-punctuation-spacing` ignores markup such as Markdown or reStructuredText.
* :ref:`autofix-punctuation-spacing` does not alter reStructuredText markup.
* Improved validation errors in :doc:`/api`, see :ref:`api-errors`.
* Any language changed into an alias in `Weblate language data <https://github.com/WeblateOrg/language-data/>`__ is now reflected in all existing installations.
* Blank alias languages (not linked to any translation, profile, component, ...) are now automatically removed.
* :ref:`check-duplicate` better works with markup such as Markdown or reStructuredText.
* Automatically use DeepL API Free endpoint for the DeepL API Free authentication keys in :ref:`mt-deepl`.
* Compatibility with third-party static files storage backends for Django.
* Improved language compatibility in :ref:`mt-microsoft-translator`.
* :ref:`check-reused` check gracefully handles languages which are not case sensitive.
* :ref:`component-enforced_checks` are now applied on strings imported from the repository.
* Reduced false positives in :ref:`check-end-colon` and :ref:`check-end-stop` for CJK languages.
* OpenAPI schema for API includes more information.
* :ref:`check-regex` supports advanced regular expressions.
* :ref:`check-same` gracefully deals with case-insensitive languages.

.. rubric:: Bug fixes

* :ref:`check-reused` wrongly triggered after fixing the error.
* Dark theme behavior in some situations.
* Translation propagation sometimes did not work as expected.
* :http:header:`Content-Security-Policy` is now automatically set for AWS.
* :ref:`machine-translation-setup` sometimes cached results too aggressively.
* Fixed translations caching in :ref:`machine-translation-setup`.
* :ref:`autofix-html` automatic fixups honors the ``ignore-safe-html`` flag.
* :ref:`check-punctuation-spacing` no longer applies to Breton.
* Fixed :ref:`addon-weblate.git.squash` on linked repositories.
* :ref:`check-multiple-failures` avoids false positives and better lists related checks.

.. rubric:: Compatibility

* Running tests using Django test executor is no longer supported, see :doc:`/contributing/tests`.
* :ref:`check-bbcode` check is now disabled by default. The `bbcode-text` flag is required to activate this check, see :ref:`custom-checks`.
* API error responses format has changed, see :ref:`api-errors`.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

* There are several changes in :file:`settings_example.py`, most notable are the new settings for :ref:`api` in ``REST_FRAMEWORK``, ``SPECTACULAR_SETTINGS``, ``DRF_STANDARDIZED_ERRORS`` and ``INSTALLED_APPS``; please adjust your settings accordingly.
* PostgreSQL 12 and MariaDB 10.4 are no longer supported.

.. rubric:: Contributors

.. include:: changes/contributors/5.10.rst

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/133?closed=1>`__.

Weblate 5.9.2
-------------

*Released on December 19th 2024.*

.. rubric:: Improvements

* Renamed :ref:`vcs-bitbucket-data-center` to match new product name.
* :http:get:`/api/users/` supports searching by user ID.

.. rubric:: Bug fixes

* Avoid query parser crash in multi-threaded environments.
* Avoid :ref:`autofix` crash on multi-value strings.
* Make project tokens work when :ref:`2fa` or :ref:`component-agreement` are enforced.
* Captcha solution were sometimes not accepted.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

.. rubric:: Contributors

.. include:: changes/contributors/5.9.2.rst

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/135?closed=1>`__.

Weblate 5.9.1
-------------

*Released on December 16th 2024.*

.. rubric:: Bug fixes

* Fixed publishing package to PyPI.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

.. rubric:: Contributors

.. include:: changes/contributors/5.9.1.rst

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/134?closed=1>`__.

Weblate 5.9
-----------

*Released on December 16th 2024.*

.. rubric:: New features

* Per-project :ref:`machine-translation-setup` can now be configured via the Project :ref:`api`.

  * Added :http:get:`/api/projects/{string:project}/machinery_settings/`.
  * Added :http:post:`/api/projects/{string:project}/machinery_settings/`.

* Translation memory import now supports files with XLIFF, PO and CSV formats, see :ref:`memory-user` and :wladmin:`import_memory` command in :ref:`manage`.
* The registration CAPTCHA now includes proof-of-work mechanism ALTCHA.
* Leading problematic characters in CSV are now checks for :ref:`glossary`, see :ref:`check-prohibited-initial-character`.
* Logging to :ref:`graylog`.

.. rubric:: Improvements

* :ref:`mt-google-translate-api-v3` now supports :ref:`glossary-mt` (optional).
* A shortcut to duplicate a component is now available directly in the menu (:guilabel:`Manage` → :guilabel:`Duplicate this component`).
* Included username when generating :ref:`credits`.
* :ref:`bulk-edit` shows a preview of matched strings.
* :http:get:`/api/components/(string:project)/(string:component)/` exposes component lock state.
* Editor in :ref:`zen-mode` is now stick to bottom of screen.
* Added page navigation while :ref:`translating`.
* :ref:`manage-appearance` now has distinct settings for dark mode.
* Improved :ref:`translation-propagation` performance.
* More detailed error messages for :http:post:`/api/translations/(string:project)/(string:component)/(string:language)/file/`.

.. rubric:: Bug fixes

* Using the ``has:variant`` field now correctly displays strings that have variants in the search language, see :ref:`search-strings`.
* Saving newly added strings in some formats.
* :ref:`check-java-printf-format` gracefully handles escaping.

.. rubric:: Compatibility

* :ref:`rollbar-errors` integration no longer includes client-side error collection.
* Weblate now requires Git 2.28 or newer.
* Any custom code that relied on `Change` models signals should be reviewed.
* :ref:`fedora-messaging` integration needs to be updated to be compatible with this release.
* :envvar:`WEB_WORKERS` now configures number of threads instead of processes.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

.. rubric:: Contributors

.. include:: changes/contributors/5.9.rst

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/127?closed=1>`__.

Weblate 5.8.4
-------------

*Released on November 19th 2024.*

.. rubric:: Improvements

* :ref:`search-users` can search based on user changes.

.. rubric:: Bug fixes

* Fixed occasional crash in :ref:`rss`.
* :ref:`check-icu-message-format` gracefully handles plural strings.
* :ref:`vcs-bitbucket-cloud` correctly generates pull request description.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

.. rubric:: Contributors

.. include:: changes/contributors/5.8.4.rst

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/132?closed=1>`__.

Weblate 5.8.3
-------------

*Released on November 6th 2024.*

.. rubric:: Bug fixes

* Formatting of some :ref:`audit-log` entries.
* Fixed XML escaped output in some machine translation integrations.
* Fixed duplicate listing of newly added glossary terms.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

.. rubric:: Contributors

.. include:: changes/contributors/5.8.3.rst

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/131?closed=1>`__.

Weblate 5.8.2
-------------

*Released on November 1st 2024.*

.. rubric:: Bug fixes

* Update outdated plural definitions during the database migration.
* Reduced number of database queries when updating multiple strings.
* Leading problematic characters in :ref:`glossary` terms are now properly stripped in uploaded files.
* Improved :ref:`workflow-customization` performance.
* Fixed XML escaped output in some machine translation integrations.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

.. rubric:: Contributors

.. include:: changes/contributors/5.8.2.rst

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/129?closed=1>`__.

Weblate 5.8.1
-------------

*Released on October 15th 2024.*

.. rubric:: Bug fixes

* Use lower case name for the Python package.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

.. rubric:: Contributors

.. include:: changes/contributors/5.8.1.rst

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/128?closed=1>`__.

Weblate 5.8
-----------

*Released on October 15th 2024.*

.. rubric:: New features

* Added :ref:`component-key_filter` in the component.
* :doc:`/user/search` now supports filtering by object path and :ref:`date-search`.
* Merge requests credentials can now be passed in the repository URL, see :ref:`settings-credentials`.
* :ref:`mt-azure-openai` automatic suggestion service.
* :ref:`vcs-bitbucket-cloud`.

.. rubric:: Improvements

* :ref:`mt-modernmt` supports :ref:`glossary-mt`.
* :ref:`mt-deepl` now supports specifying translation context.
* :ref:`mt-aws` now supports :ref:`glossary-mt`.
* :ref:`autofix` for Devanagari danda now better handles latin script.
* :ref:`autofix` for French and Breton now uses a non-breaking space before colons instead of a narrow one.
* :ref:`api` now has a preview OpenAPI specification.
* Stale, empty glossaries are now automatically removed.
* :kbd:`?` now displays available :ref:`keyboard`.
* Translation and language view in the project now include basic information about the language and plurals.
* :ref:`search-replace` shows a preview of matched strings.
* :ref:`aresource` now support translatable attribute in its strings.
* Creating component via file upload (Translate document) now supports bilingual files.

.. rubric:: Bug fixes

* Displaying :ref:`workflow-customization` setting in some cases.
* Users can add component in any language already existing in a project.
* :ref:`check-unnamed-format` better handles some strings, such as :ref:`check-python-brace-format`.

.. rubric:: Compatibility

* Weblate now requires Python 3.11 or newer.
* :ref:`mt-aws` now requires the `TranslateFullAccess` permission.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

* There are several changes in :file:`settings_example.py`, most notable are the new settings for :ref:`api` in ``SPECTACULAR_SETTINGS`` and changes in ``REST_FRAMEWORK`` and ``INSTALLED_APPS``; please adjust your settings accordingly.

.. rubric:: Contributors

.. include:: changes/contributors/5.8.rst

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/122?closed=1>`__.

Weblate 5.7.2
-------------

*Released on September 5th 2024.*

.. rubric:: Improvements

* :ref:`2fa` remembers last method used by user.
* Instead of redirecting, the sign-out now displays a page.
* Improved readability of exception logs.

.. rubric:: Bug fixes

* Updating of translations from the repository in linked components.
* Improved rendering of digest notification e-mails.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

.. rubric:: Contributors

.. include:: changes/contributors/5.7.2.rst

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/126?closed=1>`__.

Weblate 5.7.1
-------------

*Released on August 30th 2024.*

.. rubric:: Improvements

* Updated language names to better describe different scripts and Sintic languages.
* :ref:`addon-weblate.cleanup.generic` is now automatically installed for formats which need it to update non-translation content in the translated files.

.. rubric:: Bug fixes

* Support for using Docker network names in automatic suggestion settings.
* Fixed authentication using some third-party providers such as Azure.
* Support for formal and informal Portuguese in :ref:`mt-deepl`.
* QR code for TOTP is now black/white even in dark mode.
* Fixed TOTP authentication when WebAuthn is also configured for the user.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

.. rubric:: Contributors

.. include:: changes/contributors/5.7.1.rst

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/125?closed=1>`__.

Weblate 5.7
-----------

*Released on August 15th 2024.*

.. rubric:: New features

* :ref:`2fa` is now supported using Passkeys, WebAuthn, authentication apps (TOTP), and recovery codes.
* :ref:`2fa` can be enforced at the team or project level.
* :ref:`adding-new-strings` can now create plural strings in the user interface.
* :ref:`labels` now include description to explain them.
* New :ref:`subscriptions` for completed translation and component.
* :ref:`mt-openai` now supports custom models and URLs and offers rephrasing of existing strings.
* :ref:`mt-cyrtranslit` automatic suggestion service.

.. rubric:: Improvements

* :ref:`addon-weblate.properties.sort` can now do case-sensitive sorting.
* The status widgets are now supported site-wide and language-wide, see :ref:`promotion`.
* :ref:`reports` are now available for categories.
* Highlight newlines in the editor.
* :doc:`/formats/csv` better handle files with two fields only.
* Browse mode can now be navigated using keyboard, see :ref:`keyboard`.
* :http:get:`/api/components/(string:project)/(string:component)/credits/` and :http:get:`/api/projects/(string:project)/credits/` API endpoints for components and projects.
* :ref:`glossary-terminology` entries in Glossary can now only be created by users with :guilabel:`Add glossary terminology` permission.
* :ref:`check-python-brace-format` detects extra curly braces.
* Screenshots now can be pasted from the clipboard in :ref:`screenshots`.

.. rubric:: Bug fixes

* Accessibility of keyboard navigation.
* :ref:`git-exporter` now works with all Git based :ref:`vcs`.
* :ref:`check-max-size` sometimes failed to render screenshot.

.. rubric:: Compatibility

* Weblate now uses mistletoe instead of misaka as a Markdown renderer.
* :ref:`csp` is now stricter what might block third-party customizations.
* Monolingual formats no longer copy comments from :ref:`component-template` when adding strings to translation.
* Dropped support for Amagama in :ref:`machine-translation-setup` as the service is no longer maintained.
* Default value for :setting:`SENTRY_SEND_PII` was changed.
* Translation credit reports in the JSON format now follows a different format for entries.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

* There are several changes in :file:`settings_example.py`, most notable are the new settings for :ref:`2fa` and changes in ``INSTALLED_APPS``, ``SOCIAL_AUTH_PIPELINE`` and ``MIDDLEWARE``; please adjust your settings accordingly.
* :setting:`ENABLE_HTTPS` is now required for WebAuthn support. If you cannot use HTTPS, please silence related check as described in :setting:`ENABLE_HTTPS` documentation.

.. rubric:: Contributors

.. include:: changes/contributors/5.7.rst

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/116?closed=1>`__.

Weblate 5.6.2
-------------

*Released on July 1st 2024.*

.. rubric:: Bug fixes

* Rendering of :ref:`labels` color selection widget.
* Detection of pending outgoing commits.
* :ref:`addons` button layout.
* Crash when installing :ref:`addon-weblate.discovery.discovery` add-on.
* Removal of source strings in :ref:`glossary`.
* Validation of :ref:`projectbackup` ZIP file upon restoring (CVE-2024-39303 / GHSA-jfgp-674x-6q4p).

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/124?closed=1>`__.

Weblate 5.6.1
-------------

*Released on June 24th 2024.*

.. rubric:: Improvements

* Docker container accepts :envvar:`WEBLATE_REMOVE_ADDONS` and :envvar:`WEBLATE_ADD_MACHINERY` to customize automatic suggestion services and :envvar:`WEBLATE_CORS_ALLOW_ALL_ORIGINS` for CORS handling in API.
* Added OpenMetrics compatibility for :http:get:`/api/metrics/`.

.. rubric:: Bug fixes

* Language aliases in :doc:`/admin/machine`.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/123?closed=1>`__.

Weblate 5.6
-----------

*Released on June 19th 2024.*

.. rubric:: New features

* :ref:`addons` activity log for tracking add-on activity.
* Improved date range selection in :ref:`reports`.

.. rubric:: Improvements

* :ref:`subscriptions` now include strings which need updating.
* Improved compatibility with password managers.
* Improved tracking of uploaded changes.
* Gracefully handle temporary machine translation errors in automatic suggestions.
* :http:get:`/api/units/(int:id)/` now includes `last_updated` timestamp.
* :http:get:`/api/changes/(int:id)/` now includes `old` and `details`.
* Reduced memory usage and increased performance of some views.

.. rubric:: Bug fixes

* Loading of strings with many glossary matches.
* Fixed behavior of some site-wide :ref:`addons`.
* Saving strings needing editing to :doc:`/formats/winrc`.
* :ref:`check-xml-tags` better handle XML entities.
* Automatic suggestions could mix up replacements between translated strings.

.. rubric:: Compatibility

* Compatibility with Django 5.1.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/114?closed=1>`__.

Weblate 5.5.5
-------------

*Released on May 13th 2024.*

.. rubric:: Bug fixes

* False-positive merge failure alert when using push branch.
* Cleanup of stale repositories.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/121?closed=1>`__.

Weblate 5.5.4
-------------

*Released on May 10th 2024.*

.. rubric:: Improvements

* Visually highlight explanation in :ref:`glossary`.
* Add :ref:`addons` history tab in management.
* New :ref:`alerts` when :ref:`glossary` might not work as expected.
* :doc:`/admin/announcements` can be posted on project/language scope.

.. rubric:: Bug fixes

* Improved handling placeables in :ref:`mt-openai`.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/120?closed=1>`__.

Weblate 5.5.3
-------------

*Released on May 3rd 2024.*

.. rubric:: Improvements

* Improved performance of rendering large lists of objects.
* Component management: added links to manage project/site-wide :ref:`addons`.

.. rubric:: Bug fixes

* Fixed crashes with librsvg older than 2.46.
* Daily execution of some :ref:`addons`.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/119?closed=1>`__.

Weblate 5.5.2
-------------

*Released on April 26th 2024.*

.. rubric:: Bug fixes

* Fixed publishing packages to PyPI.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/118?closed=1>`__.

Weblate 5.5.1
-------------

*Released on April 26th 2024.*

.. rubric:: New features

* :doc:`/user/search` supports ``source_changed:DATETIME``.
* Added several new :ref:`component-language_code_style`.

.. rubric:: Improvements

* Display more details on source string change in history.
* :ref:`mt-microsoft-translator` now supports using custom translators.
* Improved error handling in :ref:`invite-user`.
* Added PNG status badge.
* Added list of managed projects to the dashboard view.
* More detailed status of outgoing commits.
* Reduced memory usage.

.. rubric:: Bug fixes

* Fixed skipped component update with some add-ons enabled.
* Daily execution of project and site wide add-ons.
* Allow editing strings when the source is marked for editing.
* Updates of the last updated timestamp of a string.
* Fixed project and site wide installation of :ref:`addon-weblate.git.squash` and :ref:`addon-weblate.discovery.discovery` add-ons.
* Graceful handling of locking errors in the :ref:`api`.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

* There is a change in ``REST_FRAMEWORK`` setting (newly added ``EXCEPTION_HANDLER``).

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/117?closed=1>`__.

Weblate 5.5
-----------

*Released on April 20th 2024.*

.. rubric:: New features

* :ref:`addons` can be now installed project-wide and site-wide.

* API improvements.

  * Added :http:get:`/api/categories/(int:id)/statistics/`.
  * Added :http:get:`/api/projects/(string:project)/file/`.
  * Added :http:post:`/api/groups/(int:id)/admins/`.
  * Added :http:delete:`/api/groups/(int:id)/admins/(int:user_id)`.
  * Improved :http:post:`/api/translations/(string:project)/(string:component)/(string:language)/units/`.

* Added :ref:`mt-systran` automatic translation support.

.. rubric:: Improvements

* Docker container now validates user password strength by default, see :envvar:`WEBLATE_MIN_PASSWORD_SCORE`.
* Improved error reporting in :ref:`machine-translation-setup`.
* :ref:`check-max-size` better displays rendered text.
* Admins can now specify username and full name when :ref:`invite-user`.
* Added :ref:`check-end-interrobang`.
* :ref:`alerts` are now refreshed when needed, not just daily.
* :doc:`/devel/reporting` uses specific word count for CJK languages.
* Team membership changes are now tracked in :ref:`audit-log`.

.. rubric:: Bug fixes

* :ref:`check-check-glossary` works better for languages not using whitespace.
* :ref:`alerts` better handle non-latin source languages.
* :ref:`check-max-size` sometimes ignored ``font-spacing:SPACING`` flag.
* Fixed per-language statistics on nested categories.
* Fixed categories listing on per-language pages.
* Fixed :guilabel:`Needs editing` state calculation.
* Fixed changing :ref:`component-push` with :ref:`vcs-gerrit`.
* Fixed using categorized components in :ref:`manage`, :ref:`memory` or :ref:`auto-translation`.

.. rubric:: Compatibility

* Several API calls might be affected by stricter validation of boolean fields by Django REST Framework. For example :http:post:`/api/projects/(string:project)/components/`.
* Uniqueness of name and slug of a component is now enforced at the database level on PostgreSQL 15+.
* Docker image now ships Python packages in :file:`/app/venv` and installs using :program:`uv`.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

* There are several changes in :file:`settings_example.py`, most notable is changes in ``INSTALLED_APPS`` and ``LOGOUT_REDIRECT_URL``, please adjust your settings accordingly.
* Weblate now requires Python 3.10 and Django 5.0.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/111?closed=1>`__.

Weblate 5.4.3
-------------

*Released on March 26th 2024.*

.. rubric:: Bug fixes

* Superuser access to components with :ref:`component-restricted`.
* Adjusted default :setting:`LOGIN_REQUIRED_URLS_EXCEPTIONS` to not block :ref:`manage-appearance`.
* Avoid crash on pushing changes to diverged repository.
* Avoid crash when installing :ref:`addon-weblate.generate.pseudolocale`.
* :ref:`azure-setup` gracefully handles repositories with spaces in URL.
* :ref:`mt-deepl` gracefully handles glossaries for language variants.
* :doc:`/formats/excel` better handles blank cells.
* Fixed possible data loss when merging gettext PO file changes in Git.
* Repository operations on project could have skipped some components.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/115?closed=1>`__.

Weblate 5.4.2
-------------

*Released on February 22nd 2024.*

.. rubric:: Bug fixes

* Displaying debugging page in case of database connection issues.
* Gracefully handle migration with duplicate built-in teams.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/113?closed=1>`__.

Weblate 5.4.1
-------------

*Released on February 19th 2024.*

.. rubric:: Bug fixes

* Possible crash on Weblate upgrade check when cached from the previous versions.
* Gracefully handle migration with duplicate built-in teams.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/112?closed=1>`__.

Weblate 5.4
-----------

*Released on February 15th 2024.*

.. rubric:: New features

* :ref:`check-perl-brace-format` quality check.
* :doc:`/formats/moko`.
* :doc:`/formats/formatjs`.
* Search input is now syntax highlighted, see :doc:`/user/search`.
* Weblate is now available in தமிழ்.

.. rubric:: Improvements

* Better logging in :wladmin:`createadmin`.
* :ref:`addon-weblate.discovery.discovery` now reports skipped entries.
* Adding string in a repository triggers :ref:`subscriptions`.
* :ref:`mt-openai` better handles batch translations and glossaries.
* :ref:`mt-libretranslate` better handles batch translations.
* Text variant of notification e-mails now properly indicate changed strings.
* File downloads now honor :http:header:`If-Modified-Since`.
* :ref:`num-words` support for CJK languages.
* :ref:`addon-weblate.discovery.discovery` now preserves :ref:`componentlists`.
* Nicer formatting of :ref:`glossary` tooltips.
* :http:get:`/api/components/(string:project)/(string:component)/` now includes information about linked component.
* Improved :ref:`workflow-customization` configuration forms.

.. rubric:: Bug fixes

* Plural forms handling in :doc:`/formats/qt`.
* Added missing documentation for :setting:`ADMINS_CONTACT`.
* Automatic fixer for :ref:`autofix-punctuation-spacing` no longer adds new whitespace.
* Pending changes committing could be omitted under some circumstances.
* :ref:`addon-weblate.cleanup.blank` now correctly removes blank plurals.

.. rubric:: Compatibility

* Last changed timestamp now reflects changes outside Weblate as well. This affects both :ref:`api` and the user interface.
* Releases are signed by Sigstore instead of PGP, see :ref:`verify`.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/109?closed=1>`__.

Weblate 5.3.1
-------------

*Released on December 19th 2023.*

.. rubric:: Bug fixes

* Not updating statistics in some situations.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/110?closed=1>`__.

Weblate 5.3
-----------

*Released on December 14th 2023.*

.. rubric:: New features

* :ref:`mt-openai` automatic suggestion service.
* :ref:`mt-alibaba` automatic suggestion service.
* Added labels API, see :http:get:`/api/projects/(string:project)/labels/`.
* :ref:`glossary-mt`.
* New automatic fixer for :ref:`autofix-punctuation-spacing`.
* :ref:`mt-google-translate-api-v3` now better honors placeables or line breaks.

.. rubric:: Improvements

* Reduced memory usage for statistics.
* :ref:`mt-deepl` performs better in :ref:`auto-translation` and supports :ref:`glossary-mt`.
* :ref:`mt-microsoft-translator` supports :ref:`glossary-mt`.
* Improved region selection in :ref:`mt-google-translate-api-v3`.
* Added nested JSON exporter in :ref:`download`.
* Improved :ref:`git-exporter` performance on huge repositories.

.. rubric:: Bug fixes

* Removing stale VCS directories.

.. rubric:: Compatibility

* Dropped Microsoft Terminology service for automatic suggestions, as it is no longer provided by Microsoft.
* ``labels`` in units API now expose full label info, see :http:get:`/api/units/(int:id)/`.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/107?closed=1>`__.

Weblate 5.2.1
-------------

*Released on November 22nd 2023.*

.. rubric:: Improvements

* Show search field after no strings found while translating.
* Added soft hyphen to special-characters toolbar.

.. rubric:: Bug fixes

* Database backups compatibility with Alibaba Cloud Database PolarDB.
* Crash on loading statistics calculated by previous versions.
* Sort icons in dark mode.
* Project level statistics no longer count categorized components twice.
* Possible discarding pending translations after editing source strings.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/108?closed=1>`__.

Weblate 5.2
-----------

*Released on November 16th 2023.*

.. rubric:: New features

* :ref:`vcs-azure-devops`.

.. rubric:: Improvements

* Faster statistics updates.
* Better e-mail selection in user profile.
* :ref:`autofix` are now applied to suggestions as well.
* :ref:`mt-deepl` can now configure default formality for translations.
* Use neutral colors for progress bars and translation unit states.
* :ref:`addon-weblate.gettext.mo` can optionally include strings needing editing.
* Use :http:header:`Accept-Language` to order translations for unauthenticated users.
* Add option to directly approve suggestions with :ref:`reviews` workflow.
* One-click removal of project or component :ref:`subscriptions`.
* :ref:`api-statistics` now includes character and word counts for more string states.

.. rubric:: Bug fixes

* Fixed creating component within a category by upload.
* Error handling in organizing components and categories.
* Fixed moving categories between projects.
* Fixed formatting of translation memory search results.
* Allow non-breaking space character in :ref:`autofix-html`.

.. rubric:: Compatibility

* :doc:`/formats/apple` exporter now produces UTF-8 encoded files.
* Python 3.12 is now supported, though not recommended, see :ref:`python-deps`.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/104?closed=1>`__.

Weblate 5.1.1
-------------

*Released on October 25th 2023.*

.. rubric:: Improvements

* :ref:`addon-weblate.consistency.languages` now uses a dedicated user for changes.
* Added button for sharing on Fediverse.
* Added validation for VCS integration credentials.
* Reduced overhead of statistics collection.

.. rubric:: Bug fixes

* Added plurals validation when editing string using the API.
* Replacing a file using upload when existing is corrupted.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/106?closed=1>`__.

Weblate 5.1
-----------

*Released on October 16th 2023.*

.. rubric:: New features

* :ref:`mt-yandex-v2` machine translation service.
* :ref:`addon-weblate.autotranslate.autotranslate` and :ref:`auto-translation` are now stored with a dedicated user as an author.
* :ref:`addons` changes to strings are now stored with a dedicated user as an author.
* :ref:`download-multi` can now convert file formats.
* :ref:`workflow-customization` allows to fine-tune localization workflow per language.

.. rubric:: Improvements

* :ref:`project-translation_review` also shows the approval percentage in object listings.
* Project is added to watched upon accepting an invitation.
* Configure VCS API credentials as a Python dict from environment variables.
* Improved accuracy of checks on plural messages.
* Engage page better shows stats.
* Strings which can not be saved to a file no longer block other strings to be written.
* Fixed some API URLs for categorized components.
* Show plural form examples more prominently.
* Highlight whitespace in :ref:`machine-translation`.
* Faster comment and component removal.
* Show disabled save button reason more prominently.
* New string notification can now be triggered for each string.

.. rubric:: Bug fixes

* Improved OCR error handling in :ref:`screenshots`.
* :ref:`autofix` gracefully handle strings from :ref:`multivalue-csv`.
* Occasional crash in :ref:`machine-translation` caching.
* Fixed history listing for entries within a :ref:`category`.
* Fixed editing :guilabel:`Administration` team.
* :ref:`addon-weblate.consistency.languages` add-on could miss some languages.

.. rubric:: Compatibility

* Categories are now included ``weblate://`` repository URLs.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

* Upgrades from older version than 5.0.2 are not supported, please upgrade to 5.0.2 first and then continue in upgrading.
* Dropped support for deprecated insecure configuration of VCS service API keys via _TOKEN/_USERNAME in :file:`settings.py`.
* Weblate now defaults to persistent database connections in :file:`settings_example.py` and Docker.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/100?closed=1>`__.

Weblate 5.0.2
-------------

*Released on September 14th 2023.*

.. rubric:: Improvements

* Translate page performance.
* Search now looks for categories as well.

.. rubric:: Bug fixes

* Rendering of release notes on GitHub.
* Listing of categorized projects.
* Translating a language inside a category.
* Categories sorting.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

* The database upgrade can take considerable time on larger sites due to indexing changes.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/105?closed=1>`__.

Weblate 5.0.1
-------------

*Released on September 10th 2023.*

.. rubric:: New features

* Added :http:get:`/api/component-lists/(str:slug)/components/`.

.. rubric:: Improvements

* Related glossary terms lookup is now faster.
* Logging of failures when creating pull requests.
* History is now loaded faster.
* Added object ``id`` to all :ref:`api` endpoints.
* Better performance of projects with a lot of components.
* Added compatibility redirects for some old URLs.

.. rubric:: Bug fixes

* Creating component within a category.
* Source strings and state display for converted formats.
* Block :ref:`component-edit_template` on formats which do not support it.
* :ref:`check-reused` is no longer triggered for blank strings.
* Performance issues while browsing some categories.
* Fixed GitHub Team and Organization authentication in Docker container.
* GitLab merge requests when using a customized SSH port.

.. rubric:: Compatibility

* `pyahocorasick` dependency has been replaced by `ahocorasick_rs`.
* The default value of :setting:`IP_PROXY_OFFSET` has been changed from 1 to -1.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

* The database upgrade can take considerable time on larger sites due to indexing changes.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/103?closed=1>`__.

Weblate 5.0
-----------

*Released on August 24th 2023.*

.. rubric:: New features

* :doc:`/formats/markdown` support, thanks to Anders Kaplan.
* :ref:`category` can now organize components within a project.
* :doc:`/formats/fluent` now has better syntax checks thanks to Henry Wilkes.
* Inviting users now works with all authentication methods.
* Docker container supports file backed secrets, see :ref:`docker-secrets`.

.. rubric:: Improvements

* Plurals handling in machine translation.
* :ref:`check-same` check now honors placeholders even in the strict mode.
* :ref:`check-reused` is no longer triggered for languages with a single plural form.
* WebP is now supported for :ref:`screenshots`.
* Avoid duplicate notification when a user is subscribed to overlapping scopes.
* OCR support for non-English languages in :ref:`screenshots`.
* :ref:`xliff` now supports displaying source string location.
* Rendering strings with plurals, placeholders or alternative translations.
* User API now includes last sign in date.
* User API token is now hidden for privacy reasons by default.
* Faster adding terms to glossary.
* Better preserve translation on source file change in :doc:`/formats/html` and :doc:`/formats/txt`.
* Added indication of automatic assignment to team listing.
* Users now have to confirm invitations to become team members.
* :ref:`check-formats` can now check all plural forms with the ``strict-format`` flag.
* :doc:`/user/checks` browsing experience.
* Highlight differences in the source string in automatic suggestions.
* Visual diff now better understands compositing characters.

.. rubric:: Bug fixes

* User names handling while committing to Git.
* :ref:`addon-weblate.cleanup.blank` and :ref:`addon-weblate.cleanup.generic` now remove all strings at once.
* Language filtering in :doc:`/devel/reporting`.
* Reduced false positives of :ref:`check-reused` when fixing the translation.
* Fixed caching issues after updating screenshots from the repository.

.. rubric:: Compatibility

* Python 3.9 or newer is now required.
* Several UI URLs have been changed to be able to handle categories.

.. rubric:: Upgrading

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

* There are several changes in :file:`settings_example.py`, most notable is changes in ``CACHES`` and ``SOCIAL_AUTH_PIPELINE``, please adjust your settings accordingly.
* Several previously optional dependencies are now required.
* The database upgrade can take considerable time on larger sites due to structure changes.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/99?closed=1>`__.
