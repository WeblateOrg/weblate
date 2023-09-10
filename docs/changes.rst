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
* The default value of :setting::`IP_PROXY_OFFSET` has been changed from 1 to -1.

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
