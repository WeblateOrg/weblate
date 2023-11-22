Weblate 5.2.1
-------------

Released on November 22nd 2023.

**Improvements**

* Show search field after no strings found while translating.

**Bug fixes**

* Database backups compatibility with Alibaba Cloud Database PolarDB.
* Crash on loading statistics calculated by previous versions.
* Sort icons in dark mode.

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

* Added plurals validation when editing string using API.
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
* Performace issues while browsing some categories.
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
