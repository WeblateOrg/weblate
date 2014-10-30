Changes
=======

weblate 2.0
-----------

Released on ? 2014.

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
* Per resource customization of quality checks.
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
* Project or resource can now be locked for translations.
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
* Better validation while creating resource.
* Added support for shared git repositories across resources.
* Do not necessary commit on every attempt to pull remote repo.
* Added support for offloading indexing.

weblate 1.0
-----------

Released on May 10th 2012.

* Improved validation while adding/saving resource.
* Experimental support for Android resource files (needs patched ttkit).
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
* Better validation while creating resource.
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
