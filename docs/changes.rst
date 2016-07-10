Changes
=======

weblate 2.7
-----------

Released on Jul 10th 2016.

* Removed Google web translate machine translation.
* Improved commit message when adding translation.
* Fixed Google Translate API for Hebrew language.
* Compatibility with Mercurial 3.8.
* Added import_json management command.
* Correct ordering of listed traslations.
* Show full suggestion text, not only a diff.
* Extend API (detailed repository status, statistics, ...).
* Testsuite no longer requires network access to test repositories.

weblate 2.6
-----------

Released on Apr 28th 2016.

* Fixed validation of subprojects with language filter.
* Improved support for XLIFF files.
* Fixed machine translation for non English sources.
* Added REST API.
* Django 1.10 compatibility.
* Added categories to whiteboard messages.

weblate 2.5
-----------

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
* Support for adding new transations in Qt TS.
* Improved support for translating PHP files.
* Performance improvements for quality checks.
* Fixed sitewide search for failing checks.
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
* Clarified terminology on strings needing review (formerly fuzzy).
* Clarified terminology on strings needing action and not translated strings.
* Support for Python 3.
* Dropped support for Django 1.7.
* Dropped dependency on msginit for creating new Gettext po files.
* Added configurable dashboard views.
* Improved notifications on parse erorrs.
* Added option to import components with duplicate name to import_project.
* Improved support for translating PHP files
* Added XLIFF export for dictionary.
* Added XLIFF and Gettext PO export for all translations.
* Documentation improvements.
* Added support for configurable automatic group assignments.
* Improved adding of new translations.

weblate 2.4
-----------

Released on Sep 20th 2015.

* Improved support for PHP files.
* Ability to add ACL to anonymous user.
* Improved configurability of import_project command.
* Added CSV dump of history.
* Avoid copy/paste errors with whitespace chars.
* Added support for Bitbucket webhooks.
* Tigher control on fuzzy strings on translation upload.
* Several URLs have changed, you might have to update your bookmarks.
* Hook scripts are executed with VCS root as current directory.
* Hook scripts are executed with environment variables descriping current component.
* Add management command to optimize fulltext index.
* Added support for error reporting to Rollbar.
* Projects now can have multiple owners.
* Project owners can manage themselves.
* Added support for javascript-format used in Gettext PO.
* Support for adding new translations in XLIFF.
* Improved file format autodetection.
* Extended keyboard shortcuts.
* Improved dictionary matching for several languages.
* Improved layout of most of pages.
* Support for adding words to dictionary while translating.
* Added support for filtering languages to be managed by Weblate.
* Added support for translating and importing CSV files.
* Rewritten handling of static files.
* Direct login/registration links to third party service if that's the only one.
* Commit pending changes on account removal.
* Add management command to change site name.
* Add option to confiugure default committer.
* Add hook after adding new translation.
* Add option to specify multiple files to add to commit.

weblate 2.3
-----------

Released on May 22nd 2015.

* Dropped support for Django 1.6 and South migrations.
* Support for adding new translations when using Java Property files
* Allow to accept suggestion without editing.
* Improved support for Google OAuth2.
* Added support for Microsoft .resx files.
* Tuned default robots.txt to disallow big crawling of translations.
* Simplified workflow for accepting suggestions.
* Added project owners who always receive important notifications.
* Allow to disable editing of monolingual template.
* More detailed repository status view.
* Direct link for editing template when changing translation.
* Allow to add more permissions to project owners.
* Allow to show secondary language in zen mode.
* Support for hiding source string in favor of secondary language.

weblate 2.2
-----------

Released on Feb 19th 2015.

* Performance improvements.
* Fulltext search on location and comments fields.
* New SVG/javascript based activity charts.
* Support for Django 1.8.
* Support for deleting comments.
* Added own SVG badge.
* Added support for Google Analytics.
* Improved handling of translation file names.
* Added support for monolingual JSON translations.
* Record component locking in a history.
* Support for editing source (template) language for monolingual translations.
* Added basic support for Gerrit.

weblate 2.1
-----------

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

weblate 2.0
-----------

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
* Extended search possibilites.
* Give more hints to translators about plurals.
* Fixed Git repository locking.
* Compatibility with older Git versions.
* Improved ACL support.
* Added buttons for per language quotes and other special chars.
* Support for exporting stats as JSONP.

weblate 1.9
-----------

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

weblate 1.8
-----------

Released on November 7th 2013.

* Please check manual for upgrade instructions.
* Nicer listing of project summary.
* Better visible options for sharing.
* More control over anonymous users privileges.
* Supports login using third party services, check manual for more details.
* Users can login by email instead of username.
* Documentation improvements.
* Improved source strings review.
* Searching across all units.
* Better tracking of source strings.
* Captcha protection for registration.

weblate 1.7
-----------

Released on October 7th 2013.

* Please check manual for upgrade instructions.
* Support for checking Python brace format string.
* Per component customization of quality checks.
* Detailed per translation stats.
* Changed way of linking suggestions, checks and comments to units.
* Users can now add text to commit message.
* Support for subscribing on new language requests.
* Support for adding new translations.
* Widgets and charts are now rendered using Pillow instead of Pango + Cairo.
* Add status badge widget.
* Dropped invalid text direction check.
* Changes in dictionary are now logged in history.
* Performance improvements for translating view.

weblate 1.6
-----------

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

weblate 1.5
-----------

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
* Added support for custom pre-commit hooks and commiting additional files.
* Rewritten search for better performance and user experience.
* New interface for machine translations.
* Added support for monolingual po files.
* Extend amount of cached metadata to improve speed of various searches.
* Now shows word counts as well.

weblate 1.4
-----------

Released on January 23rd 2013.

* Fixed deleting of checks/comments on unit deletion.
* Added option to disable automatic propagation of translations.
* Added option to subscribe for merge failures.
* Correctly import on projects which needs custom ttkit loader.
* Added sitemaps to allow easier access by crawlers.
* Provide direct links to string in notification emails or feeds.
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
* Basic unit tests coverage.

weblate 1.3
-----------

Released on November 16th 2012.

* Compatibility with PostgreSQL database backend.
* Removes languages removed in upstream git repository.
* Improved quality checks processing.
* Added new checks (BB code, XML markup and newlines).
* Support for optional rebasing instead of merge.
* Possibility to relocate Weblate (eg. to run it under /weblate path).
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

weblate 1.2
-----------

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
* Support for email notifications of translators.
* List only used languages in preferences.
* Improved handling of not known languages when importing project.
* Support for locking translation by translator.
* Optionally maintain Language-Team header in po file.
* Include some statistics in about page.
* Supports (and requires) django-registration 0.8.
* Caching of counted units with failing checks.
* Checking of requirements during setup.
* Documentation improvements.

weblate 1.1
-----------

Released on July 4th 2012.

* Improved several translations.
* Better validation while creating component.
* Added support for shared git repositories across components.
* Do not necessary commit on every attempt to pull remote repo.
* Added support for offloading indexing.

weblate 1.0
-----------

Released on May 10th 2012.

* Improved validation while adding/saving component.
* Experimental support for Android component files (needs patched ttkit).
* Updates from hooks are run in background.
* Improved installation instructions.
* Improved navigation in dictionary.

weblate 0.9
-----------

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

weblate 0.8
-----------

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

weblate 0.7
-----------

Released on February 16th 2012.

* Direct support for GitHub notifications.
* Added support for cleaning up orphaned checks and translations.
* Displays nearby strings while translating.
* Displays similar strings while translating.
* Improved searching for string.

weblate 0.6
-----------

Released on February 14th 2012.

* Added various checks for translated messages.
* Tunable access control.
* Improved handling of translations with new lines.
* Added client side sorting of tables.
* Please check upgrading instructions in case you are upgrading.

weblate 0.5
-----------

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

weblate 0.4
-----------

Released on February 8th 2012.

* Added usage guide to documentation.
* Fixed API hooks not to require CSRF protection.

weblate 0.3
-----------

Released on February 8th 2012.

* Better display of source for plural translations.
* New documentation in Sphinx format.
* Displays secondary languages while translating.
* Improved error page to give list of existing projects.
* New per language stats.

weblate 0.2
-----------

Released on February 7th 2012.

* Improved validation of several forms.
* Warn users on profile upgrade.
* Remember URL for login.
* Naming of text areas while entering plural forms.
* Automatic expanding of translation area.

weblate 0.1
-----------

Released on February 6th 2012.

* Initial release.
