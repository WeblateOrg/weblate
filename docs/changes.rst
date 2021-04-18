Weblate 4.6
-----------

Released on April 19th 2021.

* The auto_translate management command has now a parameter for specifying translation mode.
* Added support for :ref:`txt`.
* Added trends and metrics for all objects.
* Added support for direct copying text from secondary languages.
* Added date filtering when browsing changes.
* Improved activity charts.
* Sender for contact form e-mails can now be configured.
* Improved parameters validation in component creation API.
* The rate limiting no longer applies to superusers.
* Improved automatic translation addon performance and reliability.
* The rate limiting now can be customized in the Docker container.
* API for creating components now automatically uses :ref:`internal-urls`.
* Simplified state indication while listing strings.
* Password hashing now uses Argon2 by default.
* Simplified progress bars indicating translation status.
* Renamed :ref:`addon-weblate.consistency.languages` to clarify the purpose.
* Fixed saving string state to XLIFF.
* Added language-wide search.
* Initial support for :ref:`docker-scaling` the Docker deployment.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/61?closed=1>`__.

Weblate 4.5.3
-------------

Released on April 1st 2021.

* Fixed metrics collection.
* Fixed possible crash when adding strings.
* Improved search query examples.
* Fixed possible loss of newly added strings on replace upload.

Weblate 4.5.2
-------------

Released on March 26th 2021.

* Configurable schedule for automatic translation.
* Added Lua format check.
* Ignore format strings in the :ref:`check-duplicate` check.
* Allow uploading screenshot from a translate page.
* Added forced file synchronization to the repository maintenance.
* Fixed automatic suggestions for languages with a longer code.
* Improved performance when adding new strings.
* Several bug fixes in quality checks.
* Several performance improvements.
* Added integration with :ref:`discover-weblate`.
* Fixed checks behavior with read-only strings.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/63?closed=1>`__.

Weblate 4.5.1
-------------

Released on March 05th 2021.

* Fixed editing of glossary flags in some corner cases.
* Extend metrics usage to improve performance of several pages.
* Store correct source language in TMX files.
* Better handling for uploads of monolingual PO using API.
* Improved alerts behavior glossaries.
* Improved Markdown link checks.
* Indicate glossary and source language in breadcrumbs.
* Paginated component listing of huge projects.
* Improved performance of translation, component or project removal.
* Improved bulk edit performance.
* Fixed preserving "Needs editing" and "Approved" states for ODF files.
* Improved interface for customizing translation-file downloads

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/62?closed=1>`__.

Weblate 4.5
-----------

Released on February 19th 2021.

* Added support for ``lua-format`` used in gettext PO.
* Added support for sharing a component between projects.
* Fixed multiple unnamed variables check behavior with multiple format flags.
* Dropped mailing list field on the project in favor of generic instructions for translators.
* Added pseudolocale generation addon.
* Added support for TermBase eXchange files.
* Added support for manually defining string variants using a flag.
* Improved performance of consistency checks.
* Improved performance of translation memory for long strings.
* Added support for searching in explanations.
* Strings can now be added and removed in bilingual formats as well.
* Extend list of supported languages in Amazon Translate machine translation.
* Automatically enable Java MessageFormat checks for Java Properties.
* Added a new upload method to add new strings to a translation.
* Added a simple interface to browse translation.
* Glossaries are now stored as regular components.
* Dropped specific API for glossaries as component API is used now.
* Added simplified interface to toggle some of the flags.
* Added support for non-translatable or forbidden terms in the glossary.
* Added support for defining terminology in a glossary.
* Moved text direction toggle to get more space for the visual keyboard.
* Added option to automatically watch projects user-contributed to.
* Added check whether translation matches the glossary.
* Added support for customizing navigation text color.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/59?closed=1>`__.

Weblate 4.4.2
-------------

Released on January 14th 2021.

* Fixed corruption of one distributed MO file.

Weblate 4.4.1
-------------

Released on January 13th 2021.

* Fixed reverting plural changes.
* Fixed displaying help for project settings.
* Improved administration of users.
* Improved handling of context in monolingual PO files.
* Fixed cleanup addon behavior with HTML, ODF, IDML and Windows RC formats.
* Fixed parsing of location from CSV files.
* Use content compression for file downloads.
* Improved user experience on importing from ZIP file.
* Improved detection of file format for uploads.
* Avoid duplicate pull requests on Pagure.
* Improved performance when displaying ghost translations.
* Reimplemented translation editor to use native browser textarea.
* Fixed cleanup addon breaking adding new strings.
* Added API for addons.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/60?closed=1>`__.

Weblate 4.4
-----------

Released on December 15th 2020.

* Improved validation when creating a component.
* Weblate now requires Django 3.1.
* Added support for appearance customization in the management interface.
* Fixed read-only state handling in bulk edit.
* Improved CodeMirror integration.
* Added addon to remove blank strings from translation files.
* The CodeMirror editor is now used for translations.
* Syntax highlighting in translation editor for XML, HTML, Markdown and reStructuredText.
* Highlight placeables in translation editor.
* Improved support for non-standard language codes.
* Added alert when using ambiguous language codes.
* The user is now presented with a filtered list of languages when adding a new translation.
* Extended search capabilities for changes in history.
* Improved billing detail pages and libre hosting workflow.
* Extended translation statistics API.
* Improved "other translations" tab while translating.
* Added tasks API.
* Improved performance of file upload.
* Improved display of user defined special characters.
* Improved performance of auto-translation.
* Several minor improvements in the user interface.
* Improved naming of ZIP downloads.
* Added option for getting notifications on unwatched projects.

 `All changes in detail <https://github.com/WeblateOrg/weblate/milestone/56?closed=1>`__.

Weblate 4.3.2
-------------

Released on November 4th 2020.

* Fixed crash on certain component filemasks.
* Improved accuracy of the consecutive duplicated words check.
* Added support for Pagure pull requests.
* Improved error messages for failed registrations.
* Reverted rendering developer comments as Markdown.
* Simplified setup of Git repositories with different default branch than "master".
* Newly created internal repositories now use main as the default branch.
* Reduced false positives rate of unchanged translation while translating reStructuredText.
* Fixed CodeMirror display issues in some situations.
* Renamed Template group to "Sources" to clarify its meaning.
* Fixed GitLab pull requests on repositories with longer paths.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/58?closed=1>`__.

Weblate 4.3.1
-------------

Released on October 21st 2020.

* Improved auto-translation performance.
* Fixed session expiry for authenticated users.
* Add support for hiding version information.
* Improve hooks compatibility with Bitbucket Server.
* Improved performance of translation memory updates.
* Reduced memory usage.
* Improved performance of Matrix view.
* Added confirmation before removing a user from a project.

 `All changes in detail <https://github.com/WeblateOrg/weblate/milestone/57?closed=1>`__.

Weblate 4.3
-----------

Released on October 15th 2020.

* Include user stats in the API.
* Fixed component ordering on paginated pages.
* Define source language for a glossary.
* Rewritten support for GitHub and GitLab pull requests.
* Fixed stats counts after removing suggestion.
* Extended public user profile.
* Fixed configuration of enforced checks.
* Improve documentation about built-in backups.
* Moved source language attribute from project to a component.
* Add Vue I18n formatting check.
* Generic placeholders check now supports regular expressions.
* Improved look of Matrix mode.
* Machinery is now called automatic suggestions.
* Added support for interacting with multiple GitLab or GitHub instances.
* Extended API to cover project updates, unit updates and removals and glossaries.
* Unit API now properly handles plural strings.
* Component creation can now handle ZIP file or document upload.
* Consolidated API response status codes.
* Support Markdown in contributor agreement.
* Improved source strings tracking.
* Improved JSON, YAML and CSV formats compatibility.
* Added support for removing strings.
* Improved performance of file downloads.
* Improved repository management view.
* Automatically enable java-format for Android.
* Added support for localized screenshots.
* Added support for Python 3.9.
* Fixed translating HTML files under certain conditions.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/53?closed=1>`__.

Weblate 4.2.2
-------------

Released on September 2nd 2020.

* Fixed matching of source strings for JSON formats.
* Fixed login redirect for some authentication configurations.
* Fixed LDAP authentication with group sync.
* Fixed crash in reporting automatic translation progress.
* Fixed Git commit squashing with trailers enabled.
* Fixed creating local VCS components using API.

Weblate 4.2.1
-------------

Released on August 21st 2020.

* Fixed saving plurals for some locales in Android resources.
* Fixed crash in the cleanup addon for some XLIFF files.
* Allow setting up localization CDN in Docker image.

Weblate 4.2
-----------

Released on August 18th 2020.

* Improved user pages and added listing of users.
* Dropped support for migrating from 3.x releases, migrate through 4.1 or 4.0.
* Added exports into several monolingual formats.
* Improved activity charts.
* Number of displayed nearby strings can be configured.
* Added support for locking components experiencing repository errors.
* Simplified main navigation (replaced buttons with icons).
* Improved language code handling in Google Translate integration.
* The Git squash addon can generate ``Co-authored-by:`` trailers.
* Improved query search parser.
* Improved user feedback from format strings checks.
* Improved performance of bulk state changes.
* Added compatibility redirects after project or component renaming.
* Added notifications for strings approval, component locking and license change.
* Added support for ModernMT.
* Allow to avoid overwriting approved translations on file upload.
* Dropped support for some compatibility URL redirects.
* Added check for ECMAScript template literals.
* Added option to watch a component.
* Removed leading dot from JSON unit keys.
* Removed separate Celery queue for translation memory.
* Allow translating all components a language at once.
* Allow to configure ``Content-Security-Policy`` HTTP headers.
* Added support for aliasing languages at project level.
* New addon to help with HTML or JavaScript localization, see :ref:`addon-weblate.cdn.cdnjs`.
* The Weblate domain is now configured in the settings, see :setting:`SITE_DOMAIN`.
* Add support for searching by component and project.

Weblate 4.1.1
-------------

Released on June 19th 2020.

* Fixed changing autofix or addons configuration in Docker.
* Fixed possible crash in "About" page.
* Improved installation of byte-compiled locale files.
* Fixed adding words to glossary.
* Fixed keyboard shortcuts for machinery.
* Removed debugging output causing discarding log events in some setups.
* Fixed lock indication on project listing.
* Fixed listing GPG keys in some setups.
* Added option for which DeepL API version to use.
* Added support for acting as SAML Service Provider, see :ref:`saml-auth`.

Weblate 4.1
-----------

Released on June 15th 2020.

* Added support for creating new translations with included country code.
* Added support for searching source strings with screenshot.
* Extended info available in the stats insights.
* Improved search editing on "Translate" pages.
* Improve handling of concurrent repository updates.
* Include source language in project creation form.
* Include changes count in credits.
* Fixed UI language selection in some cases.
* Allow to whitelist registration methods with registrations closed.
* Improved lookup of related terms in glossary.
* Improved translation memory matches.
* Group same machinery results.
* Add direct link to edit screenshot from translate page.
* Improved removal confirmation dialog.
* Include templates in ZIP download.
* Add support for Markdown and notification configuration in announcements.
* Extended details in check listings.
* Added support for new file formats: :ref:`laravel-php`, :ref:`html`, :ref:`odf`, :ref:`idml`, :ref:`winrc`, :ref:`ini`, :ref:`islu`, :ref:`gwt`, :ref:`go-i18n-json`, :ref:`arb`.
* Consistently use dismissed as state of dismissed checks.
* Add support for configuring default addons to enable.
* Fixed editor keyboard shortcut to dismiss checks.
* Improved machine translation of strings with placeholders.
* Show ghost translation for user languages to ease starting them.
* Improved language code parsing.
* Show translations in user language first in the list.
* Renamed shapings to more generic name variants.
* Added new quality checks: :ref:`check-unnamed-format`, :ref:`check-long-untranslated`, :ref:`check-duplicate`.
* Reintroduced support for wiping translation memory.
* Fixed option to ignore source checks.
* Added support for configuring different branch for pushing changes.
* API now reports rate limiting status in the HTTP headers.
* Added support for Google Translate V3 API (Advanced).
* Added ability to restrict access on component level.
* Added support for whitespace and other special chars in translation flags, see :ref:`custom-checks`.
* Always show rendered text check if enabled.
* API now supports filtering of changes.
* Added support for sharing glossaries between projects.

Weblate 4.0.4
-------------

Released on May 07th 2020.

* Fixed testsuite execution on some Python 3.8 environments.
* Typo fixes in the documentation.
* Fixed creating components using API in some cases.
* Fixed JavaScript errors breaking mobile navigation.
* Fixed crash on displaying some checks.
* Fixed screenshots listing.
* Fixed monthly digest notifications.
* Fixed intermediate translation behavior with units non existing in translation.

Weblate 4.0.3
-------------

Released on May 02nd 2020.

* Fixed possible crash in reports.
* User mentions in comments are now case insensitive.
* Fixed PostgreSQL migration for non superusers.
* Fixed changing the repository URL while creating component.
* Fixed crash when upstream repository is gone.

Weblate 4.0.2
-------------

Released on April 27th 2020.

* Improved performance of translation stats.
* Improved performance of changing labels.
* Improved bulk edit performance.
* Improved translation memory performance.
* Fixed possible crash on component deletion.
* Fixed displaying of translation changes in some corner cases.
* Improved warning about too long celery queue.
* Fixed possible false positives in the consistency check.
* Fixed deadlock when changing linked component repository.
* Included edit distance in changes listing and CSV and reports.
* Avoid false positives of punctuation spacing check for Canadian French.
* Fixed XLIFF export with placeholders.
* Fixed false positive with zero width check.
* Improved reporting of configuration errors.
* Fixed bilingual source upload.
* Automatically detect supported languages for DeepL machine translation.
* Fixed progress bar display in some corner cases.
* Fixed some checks triggering on non translated strings.

Weblate 4.0.1
-------------

Released on April 16th 2020.

* Fixed package installation from PyPI.

Weblate 4.0
-----------

Released on April 16th 2020.

* Weblate now requires Python 3.6 or newer.
* Added management overview of component alerts.
* Added component alert for broken repository browser URLs.
* Improved sign in and registration pages.
* Project access control and workflow configuration integrated to project settings.
* Added check and highlighter for i18next interpolation and nesting.
* Added check and highlighter for percent placeholders.
* Display suggestions failing checks.
* Record source string changes in history.
* Upgraded Microsoft Translator to version 3 API.
* Reimplemented translation memory backend.
* Added support for several ``is:`` lookups in :doc:`user/search`.
* Allow to make :ref:`check-same` avoid internal blacklist.
* Improved comments extraction from monolingual po files.
* Renamed whiteboard messages to announcements.
* Fixed occasional problems with registration mails.
* Improved LINGUAS update addon to handle more syntax variants.
* Fixed editing monolingual XLIFF source file.
* Added support for exact matching in :doc:`user/search`.
* Extended API to cover screenshots, users, groups, componentlists and extended creating projects.
* Add support for source upload on bilingual translations.
* Added support for intermediate language from developers.
* Added support for source strings review.
* Extended download options for platform wide translation memory.

Weblate 3.x series
------------------

Weblate 3.11.3
~~~~~~~~~~~~~~

Released on March 11th 2020.

* Fixed searching for fields with certain priority.
* Fixed predefined query for recently added strings.
* Fixed searching returning duplicate matches.
* Fixed notifications rendering in Gmail.
* Fixed reverting changes from the history.
* Added links to events in digest notifications.
* Fixed email for account removal confirmation.
* Added support for Slack authentication in Docker container.
* Avoid sending notifications for not subscribed languages.
* Include Celery queues in performance overview.
* Fixed documentation links for addons.
* Reduced false negatives for unchanged translation check.
* Raised bleach dependency to address CVE-2020-6802.
* Fixed listing project level changes in history.
* Fixed stats invalidation in some corner cases.
* Fixed searching for certain string states.
* Improved format string checks behavior on missing percent.
* Fixed authentication using some third party providers.

Weblate 3.11.2
~~~~~~~~~~~~~~

Released on February 22nd 2020.

* Fixed rendering of suggestions.
* Fixed some strings wrongly reported as having no words.

Weblate 3.11.1
~~~~~~~~~~~~~~

Released on February 20th 2020.

* Documented Celery setup changes.
* Improved filename validation on component creation.
* Fixed minimal versions of some dependencies.
* Fixed adding groups with certain Django versions.
* Fixed manual pushing to upstream repository.
* Improved glossary matching.

Weblate 3.11
~~~~~~~~~~~~

Released on February 17th 2020.

* Allow using VCS push URL during component creation via API.
* Rendered width check now shows image with the render.
* Fixed links in notifications e-mails.
* Improved look of plaintext e-mails.
* Display ignored checks and allow to make them active again.
* Display nearby keys on monolingual translations.
* Added support for grouping string shapings.
* Recommend upgrade to new Weblate versions in the system checks.
* Provide more detailed analysis for duplicate language alert.
* Include more detailed license info on the project pages.
* Automatically unshallow local copies if needed.
* Fixed download of strings needing action.
* New alert to warn about using the same filemask twice.
* Improve XML placeables extraction.
* The :setting:`SINGLE_PROJECT` can now enforce redirection to chosen project.
* Added option to resolve comments.
* Added bulk editing of flags.
* Added support for :ref:`labels`.
* Added bulk edit addon.
* Added option for :ref:`enforcing-checks`.
* Increased default validity of confirmation links.
* Improved Matomo integration.
* Fixed :ref:`check-translated` to correctly handle source string change.
* Extended automatic updates configuration by :setting:`AUTO_UPDATE`.
* LINGUAS addons now do full sync of translations in Weblate.

Weblate 3.10.3
~~~~~~~~~~~~~~

Released on January 18th 2020.

* Support for translate-toolkit 2.5.0.

Weblate 3.10.2
~~~~~~~~~~~~~~

Released on January 18th 2020.

* Add lock indication to projects.
* Fixed CSS bug causing flickering in some web browsers.
* Fixed searching on systems with non-English locales.
* Improved repository matching for GitHub and Bitbucket hooks.
* Fixed data migration on some Python 2.7 installations.
* Allow configuration of Git shallow cloning.
* Improved background notification processing.
* Fixed broken form submission when navigating back in web browser.
* New addon to configure YAML formatting.
* Fixed same plurals check to not fire on single plural form languages.
* Fixed regex search on some fields.

Weblate 3.10.1
~~~~~~~~~~~~~~

Released on January 9th 2020.

* Extended API with translation creation.
* Fixed several corner cases in data migrations.
* Compatibility with Django 3.0.
* Improved data clean-up performance.
* Added support for customizable security.txt.
* Improved breadcrumbs in changelog.
* Improved translations listing on dashboard.
* Improved HTTP responses for webhooks.
* Added support for GitLab merge requests in Docker container.

Weblate 3.10
~~~~~~~~~~~~

Released on December 20th 2019.

* Improved application user interface.
* Added doublespace check.
* Fixed creating new languages.
* Avoid sending auditlog notifications to deleted e-mails.
* Added support for read only strings.
* Added support for Markdown in comments.
* Allow placing translation instruction text in project info.
* Add copy to clipboard for secondary languages.
* Improved support for Mercurial.
* Improved Git repository fetching performance.
* Add search lookup for age of string.
* Show source language for all translations.
* Show context for nearby strings.
* Added support for notifications on repository operations.
* Improved translation listings.
* Extended search capabilities.
* Added support for automatic translation strings marked for editing.
* Avoid sending duplicate notifications for linked component alerts.
* Improve default merge request message.
* Better indicate string state in Zen mode.
* Added support for more languages in Yandex Translate.
* Improved look of notification e-mails.
* Provide choice for translation license.

Weblate 3.9.1
~~~~~~~~~~~~~

Released on October 28th 2019.

* Remove some unneeded files from backups.
* Fixed potential crash in reports.
* Fixed cross database migration failure.
* Added support for force pushing Git repositories.
* Reduced risk of registration token invalidation.
* Fixed account removal hitting rate limiter.
* Added search based on priority.
* Fixed possible crash on adding strings to JSON file.
* Safe HTML check and fixup now honor source string markup.
* Avoid sending notifications to invited and deleted users.
* Fix SSL connection to redis in Celery in Docker container.

Weblate 3.9
~~~~~~~~~~~

Released on October 15th 2019.

* Include Weblate metadata in downloaded files.
* Improved UI for failing checks.
* Indicate missing strings in format checks.
* Separate check for French punctuation spacing.
* Add support for fixing some of quality checks errors.
* Add separate permission to create new projects.
* Extend stats for char counts.
* Improve support for Java style language codes.
* Added new generic check for placeholders.
* Added support for WebExtension JSON placeholders.
* Added support for flat XML format.
* Extended API with project, component and translation removal and creation.
* Added support for Gitea and Gitee webhooks.
* Added new custom regex based check.
* Allow to configure contributing to shared translation memory.
* Added ZIP download for more translation files.
* Make XLIFF standard compliant parsing of maxwidth and font.
* Added new check and fixer for safe HTML markup for translating web applications.
* Add component alert on unsupported configuration.
* Added automatic translation addon to bootstrap translations.
* Extend automatic translation to add suggestions.
* Display addon parameters on overview.
* Sentry is now supported through modern Sentry SDK instead of Raven.
* Changed example settings to be better fit for production environment.
* Added automated backups using BorgBackup.
* Split cleanup addon for RESX to avoid unwanted file updates.
* Added advanced search capabilities.
* Allow users to download their own reports.
* Added localization guide to help configuring components.
* Added support for GitLab merge requests.
* Improved display of repository status.
* Perform automated translation in the background.

Weblate 3.8
~~~~~~~~~~~

Released on August 15th 2019.

* Added support for simplified creating of similar components.
* Added support for parsing translation flags from the XML based file formats.
* Log exceptions into Celery log.
* Improve performance of repository scoped addons.
* Improved look of notification e-mails.
* Fixed password reset behavior.
* Improved performance on most of translation pages.
* Fixed listing of languages not known to Weblate.
* Add support for cloning addons to discovered components.
* Add support for replacing file content with uploaded.
* Add support for translating non VCS based content.
* Added OpenGraph widget image to use on social networks.
* Added support for animated screenshots.
* Improved handling of monolingual XLIFF files.
* Avoid sending multiple notifications for single event.
* Add support for filtering changes.
* Extended predefined periods for reporting.
* Added webhook support for Azure Repos.
* New opt-in notifications on pending suggestions or untranslated strings.
* Add one click unsubscribe link to notification e-mails.
* Fixed false positives with Has been translated check.
* New management interface for admins.
* String priority can now be specified using flags.
* Added language management views.
* Add checks for Qt library and Ruby format strings.
* Added configuration to better fit single project installations.
* Notify about new string on source string change on monolingual translations.
* Added separate view for translation memory with search capability.

Weblate 3.7.1
~~~~~~~~~~~~~

Released on June 28th 2019.

* Documentation updates.
* Fixed some requirements constraints.
* Updated language database.
* Localization updates.
* Various user interface tweaks.
* Improved handling of unsupported but discovered translation files.
* More verbosely report missing file format requirements.

Weblate 3.7
~~~~~~~~~~~

Released on June 21st 2019.

* Added separate Celery queue for notifications.
* Use consistent look with application for API browsing.
* Include approved stats in the reports.
* Report progress when updating translation component.
* Allow to abort running background component update.
* Extend template language for filename manipulations.
* Use templates for editor link and repository browser URL.
* Indicate max length and current characters count when editing translation.
* Improved handling of abbreviations in unchanged translation check.
* Refreshed landing page for new contributors.
* Add support for configuring msgmerge addon.
* Delay opening SMTP connection when sending notifications.
* Improved error logging.
* Allow custom location in MO generating addon.
* Added addons to cleanup old suggestions or comments.
* Added option to enable horizontal mode in the Zen editor.
* Improved import performance with many linked components.
* Fixed examples installation in some cases.
* Improved rendering of alerts in changes.
* Added new horizontal stats widget.
* Improved format strings check on plurals.
* Added font management tool.
* New check for rendered text dimensions.
* Added support for subtitle formats.
* Include overall completion stats for languages.
* Added reporting at project and global scope.
* Improved user interface when showing translation status.
* New Weblate logo and color scheme.
* New look of bitmap badges.

Weblate 3.6.1
~~~~~~~~~~~~~

Released on April 26th 2019.

* Improved handling of monolingual XLIFF files.
* Fixed digest notifications in some corner cases.
* Fixed addon script error alert.
* Fixed generating MO file for monolingual PO files.
* Fixed display of uninstalled checks.
* Indicate administered projects on project listing.
* Allow update to recover from missing VCS repository.

Weblate 3.6
~~~~~~~~~~~

Released on April 20th 2019.

* Add support for downloading user data.
* Addons are now automatically triggered upon installation.
* Improved instructions for resolving merge conflicts.
* Cleanup addon is now compatible with app store metadata translations.
* Configurable language code syntax when adding new translations.
* Warn about using Python 2 with planned termination of support in April 2020.
* Extract special characters from the source string for visual keyboard.
* Extended contributor stats to reflect both source and target counts.
* Admins and consistency addons can now add translations even if disabled for users.
* Fixed description of toggle disabling ``Language-Team`` header manipulation.
* Notify users mentioned in comments.
* Removed file format autodetection from component setup.
* Fixed generating MO file for monolingual PO files.
* Added digest notifications.
* Added support for muting component notifications.
* Added notifications for new alerts, whiteboard messages or components.
* Notifications for administered projects can now be configured.
* Improved handling of three letter language codes.

Weblate 3.5.1
~~~~~~~~~~~~~

Released on March 10th 2019.

* Fixed Celery systemd unit example.
* Fixed notifications from HTTP repositories with login.
* Fixed race condition in editing source string for monolingual translations.
* Include output of failed addon execution in the logs.
* Improved validation of choices for adding new language.
* Allow to edit file format in component settings.
* Update installation instructions to prefer Python 3.
* Performance and consistency improvements for loading translations.
* Make Microsoft Terminology service compatible with current Zeep releases.
* Localization updates.

Weblate 3.5
~~~~~~~~~~~

Released on March 3rd 2019.

* Improved performance of built-in translation memory.
* Added interface to manage global translation memory.
* Improved alerting on bad component state.
* Added user interface to manage whiteboard messages.
* Addon commit message now can be configured.
* Reduce number of commits when updating upstream repository.
* Fixed possible metadata loss when moving component between projects.
* Improved navigation in the Zen mode.
* Added several new quality checks (Markdown related and URL).
* Added support for app store metadata files.
* Added support for toggling GitHub or Gerrit integration.
* Added check for Kashida letters.
* Added option to squash commits based on authors.
* Improved support for XLSX file format.
* Compatibility with Tesseract 4.0.
* Billing addon now removes projects for unpaid billings after 45 days.

Weblate 3.4
~~~~~~~~~~~

Released on January 22nd 2019.

* Added support for XLIFF placeholders.
* Celery can now utilize multiple task queues.
* Added support for renaming and moving projects and components.
* Include characters counts in reports.
* Added guided adding of translation components with automatic detection of translation files.
* Customizable merge commit messages for Git.
* Added visual indication of component alerts in navigation.
* Improved performance of loading translation files.
* New addon to squash commits prior to push.
* Improved displaying of translation changes.
* Changed default merge style to rebase and made that configurable.
* Better handle private use subtags in language code.
* Improved performance of fulltext index updates.
* Extended file upload API to support more parameters.

Weblate 3.3
~~~~~~~~~~~

Released on November 30th 2018.

* Added support for component and project removal.
* Improved performance for some monolingual translations.
* Added translation component alerts to highlight problems with a translation.
* Expose XLIFF string resname as context when available.
* Added support for XLIFF states.
* Added check for non writable files in DATA_DIR.
* Improved CSV export for changes.

Weblate 3.2.2
~~~~~~~~~~~~~

Released on October 20th 2018.

* Remove no longer needed Babel dependency.
* Updated language definitions.
* Improve documentation for addons, LDAP and Celery.
* Fixed enabling new dos-eol and auto-java-messageformat flags.
* Fixed running setup.py test from PyPI package.
* Improved plurals handling.
* Fixed translation upload API failure in some corner cases.
* Fixed updating Git configuration in case it was changed manually.

Weblate 3.2.1
~~~~~~~~~~~~~

Released on October 10th 2018.

* Document dependency on backports.csv on Python 2.7.
* Fix running tests under root.
* Improved error handling in gitexport module.
* Fixed progress reporting for newly added languages.
* Correctly report Celery worker errors to Sentry.
* Fixed creating new translations with Qt Linguist.
* Fixed occasional fulltext index update failures.
* Improved validation when creating new components.
* Added support for cleanup of old suggestions.

Weblate 3.2
~~~~~~~~~~~

Released on October 6th 2018.

* Add install_addon management command for automated addon installation.
* Allow more fine grained ratelimit settings.
* Added support for export and import of Excel files.
* Improve component cleanup in case of multiple component discovery addons.
* Rewritten Microsoft Terminology machine translation backend.
* Weblate now uses Celery to offload some processing.
* Improved search capabilities and added regular expression search.
* Added support for Youdao Zhiyun API machine translation.
* Added support for Baidu API machine translation.
* Integrated maintenance and cleanup tasks using Celery.
* Improved performance of loading translations by almost 25%.
* Removed support for merging headers on upload.
* Removed support for custom commit messages.
* Configurable editing mode (zen/full).
* Added support for error reporting to Sentry.
* Added support for automated daily update of repositories.
* Added support for creating projects and components by users.
* Built-in translation memory now automatically stores translations done.
* Users and projects can import their existing translation memories.
* Better management of related strings for screenshots.
* Added support for checking Java MessageFormat.

See `3.2 milestone on GitHub <https://github.com/WeblateOrg/weblate/milestone/36?closed=1>`_
for detailed list of addressed issues.

Weblate 3.1.1
~~~~~~~~~~~~~

Released on July 27th 2018.

* Fix testsuite failure on some setups.

Weblate 3.1
~~~~~~~~~~~

Released on July 27th 2018.

* Upgrades from older version than 3.0.1 are not supported.
* Allow to override default commit messages from settings.
* Improve webhooks compatibility with self hosted environments.
* Added support for Amazon Translate.
* Compatibility with Django 2.1.
* Django system checks are now used to diagnose problems with installation.
* Removed support for soon shutdown libravatar service.
* New addon to mark unchanged translations as needing edit.
* Add support for jumping to specific location while translating.
* Downloaded translations can now be customized.
* Improved calculation of string similarity in translation memory matches.
* Added support by signing Git commits by GnuPG.

Weblate 3.0.1
~~~~~~~~~~~~~

Released on June 10th 2018.

* Fixed possible migration issue from 2.20.
* Localization updates.
* Removed obsolete hook examples.
* Improved caching documentation.
* Fixed displaying of admin documentation.
* Improved handling of long language names.

Weblate 3.0
~~~~~~~~~~~

Released on June 1st 2018.

* Rewritten access control.
* Several code cleanups that lead to moved and renamed modules.
* New addon for automatic component discovery.
* The import_project management command has now slightly different parameters.
* Added basic support for Windows RC files.
* New addon to store contributor names in PO file headers.
* The per component hook scripts are removed, use addons instead.
* Add support for collecting contributor agreements.
* Access control changes are now tracked in history.
* New addon to ensure all components in a project have same translations.
* Support for more variables in commit message templates.
* Add support for providing additional textual context.

Weblate 2.x series
------------------

Weblate 2.20
~~~~~~~~~~~~

Released on April 4th 2018.

* Improved speed of cloning subversion repositories.
* Changed repository locking to use third party library.
* Added support for downloading only strings needing action.
* Added support for searching in several languages at once.
* New addon to configure gettext output wrapping.
* New addon to configure JSON formatting.
* Added support for authentication in API using RFC 6750 compatible Bearer authentication.
* Added support for automatic translation using machine translation services.
* Added support for HTML markup in whiteboard messages.
* Added support for mass changing state of strings.
* Translate-toolkit at least 2.3.0 is now required, older versions are no longer supported.
* Added built-in translation memory.
* Added componentlists overview to dashboard and per component list overview pages.
* Added support for DeepL machine translation service.
* Machine translation results are now cached inside Weblate.
* Added support for reordering committed changes.

Weblate 2.19.1
~~~~~~~~~~~~~~

Released on February 20th 2018.

* Fixed migration issue on upgrade from 2.18.
* Improved file upload API validation.

Weblate 2.19
~~~~~~~~~~~~

Released on February 15th 2018.

* Fixed imports across some file formats.
* Display human friendly browser information in audit log.
* Added TMX exporter for files.
* Various performance improvements for loading translation files.
* Added option to disable access management in Weblate in favor of Django one.
* Improved glossary lookup speed for large strings.
* Compatibility with django_auth_ldap 1.3.0.
* Configuration errors are now stored and reported persistently.
* Honor ignore flags in whitespace autofixer.
* Improved compatibility with some Subversion setups.
* Improved built-in machine translation service.
* Added support for SAP Translation Hub service.
* Added support for Microsoft Terminology service.
* Removed support for advertisement in notification e-mails.
* Improved translation progress reporting at language level.
* Improved support for different plural formulas.
* Added support for Subversion repositories not using stdlayout.
* Added addons to customize translation workflows.

Weblate 2.18
~~~~~~~~~~~~

Released on December 15th 2017.

* Extended contributor stats.
* Improved configuration of special characters virtual keyboard.
* Added support for DTD file format.
* Changed keyboard shortcuts to less likely collide with browser/system ones.
* Improved support for approved flag in XLIFF files.
* Added support for not wrapping long strings in gettext PO files.
* Added button to copy permalink for current translation.
* Dropped support for Django 1.10 and added support for Django 2.0.
* Removed locking of translations while translating.
* Added support for adding new strings to monolingual translations.
* Added support for translation workflows with dedicated reviewers.

Weblate 2.17.1
~~~~~~~~~~~~~~

Released on October 13th 2017.

* Fixed running testsuite in some specific situations.
* Locales updates.

Weblate 2.17
~~~~~~~~~~~~

Released on October 13th 2017.

* Weblate by default does shallow Git clones now.
* Improved performance when updating large translation files.
* Added support for blocking certain e-mails from registration.
* Users can now delete their own comments.
* Added preview step to search and replace feature.
* Client side persistence of settings in search and upload forms.
* Extended search capabilities.
* More fine grained per project ACL configuration.
* Default value of BASE_DIR has been changed.
* Added two step account removal to prevent accidental removal.
* Project access control settings is now editable.
* Added optional spam protection for suggestions using Akismet.

Weblate 2.16
~~~~~~~~~~~~

Released on August 11th 2017.

* Various performance improvements.
* Added support for nested JSON format.
* Added support for WebExtension JSON format.
* Fixed git exporter authentication.
* Improved CSV import in certain situations.
* Improved look of Other translations widget.
* The max-length checks is now enforcing length of text in form.
* Make the commit_pending age configurable per component.
* Various user interface cleanups.
* Fixed component/project/site wide search for translations.

Weblate 2.15
~~~~~~~~~~~~

Released on June 30th 2017.

* Show more related translations in other translations.
* Add option to see translations of current string to other languages.
* Use 4 plural forms for Lithuanian by default.
* Fixed upload for monolingual files of different format.
* Improved error messages on failed authentication.
* Keep page state when removing word from glossary.
* Added direct link to edit secondary language translation.
* Added Perl format quality check.
* Added support for rejecting reused passwords.
* Extended toolbar for editing RTL languages.

Weblate 2.14.1
~~~~~~~~~~~~~~

Released on May 24th 2017.

* Fixed possible error when paginating search results.
* Fixed migrations from older versions in some corner cases.
* Fixed possible CSRF on project watch and unwatch.
* The password reset no longer authenticates user.
* Fixed possible CAPTCHA bypass on forgotten password.

Weblate 2.14
~~~~~~~~~~~~

Released on May 17th 2017.

* Add glossary entries using AJAX.
* The logout now uses POST to avoid CSRF.
* The API key token reset now uses POST to avoid CSRF.
* Weblate sets Content-Security-Policy by default.
* The local editor URL is validated to avoid self-XSS.
* The password is now validated against common flaws by default.
* Notify users about important activity with their account such as password change.
* The CSV exports now escape potential formulas.
* Various minor improvements in security.
* The authentication attempts are now rate limited.
* Suggestion content is stored in the history.
* Store important account activity in audit log.
* Ask for password confirmation when removing account or adding new associations.
* Show time when suggestion has been made.
* There is new quality check for trailing semicolon.
* Ensure that search links can be shared.
* Included source string information and screenshots in the API.
* Allow to overwrite translations through API upload.

Weblate 2.13.1
~~~~~~~~~~~~~~

Released on Apr 12th 2017.

* Fixed listing of managed projects in profile.
* Fixed migration issue where some permissions were missing.
* Fixed listing of current file format in translation download.
* Return HTTP 404 when trying to access project where user lacks privileges.

Weblate 2.13
~~~~~~~~~~~~

Released on Apr 12th 2017.

* Fixed quality checks on translation templates.
* Added quality check to trigger on losing translation.
* Add option to view pending suggestions from user.
* Add option to automatically build component lists.
* Default dashboard for unauthenticated users can be configured.
* Add option to browse 25 random strings for review.
* History now indicates string change.
* Better error reporting when adding new translation.
* Added per language search within project.
* Group ACLs can now be limited to certain permissions.
* The per project ALCs are now implemented using Group ACL.
* Added more fine grained privileges control.
* Various minor UI improvements.

Weblate 2.12
~~~~~~~~~~~~

Released on Mar 3rd 2017.

* Improved admin interface for groups.
* Added support for Yandex Translate API.
* Improved speed of site wide search.
* Added project and component wide search.
* Added project and component wide search and replace.
* Improved rendering of inconsistent translations.
* Added support for opening source files in local editor.
* Added support for configuring visual keyboard with special characters.
* Improved screenshot management with OCR support for matching source strings.
* Default commit message now includes translation information and URL.
* Added support for Joomla translation format.
* Improved reliability of import across file formats.

Weblate 2.11
~~~~~~~~~~~~

Released on Jan 31st 2017.

* Include language detailed information on language page.
* Mercurial backend improvements.
* Added option to specify translation component priority.
* More consistent usage of Group ACL even with less used permissions.
* Added WL_BRANCH variable to hook scripts.
* Improved developer documentation.
* Better compatibility with various Git versions in Git exporter addon.
* Included per project and component stats.
* Added language code mapping for better support of Microsoft Translate API.
* Moved fulltext cleanup to background job to make translation removal faster.
* Fixed displaying of plural source for languages with single plural form.
* Improved error handling in import_project.
* Various performance improvements.

Weblate 2.10.1
~~~~~~~~~~~~~~

Released on Jan 20th 2017.

* Do not leak account existence on password reset form (CVE-2017-5537).

Weblate 2.10
~~~~~~~~~~~~

Released on Dec 15th 2016.

* Added quality check to check whether plurals are translated differently.
* Fixed GitHub hooks for repositories with authentication.
* Added optional Git exporter module.
* Support for Microsoft Cognitive Services Translator API.
* Simplified project and component user interface.
* Added automatic fix to remove control characters.
* Added per language overview to project.
* Added support for CSV export.
* Added CSV download for stats.
* Added matrix view for quick overview of all translations.
* Added basic API for changes and strings.
* Added support for Apertium APy server for machine translations.

Weblate 2.9
~~~~~~~~~~~

Released on Nov 4th 2016.

* Extended parameters for createadmin management command.
* Extended import_json to be able to handle with existing components.
* Added support for YAML files.
* Project owners can now configure translation component and project details.
* Use "Watched" instead of "Subscribed" projects.
* Projects can be watched directly from project page.
* Added multi language status widget.
* Highlight secondary language if not showing source.
* Record suggestion deletion in history.
* Improved UX of languages selection in profile.
* Fixed showing whiteboard messages for component.
* Keep preferences tab selected after saving.
* Show source string comment more prominently.
* Automatically install Gettext PO merge driver for Git repositories.
* Added search and replace feature.
* Added support for uploading visual context (screenshots) for translations.

Weblate 2.8
~~~~~~~~~~~

Released on Aug 31st 2016.

* Documentation improvements.
* Translations.
* Updated bundled javascript libraries.
* Added list_translators management command.
* Django 1.8 is no longer supported.
* Fixed compatibility with Django 1.10.
* Added Subversion support.
* Separated XML validity check from XML mismatched tags.
* Fixed API to honor HIDE_REPO_CREDENTIALS settings.
* Show source change in Zen mode.
* Alt+PageUp/PageDown/Home/End now works in Zen mode as well.
* Add tooltip showing exact time of changes.
* Add option to select filters and search from translation page.
* Added UI for translation removal.
* Improved behavior when inserting placeables.
* Fixed auto locking issues in Zen mode.

Weblate 2.7
~~~~~~~~~~~

Released on Jul 10th 2016.

* Removed Google web translate machine translation.
* Improved commit message when adding translation.
* Fixed Google Translate API for Hebrew language.
* Compatibility with Mercurial 3.8.
* Added import_json management command.
* Correct ordering of listed translations.
* Show full suggestion text, not only a diff.
* Extend API (detailed repository status, statistics, …).
* Testsuite no longer requires network access to test repositories.

Weblate 2.6
~~~~~~~~~~~

Released on Apr 28th 2016.

* Fixed validation of components with language filter.
* Improved support for XLIFF files.
* Fixed machine translation for non English sources.
* Added REST API.
* Django 1.10 compatibility.
* Added categories to whiteboard messages.

Weblate 2.5
~~~~~~~~~~~

Released on Mar 10th 2016.

* Fixed automatic translation for project owners.
* Improved performance of commit and push operations.
* New management command to add suggestions from command line.
* Added support for merging comments on file upload.
* Added support for some GNU extensions to C printf format.
* Documentation improvements.
* Added support for generating translator credits.
* Added support for generating contributor stats.
* Site wide search can search only in one language.
* Improve quality checks for Armenian.
* Support for starting translation components without existing translations.
* Support for adding new translations in Qt TS.
* Improved support for translating PHP files.
* Performance improvements for quality checks.
* Fixed site wide search for failing checks.
* Added option to specify source language.
* Improved support for XLIFF files.
* Extended list of options for import_project.
* Improved targeting for whiteboard messages.
* Support for automatic translation across projects.
* Optimized fulltext search index.
* Added management command for auto translation.
* Added placeables highlighting.
* Added keyboard shortcuts for placeables, checks and machine translations.
* Improved translation locking.
* Added quality check for AngularJS interpolation.
* Added extensive group based ACLs.
* Clarified terminology on strings needing edit (formerly fuzzy).
* Clarified terminology on strings needing action and not translated strings.
* Support for Python 3.
* Dropped support for Django 1.7.
* Dropped dependency on msginit for creating new gettext PO files.
* Added configurable dashboard views.
* Improved notifications on parse errors.
* Added option to import components with duplicate name to import_project.
* Improved support for translating PHP files.
* Added XLIFF export for dictionary.
* Added XLIFF and gettext PO export for all translations.
* Documentation improvements.
* Added support for configurable automatic group assignments.
* Improved adding of new translations.

Weblate 2.4
~~~~~~~~~~~

Released on Sep 20th 2015.

* Improved support for PHP files.
* Ability to add ACL to anonymous user.
* Improved configurability of import_project command.
* Added CSV dump of history.
* Avoid copy/paste errors with whitespace characters.
* Added support for Bitbucket webhooks.
* Tighter control on fuzzy strings on translation upload.
* Several URLs have changed, you might have to update your bookmarks.
* Hook scripts are executed with VCS root as current directory.
* Hook scripts are executed with environment variables describing current component.
* Add management command to optimize fulltext index.
* Added support for error reporting to Rollbar.
* Projects now can have multiple owners.
* Project owners can manage themselves.
* Added support for ``javascript-format`` used in gettext PO.
* Support for adding new translations in XLIFF.
* Improved file format autodetection.
* Extended keyboard shortcuts.
* Improved dictionary matching for several languages.
* Improved layout of most of pages.
* Support for adding words to dictionary while translating.
* Added support for filtering languages to be managed by Weblate.
* Added support for translating and importing CSV files.
* Rewritten handling of static files.
* Direct login/registration links to third-party service if that's the only one.
* Commit pending changes on account removal.
* Add management command to change site name.
* Add option to configure default committer.
* Add hook after adding new translation.
* Add option to specify multiple files to add to commit.

Weblate 2.3
~~~~~~~~~~~

Released on May 22nd 2015.

* Dropped support for Django 1.6 and South migrations.
* Support for adding new translations when using Java Property files.
* Allow to accept suggestion without editing.
* Improved support for Google OAuth 2.0.
* Added support for Microsoft .resx files.
* Tuned default robots.txt to disallow big crawling of translations.
* Simplified workflow for accepting suggestions.
* Added project owners who always receive important notifications.
* Allow to disable editing of monolingual template.
* More detailed repository status view.
* Direct link for editing template when changing translation.
* Allow to add more permissions to project owners.
* Allow to show secondary language in Zen mode.
* Support for hiding source string in favor of secondary language.

Weblate 2.2
~~~~~~~~~~~

Released on Feb 19th 2015.

* Performance improvements.
* Fulltext search on location and comments fields.
* New SVG/javascript based activity charts.
* Support for Django 1.8.
* Support for deleting comments.
* Added own SVG badge.
* Added support for Google Analytics.
* Improved handling of translation filenames.
* Added support for monolingual JSON translations.
* Record component locking in a history.
* Support for editing source (template) language for monolingual translations.
* Added basic support for Gerrit.

Weblate 2.1
~~~~~~~~~~~

Released on Dec 5th 2014.

* Added support for Mercurial repositories.
* Replaced Glyphicon font by Awesome.
* Added icons for social authentication services.
* Better consistency of button colors and icons.
* Documentation improvements.
* Various bugfixes.
* Automatic hiding of columns in translation listing for small screens.
* Changed configuration of filesystem paths.
* Improved SSH keys handling and storage.
* Improved repository locking.
* Customizable quality checks per source string.
* Allow to hide completed translations from dashboard.

Weblate 2.0
~~~~~~~~~~~

Released on Nov 6th 2014.

* New responsive UI using Bootstrap.
* Rewritten VCS backend.
* Documentation improvements.
* Added whiteboard for site wide messages.
* Configurable strings priority.
* Added support for JSON file format.
* Fixed generating mo files in certain cases.
* Added support for GitLab notifications.
* Added support for disabling translation suggestions.
* Django 1.7 support.
* ACL projects now have user management.
* Extended search possibilities.
* Give more hints to translators about plurals.
* Fixed Git repository locking.
* Compatibility with older Git versions.
* Improved ACL support.
* Added buttons for per language quotes and other special characters.
* Support for exporting stats as JSONP.

Weblate 1.x series
------------------

Weblate 1.9
~~~~~~~~~~~

Released on May 6th 2014.

* Django 1.6 compatibility.
* No longer maintained compatibility with Django 1.4.
* Management commands for locking/unlocking translations.
* Improved support for Qt TS files.
* Users can now delete their account.
* Avatars can be disabled.
* Merged first and last name attributes.
* Avatars are now fetched and cached server side.
* Added support for shields.io badge.

Weblate 1.8
~~~~~~~~~~~

Released on November 7th 2013.

* Please check manual for upgrade instructions.
* Nicer listing of project summary.
* Better visible options for sharing.
* More control over anonymous users privileges.
* Supports login using third party services, check manual for more details.
* Users can login by e-mail instead of username.
* Documentation improvements.
* Improved source strings review.
* Searching across all strings.
* Better tracking of source strings.
* Captcha protection for registration.

Weblate 1.7
~~~~~~~~~~~

Released on October 7th 2013.

* Please check manual for upgrade instructions.
* Support for checking Python brace format string.
* Per component customization of quality checks.
* Detailed per translation stats.
* Changed way of linking suggestions, checks and comments to strings.
* Users can now add text to commit message.
* Support for subscribing on new language requests.
* Support for adding new translations.
* Widgets and charts are now rendered using Pillow instead of Pango + Cairo.
* Add status badge widget.
* Dropped invalid text direction check.
* Changes in dictionary are now logged in history.
* Performance improvements for translating view.

Weblate 1.6
~~~~~~~~~~~

Released on July 25th 2013.

* Nicer error handling on registration.
* Browsing of changes.
* Fixed sorting of machine translation suggestions.
* Improved support for MyMemory machine translation.
* Added support for Amagama machine translation.
* Various optimizations on frequently used pages.
* Highlights searched phrase in search results.
* Support for automatic fixups while saving the message.
* Tracking of translation history and option to revert it.
* Added support for Google Translate API.
* Added support for managing SSH host keys.
* Various form validation improvements.
* Various quality checks improvements.
* Performance improvements for import.
* Added support for voting on suggestions.
* Cleanup of admin interface.

Weblate 1.5
~~~~~~~~~~~

Released on April 16th 2013.

* Please check manual for upgrade instructions.
* Added public user pages.
* Better naming of plural forms.
* Added support for TBX export of glossary.
* Added support for Bitbucket notifications.
* Activity charts are now available for each translation, language or user.
* Extended options of import_project admin command.
* Compatible with Django 1.5.
* Avatars are now shown using libravatar.
* Added possibility to pretty print JSON export.
* Various performance improvements.
* Indicate failing checks or fuzzy strings in progress bars for projects or languages as well.
* Added support for custom pre-commit hooks and committing additional files.
* Rewritten search for better performance and user experience.
* New interface for machine translations.
* Added support for monolingual po files.
* Extend amount of cached metadata to improve speed of various searches.
* Now shows word counts as well.

Weblate 1.4
~~~~~~~~~~~

Released on January 23rd 2013.

* Fixed deleting of checks/comments on string deletion.
* Added option to disable automatic propagation of translations.
* Added option to subscribe for merge failures.
* Correctly import on projects which needs custom ttkit loader.
* Added sitemaps to allow easier access by crawlers.
* Provide direct links to string in notification e-mails or feeds.
* Various improvements to admin interface.
* Provide hints for production setup in admin interface.
* Added per language widgets and engage page.
* Improved translation locking handling.
* Show code snippets for widgets in more variants.
* Indicate failing checks or fuzzy strings in progress bars.
* More options for formatting commit message.
* Fixed error handling with machine translation services.
* Improved automatic translation locking behaviour.
* Support for showing changes from previous source string.
* Added support for substring search.
* Various quality checks improvements.
* Support for per project ACL.
* Basic code coverage by unit tests.

Weblate 1.3
~~~~~~~~~~~

Released on November 16th 2012.

* Compatibility with PostgreSQL database backend.
* Removes languages removed in upstream git repository.
* Improved quality checks processing.
* Added new checks (BB code, XML markup and newlines).
* Support for optional rebasing instead of merge.
* Possibility to relocate Weblate (for example to run it under /weblate path).
* Support for manually choosing file type in case autodetection fails.
* Better support for Android resources.
* Support for generating SSH key from web interface.
* More visible data exports.
* New buttons to enter some special characters.
* Support for exporting dictionary.
* Support for locking down whole Weblate installation.
* Checks for source strings and support for source strings review.
* Support for user comments for both translations and source strings.
* Better changes log tracking.
* Changes can now be monitored using RSS.
* Improved support for RTL languages.

Weblate 1.2
~~~~~~~~~~~

Released on August 14th 2012.

* Weblate now uses South for database migration, please check upgrade instructions if you are upgrading.
* Fixed minor issues with linked git repos.
* New introduction page for engaging people with translating using Weblate.
* Added widgets which can be used for promoting translation projects.
* Added option to reset repository to origin (for privileged users).
* Project or component can now be locked for translations.
* Possibility to disable some translations.
* Configurable options for adding new translations.
* Configuration of git commits per project.
* Simple antispam protection.
* Better layout of main page.
* Support for automatically pushing changes on every commit.
* Support for e-mail notifications of translators.
* List only used languages in preferences.
* Improved handling of not known languages when importing project.
* Support for locking translation by translator.
* Optionally maintain ``Language-Team`` header in po file.
* Include some statistics in about page.
* Supports (and requires) django-registration 0.8.
* Caching counts of strings with failing checks.
* Checking of requirements during setup.
* Documentation improvements.

Weblate 1.1
~~~~~~~~~~~

Released on July 4th 2012.

* Improved several translations.
* Better validation while creating component.
* Added support for shared git repositories across components.
* Do not necessary commit on every attempt to pull remote repo.
* Added support for offloading indexing.

Weblate 1.0
~~~~~~~~~~~

Released on May 10th 2012.

* Improved validation while adding/saving component.
* Experimental support for Android component files (needs patched ttkit).
* Updates from hooks are run in background.
* Improved installation instructions.
* Improved navigation in dictionary.

Weblate 0.x series
------------------

Weblate 0.9
~~~~~~~~~~~

Released on April 18th 2012.

* Fixed import of unknown languages.
* Improved listing of nearby messages.
* Improved several checks.
* Documentation updates.
* Added definition for several more languages.
* Various code cleanups.
* Documentation improvements.
* Changed file layout.
* Update helper scripts to Django 1.4.
* Improved navigation while translating.
* Better handling of po file renames.
* Better validation while creating component.
* Integrated full setup into syncdb.
* Added list of recent changes to all translation pages.
* Check for not translated strings ignores format string only messages.

Weblate 0.8
~~~~~~~~~~~

Released on April 3rd 2012.

* Replaced own full text search with Whoosh.
* Various fixes and improvements to checks.
* New command updatechecks.
* Lot of translation updates.
* Added dictionary for storing most frequently used terms.
* Added /admin/report/ for overview of repositories status.
* Machine translation services no longer block page loading.
* Management interface now contains also useful actions to update data.
* Records log of changes made by users.
* Ability to postpone commit to Git to generate less commits from single user.
* Possibility to browse failing checks.
* Automatic translation using already translated strings.
* New about page showing used versions.
* Django 1.4 compatibility.
* Ability to push changes to remote repo from web interface.
* Added review of translations done by others.

Weblate 0.7
~~~~~~~~~~~

Released on February 16th 2012.

* Direct support for GitHub notifications.
* Added support for cleaning up orphaned checks and translations.
* Displays nearby strings while translating.
* Displays similar strings while translating.
* Improved searching for string.

Weblate 0.6
~~~~~~~~~~~

Released on February 14th 2012.

* Added various checks for translated messages.
* Tunable access control.
* Improved handling of translations with new lines.
* Added client side sorting of tables.
* Please check upgrading instructions in case you are upgrading.

Weblate 0.5
~~~~~~~~~~~

Released on February 12th 2012.

* Support for machine translation using following online services:
    * Apertium
    * Microsoft Translator
    * MyMemory
* Several new translations.
* Improved merging of upstream changes.
* Better handle concurrent git pull and translation.
* Propagating works for fuzzy changes as well.
* Propagating works also for file upload.
* Fixed file downloads while using FastCGI (and possibly others).

Weblate 0.4
~~~~~~~~~~~

Released on February 8th 2012.

* Added usage guide to documentation.
* Fixed API hooks not to require CSRF protection.

Weblate 0.3
~~~~~~~~~~~

Released on February 8th 2012.

* Better display of source for plural translations.
* New documentation in Sphinx format.
* Displays secondary languages while translating.
* Improved error page to give list of existing projects.
* New per language stats.

Weblate 0.2
~~~~~~~~~~~

Released on February 7th 2012.

* Improved validation of several forms.
* Warn users on profile upgrade.
* Remember URL for login.
* Naming of text areas while entering plural forms.
* Automatic expanding of translation area.

Weblate 0.1
~~~~~~~~~~~

Released on February 6th 2012.

* Initial release.
