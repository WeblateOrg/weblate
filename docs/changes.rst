Changes
=======

weblate 1.1
-----------

Relased on ? 2012.

weblate 1.0
-----------

Relased on May 10th 2012.

* Improved validation while adding/saving subproject.
* Experimental support for Android resource files (needs patched ttkit).
* Updates from hooks are run in background.
* Improved installation instructions.
* Improved navigation in dictionary.

weblate 0.9
-----------

Relased on April 18th 2012.

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
* Better validation while creating subproject.
* Integrated full setup into syncdb.
* Added list of recent changes to all translation pages.
* Check for not translated strings ignores format string only messages.

weblate 0.8
-----------

Relased on April 3rd 2012.

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

Relased on February 16th 2012.

* Direct support for GitHub notifications.
* Added support for cleaning up orphaned checks and translations.
* Displays nearby strings while translating.
* Displays similar strings while translating.
* Improved searching for string.

weblate 0.6
-----------

Relased on February 14th 2012.

* Added various checks for translated messages.
* Tunable access control.
* Improved handling of translations with new lines.
* Added client side sorting of tables.
* Please check upgrading instructions in case you are upgrading.

weblate 0.5
-----------

Relased on February 12th 2012.

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

Relased on February 8th 2012.

* Added usage guide to documentation.
* Fixed API hooks not to require CSRF protection.

weblate 0.3
-----------

Relased on February 8th 2012.

* Better display of source for plural translations.
* New documentation in Sphinx format.
* Displays secondary languages while translating.
* Improved error page to give list of existing projects.
* New per language stats.

weblate 0.2
-----------

Relased on February 7th 2012.

* Improved validation of several forms.
* Warn users on profile upgrade.
* Remember URL for login.
* Naming of text areas while entering plural forms.
* Automatic expanding of translation area.

weblate 0.1
-----------

Relased on February 6th 2012.

* Initial release.
