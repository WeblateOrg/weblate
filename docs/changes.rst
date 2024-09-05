Weblate 5.7.2
-------------

Released on September 5th 2024.

**New features**

**Improvements**

* :ref:`2fa` remembers last method used by user.
* Instead of redirecting, the sign-out now displays a page.
* Improved readability of exception logs.

**Bug fixes**

* Updating of translations from the repository in linked components.
* Improved rendering of digest notification e-mails.

**Compatibility**

**Upgrading**

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

**Contributors**

.. include:: changes/contributors/5.7.2.rst

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/126?closed=1>`__.

Weblate 5.7.1
-------------

Released on August 30th 2024.

**Improvements**

* Updated language names to better describe different scripts and Sintic languages.
* :ref:`addon-weblate.cleanup.generic` is now automatically installed for formats which need it to update non-translation content in the translated files.

**Bug fixes**

* Support for using Docker network names in automatic suggestion settings.
* Fixed authentication using some third-party providers such as Azure.
* Support for formal and informal Portuguese in :ref:`mt-deepl`.
* QR code for TOTP is now black/white even in dark mode.
* Fixed TOTP authentication when WebAuthn is also configured for the user.

**Upgrading**

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

**Contributors**

.. include:: changes/contributors/5.7.1.rst

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/125?closed=1>`__.

Weblate 5.7
-----------

Released on August 15th 2024.

**New features**

* :ref:`2fa` is now supported using Passkeys, WebAuthn, authentication apps (TOTP), and recovery codes.
* :ref:`2fa` can be enforced at the team or project level.
* :ref:`adding-new-strings` can now create plural strings in the user interface.
* :ref:`labels` now include description to explain them.
* New :ref:`subscriptions` for completed translation and component.
* :ref:`mt-openai` now supports custom models and URLs and offers rephrasing of existing strings.
* :ref:`mt-cyrtranslit` automatic suggestion service.

**Improvements**

* :ref:`addon-weblate.properties.sort` can now do case-sensitive sorting.
* The status widgets are now supported site-wide and language-wide, see :ref:`promotion`.
* :ref:`reports` are now available for categories.
* Highlight newlines in the editor.
* :doc:`/formats/csv` better handle with with two fields only.
* Browse mode can now be navigated using keyboard, see :ref:`keyboard`.
* :http:get:`/api/components/(string:project)/(string:component)/credits/` and :http:get:`/api/projects/(string:project)/credits/` API endpoints for components and projects.
* :ref:`glossary-terminology` entries in Glossary can now only be created by users with :guilabel:`Add glossary terminology` permission.
* :ref:`check-python-brace-format` detects extra curly braces.
* Screenshots now can be pasted from the clipboard in :ref:`screenshots`.

**Bug fixes**

* Accessibility of keyboard navigation.
* :ref:`git-exporter` now works with all Git based :ref:`vcs`.
* :ref:`check-max-size` sometimes failed to render screenshot.

**Compatibility**

* Weblate now uses mistletoe instead of misaka as a Markdown renderer.
* :ref:`csp` is now stricter what might block third-party customizations.
* Monolingual formats no longer copy comments from :ref:`component-template` when adding strings to translation.
* Dropped support for Amagama in :ref:`machine-translation-setup` as the service is no longer maintained.
* Default value for :setting:`SENTRY_SEND_PII` was changed.
* Translation credit reports in the JSON format now follows a different format for entries.

**Upgrading**

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

* There are several changes in :file:`settings_example.py`, most notable are the new settings for :ref:`2fa` and changes in ``INSTALLED_APPS``, ``SOCIAL_AUTH_PIPELINE`` and ``MIDDLEWARE``; please adjust your settings accordingly.
* :setting:`ENABLE_HTTPS` is now required for WebAuthn support. If you cannot use HTTPS, please silence related check as described in :setting:`ENABLE_HTTPS` documentation.

**Contributors**

.. include:: changes/contributors/5.7.rst

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/116?closed=1>`__.

Weblate 5.6.2
-------------

Released on July 1st 2024.

**Bug fixes**

* Rendering of :ref:`labels` color selection widget.
* Detection of pending outgoing commits.
* :ref:`addons` button layout.
* Crash when installing :ref:`addon-weblate.discovery.discovery` add-on.
* Removal of source strings in :ref:`glossary`.
* Validation of :ref:`projectbackup` ZIP file upon restoring (CVE-2024-39303 / GHSA-jfgp-674x-6q4p).

**Upgrading**

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/124?closed=1>`__.

Weblate 5.6.1
-------------

Released on June 24th 2024.

**Improvements**

* Docker container accepts :envvar:`WEBLATE_REMOVE_ADDONS` and :envvar:`WEBLATE_ADD_MACHINERY` to customize automatic suggestion services and :envvar:`WEBLATE_CORS_ALLOW_ALL_ORIGINS` for CORS handling in API.
* Added OpenMetrics compatibility for :http:get:`/api/metrics/`.

**Bug fixes**

* Language aliases in :doc:`/admin/machine`.

**Upgrading**

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/123?closed=1>`__.

Weblate 5.6
-----------

Released on June 19th 2024.

**New features**

* :ref:`addons` activity log for tracking add-on activity.
* Improved date range selection in :ref:`reports`.

**Improvements**

* :ref:`subscriptions` now include strings which need updating.
* Improved compatibility with password managers.
* Improved tracking of uploaded changes.
* Gracefully handle temporary machine translation errors in automatic suggestions.
* :http:get:`/api/units/(int:id)/` now includes `last_updated` timestamp.
* :http:get:`/api/changes/(int:id)/` now includes `old` and `details`.
* Reduced memory usage and increased performance of some views.

**Bug fixes**

* Loading of strings with many glossary matches.
* Fixed behavior of some site-wide :ref:`addons`.
* Saving strings needing editing to :doc:`/formats/winrc`.
* :ref:`check-xml-tags` better handle XML entities.
* Automatic suggestions could mix up replacements between translated strings.

**Compatibility**

* Compatibility with Django 5.1.

**Upgrading**

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/114?closed=1>`__.

Weblate 5.5.5
-------------

Released on May 13th 2024.

**Bug fixes**

* False-positive merge failure alert when using push branch.
* Cleanup of stale repositories.

**Upgrading**

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/121?closed=1>`__.

Weblate 5.5.4
-------------

Released on May 10th 2024.

**Improvements**

* Visually highlight explanation in :ref:`glossary`.
* Add :ref:`addons` history tab in management.
* New :ref:`alerts` when :ref:`glossary` might not work as expected.
* :doc:`/admin/announcements` can be posted on project/language scope.

**Bug fixes**

* Improved handling placeables in :ref:`mt-openai`.

**Upgrading**

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/120?closed=1>`__.

Weblate 5.5.3
-------------

Released on May 3rd 2024.

**Improvements**

* Improved performance of rendering large lists of objects.
* Component management: added links to manage project/site-wide :ref:`addons`.

**Bug fixes**

* Fixed crashes with librsvg older than 2.46.
* Daily execution of some :ref:`addons`.

**Upgrading**

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/119?closed=1>`__.

Weblate 5.5.2
-------------

Released on April 26th 2024.

**Bug fixes**

* Fixed publishing packages to PyPI.

**Upgrading**

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/118?closed=1>`__.

Weblate 5.5.1
-------------

Released on April 26th 2024.

**New features**

* :ref:`Searching` supports ``source_changed:DATETIME``.
* Added several new :ref:`component-language_code_style`.

**Improvements**

* Display more details on source string change in history.
* :ref:`mt-microsoft-translator` now supports using custom translators.
* Improved error handling in :ref:`invite-user`.
* Added PNG status badge.
* Added list of managed projects to the dashboard view.
* More detailed status of outgoing commits.
* Reduced memory usage.

**Bug fixes**

* Fixed skipped component update with some add-ons enabled.
* Daily execution of project and site wide add-ons.
* Allow editing strings when the source is marked for editing.
* Updates of the last updated timestamp of a string.
* Fixed project and site wide installation of :ref:`addon-weblate.git.squash` and :ref:`addon-weblate.discovery.discovery` add-ons.
* Graceful handling of locking errors in the :ref:`api`.

**Upgrading**

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

* There is a change in ``REST_FRAMEWORK`` setting (newly added ``EXCEPTION_HANDLER``).

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/117?closed=1>`__.

Weblate 5.5
-----------

Released on April 20th 2024.

**New features**

* :ref:`addons` can be now installed project-wide and site-wide.

* API improvements

  * Added :http:get:`/api/categories/(int:id)/statistics/`.
  * Added :http:get:`/api/projects/(string:project)/file/`.
  * Added :http:post:`/api/groups/(int:id)/admins/`.
  * Added :http:delete:`/api/groups/(int:id)/admins/(int:user_id)`.
  * Improved :http:post:`/api/translations/(string:project)/(string:component)/(string:language)/units/`.

* Added :ref:`mt-systran` automatic translation support.

**Improvements**

* Docker container now validates user password strength by default, see :envvar:`WEBLATE_MIN_PASSWORD_SCORE`.
* Improved error reporting in :ref:`machine-translation-setup`.
* :ref:`check-max-size` better displays rendered text.
* Admins can now specify username and full name when :ref:`invite-user`.
* Added :ref:`check-end-interrobang`.
* :ref:`alerts` are now refreshed when needed, not just daily.
* :doc:`/devel/reporting` uses specific word count for CJK languages.
* Team membership changes are now tracked in :ref:`audit-log`.

**Bug fixes**

* :ref:`check-check-glossary` works better for languages not using whitespace.
* :ref:`alerts` better handle non-latin source languages.
* :ref:`check-max-size` sometimes ignored ``font-spacing:SPACING`` flag.
* Fixed per-language statistics on nested categories.
* Fixed categories listing on per-language pages.
* Fixed :guilabel:`Needs editing` state calculation.
* Fixed changing :ref:`component-push` with :ref:`vcs-gerrit`.
* Fixed using categorized components in :ref:`manage`, :ref:`memory` or :ref:`auto-translation`.

**Compatibility**

* Several API calls might be affected by stricter validation of boolean fields by Django REST Framework. For example :http:post:`/api/projects/(string:project)/components/`.
* Uniqueness of name and slug of a component is now enforced at the database level on PostgreSQL 15+.
* Docker image now ships Python packages in :file:`/app/venv` and installs using :program:`uv`.

**Upgrading**

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

* There are several changes in :file:`settings_example.py`, most notable is changes in ``INSTALLED_APPS`` and ``LOGOUT_REDIRECT_URL``, please adjust your settings accordingly.
* Weblate now requires Python 3.10 and Django 5.0.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/111?closed=1>`__.

Weblate 5.4.3
-------------

Released on March 26th 2024.

**Bug fixes**

* Superuser access to components with :ref:`component-restricted`.
* Adjusted default :setting:`LOGIN_REQUIRED_URLS_EXCEPTIONS` to not block :ref:`manage-appearance`.
* Avoid crash on pushing changes to diverged repository.
* Avoid crash when installing :ref:`addon-weblate.generate.pseudolocale`.
* :ref:`azure-setup` gracefully handles repositories with spaces in URL.
* :ref:`mt-deepl` gracefully handles glossaries for language variants.
* :doc:`/formats/excel` better handles blank cells.
* Fixed possible data loss when merging gettext PO file changes in Git.
* Repository operations on project could have skipped some components.

**Upgrading**

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/115?closed=1>`__.

Weblate 5.4.2
-------------

Released on February 22nd 2024.

**Bug fixes**

* Displaying debugging page in case of database connection issues.
* Gracefully handle migration with duplicate built-in teams.

**Upgrading**

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/113?closed=1>`__.

Weblate 5.4.1
-------------

Released on February 19th 2024.

**Bug fixes**

* Possible crash on Weblate upgrade check when cached from the previous versions.
* Gracefully handle migration with duplicate built-in teams.

**Upgrading**

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/112?closed=1>`__.

Weblate 5.4
-----------

Released on February 15th 2024.

**New features**

* :ref:`check-perl-brace-format` quality check.
* :doc:`/formats/moko`.
* :doc:`/formats/formatjs`.
* Search input is now syntax highlighted, see :doc:`/user/search`.
* Weblate is now available in தமிழ்.

**Improvements**

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

**Bug fixes**

* Plural forms handling in :doc:`/formats/qt`.
* Added missing documentation for :setting:`ADMINS_CONTACT`.
* Automatic fixer for :ref:`autofix-punctuation-spacing` no longer adds new whitespace.
* Pending changes committing could be omitted under some circumstances.
* :ref:`addon-weblate.cleanup.blank` now correctly removes blank plurals.

**Compatibility**

* Last changed timestamp now reflects changes outside Weblate as well. This affects both :ref:`api` and the user interface.
* Releases are signed by Sigstore instead of PGP, see :ref:`verify`.

**Upgrading**

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/109?closed=1>`__.

Weblate 5.3.1
-------------

Released on December 19th 2023.

**Bug fixes**

* Not updating statistics in some situations.

**Upgrading**

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/110?closed=1>`__.

Weblate 5.3
-----------

Released on December 14th 2023.

**New features**

* :ref:`mt-openai` automatic suggestion service.
* :ref:`mt-alibaba` automatic suggestion service.
* Added labels API, see :http:get:`/api/projects/(string:project)/labels/`.
* :ref:`glossary-mt`.
* New automatic fixer for :ref:`autofix-punctuation-spacing`.
* :ref:`mt-google-translate-api-v3` now better honors placeables or line breaks.

**Improvements**

* Reduced memory usage for statistics.
* :ref:`mt-deepl` performs better in :ref:`auto-translation` and supports :ref:`glossary-mt`.
* :ref:`mt-microsoft-translator` supports :ref:`glossary-mt`.
* Improved region selection in :ref:`mt-google-translate-api-v3`.
* Added nested JSON exporter in :ref:`download`.
* Improved :ref:`git-exporter` performance on huge repositories.

**Bug fixes**

* Removing stale VCS directories.

**Compatibility**

* Dropped Microsoft Terminology service for automatic suggestions, as it is no longer provided by Microsoft.
* ``labels`` in units API now expose full label info, see :http:get:`/api/units/(int:id)/`.

**Upgrading**

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/107?closed=1>`__.

Weblate 5.2.1
-------------

Released on November 22nd 2023.

**Improvements**

* Show search field after no strings found while translating.
* Added soft hyphen to special-characters toolbar.

**Bug fixes**

* Database backups compatibility with Alibaba Cloud Database PolarDB.
* Crash on loading statistics calculated by previous versions.
* Sort icons in dark mode.
* Project level statistics no longer count categorized components twice.
* Possible discarding pending translations after editing source strings.

**Upgrading**

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/108?closed=1>`__.

Weblate 5.2
-----------

Released on November 16th 2023.

**New features**

* :ref:`vcs-azure-devops`

**Improvements**

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

**Bug fixes**

* Fixed creating component within a category by upload.
* Error handling in organizing components and categories.
* Fixed moving categories between projects.
* Fixed formatting of translation memory search results.
* Allow non-breaking space character in :ref:`autofix-html`.

**Compatibility**

* :doc:`/formats/apple` exporter now produces UTF-8 encoded files.
* Python 3.12 is now supported, though not recommended, see :ref:`python-deps`.

**Upgrading**

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/104?closed=1>`__.

Weblate 5.1.1
-------------

Released on October 25th 2023.

**New features**

**Improvements**

* :ref:`addon-weblate.consistency.languages` now uses a dedicated user for changes.
* Added button for sharing on Fediverse.
* Added validation for VCS integration credentials.
* Reduced overhead of statistics collection.

**Bug fixes**

* Added plurals validation when editing string using the API.
* Replacing a file using upload when existing is corrupted.

**Compatibility**

**Upgrading**

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/106?closed=1>`__.

Weblate 5.1
-----------

Released on October 16th 2023.

**New features**

* :ref:`mt-yandex-v2` machine translation service.
* :ref:`addon-weblate.autotranslate.autotranslate` and :ref:`auto-translation` are now stored with a dedicated user as an author.
* :ref:`addons` changes to strings are now stored with a dedicated user as an author.
* :ref:`download-multi` can now convert file formats.
* :ref:`workflow-customization` allows to fine-tune localization workflow per language.

**Improvements**

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

**Bug fixes**

* Improved OCR error handling in :ref:`screenshots`.
* :ref:`autofix` gracefully handle strings from :ref:`multivalue-csv`.
* Occasional crash in :ref:`machine-translation` caching.
* Fixed history listing for entries within a :ref:`category`.
* Fixed editing :guilabel:`Administration` team.
* :ref:`addon-weblate.consistency.languages` add-on could miss some languages.

**Compatibility**

* Categories are now included ``weblate://`` repository URLs.

**Upgrading**

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

* Upgrades from older version than 5.0.2 are not supported, please upgrade to 5.0.2 first and then continue in upgrading.
* Dropped support for deprecated insecure configuration of VCS service API keys via _TOKEN/_USERNAME in :file:`settings.py`.
* Weblate now defaults to persistent database connections in :file:`settings_example.py` and Docker.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/100?closed=1>`__.

Weblate 5.0.2
-------------

Released on September 14th 2023.

**Improvements**

* Translate page performance.
* Search now looks for categories as well.

**Bug fixes**

* Rendering of release notes on GitHub.
* Listing of categorized projects.
* Translating a language inside a category.
* Categories sorting.

**Upgrading**

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

* The database upgrade can take considerable time on larger sites due to indexing changes.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/105?closed=1>`__.

Weblate 5.0.1
-------------

Released on September 10th 2023.

**New features**

* Added :http:get:`/api/component-lists/(str:slug)/components/`.

**Improvements**

* Related glossary terms lookup is now faster.
* Logging of failures when creating pull requests.
* History is now loaded faster.
* Added object ``id`` to all :ref:`api` endpoints.
* Better performance of projects with a lot of components.
* Added compatibility redirects for some old URLs.

**Bug fixes**

* Creating component within a category.
* Source strings and state display for converted formats.
* Block :ref:`component-edit_template` on formats which do not support it.
* :ref:`check-reused` is no longer triggered for blank strings.
* Performance issues while browsing some categories.
* Fixed GitHub Team and Organization authentication in Docker container.
* GitLab merge requests when using a customized SSH port.

**Compatibility**

* `pyahocorasick` dependency has been replaced by `ahocorasick_rs`.
* The default value of :setting:`IP_PROXY_OFFSET` has been changed from 1 to -1.

**Upgrading**

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

* The database upgrade can take considerable time on larger sites due to indexing changes.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/103?closed=1>`__.

Weblate 5.0
-----------

Released on August 24th 2023.

**New features**

* :doc:`/formats/markdown` support, thanks to Anders Kaplan.
* :ref:`category` can now organize components within a project.
* :doc:`/formats/fluent` now has better syntax checks thanks to Henry Wilkes.
* Inviting users now works with all authentication methods.
* Docker container supports file backed secrets, see :ref:`docker-secrets`.

**Improvements**

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

**Bug fixes**

* User names handling while committing to Git.
* :ref:`addon-weblate.cleanup.blank` and :ref:`addon-weblate.cleanup.generic` now remove all strings at once.
* Language filtering in :doc:`/devel/reporting`.
* Reduced false positives of :ref:`check-reused` when fixing the translation.
* Fixed caching issues after updating screenshots from the repository.

**Compatibility**

* Python 3.9 or newer is now required.
* Several UI URLs have been changed to be able to handle categories.

**Upgrading**

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

* There are several changes in :file:`settings_example.py`, most notable is changes in ``CACHES`` and ``SOCIAL_AUTH_PIPELINE``, please adjust your settings accordingly.
* Several previously optional dependencies are now required.
* The database upgrade can take considerable time on larger sites due to structure changes.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/99?closed=1>`__.
