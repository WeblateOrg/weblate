Weblate 5.0
-----------

Not yet released.

**New features**

**Improvements**

* Plurals handling in machine translation.
* :ref:`check-same` check now honors placeholders even in the strict mode.
* :ref:`check-reused` is no longer triggered for languages with a single plural form.
* WebP is now supported for :ref:`screenshots`.
* Avoid duplicate notification when a user is subscribed to overlapping scopes.
* Improved OCR support for non-English languages in :ref:`screenshots`.
* :ref:`xliff` now supports displaying source string location.

**Bug fixes**

* User names handling while committing to Git.
* :ref:`addon-weblate.cleanup.blank` and :ref:`addon-weblate.cleanup.generic` now remove all strings at once.
* Language filtering in :doc:`/devel/reporting`.

**Compatibility**

* Python 3.9 or newer is now required.

**Upgrading**

Please follow :ref:`generic-upgrade-instructions` in order to perform update.

* There are several changes in :file:`settings_example.py`, most notable is change in ``CACHES``, please adjust your settings accordingly.
* Several previously optional dependencies are now required.

`All changes in detail <https://github.com/WeblateOrg/weblate/milestone/99?closed=1>`__.
