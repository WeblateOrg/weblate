.. _appstore:

App store metadata files
------------------------

Metadata used for publishing apps in various app stores can be translated.
Currently the following tools are compatible:

* `Triple-T gradle-play-publisher <https://github.com/Triple-T/gradle-play-publisher>`_
* `Fastlane <https://docs.fastlane.tools/getting-started/android/setup/#fetch-your-app-metadata>`_
* `F-Droid <https://f-droid.org/docs/All_About_Descriptions_Graphics_and_Screenshots/>`_

The metadata consists of several textfiles, which Weblate will present as
separate strings to translate.

.. hint::

   In case you don't want to translate certain strings (for example
   changelogs), mark them read-only (see :ref:`custom-checks`). This can be
   automated by the :ref:`addon-weblate.flags.bulk`.

Weblate configuration
+++++++++++++++++++++

+--------------------------------+-------------------------------------+
| Typical Weblate :ref:`component`                                     |
+================================+=====================================+
| File mask                      | ``fastlane/metadata/android/*``     |
+--------------------------------+-------------------------------------+
| Monolingual base language file | ``fastlane/metadata/android/en-US`` |
+--------------------------------+-------------------------------------+
| Template for new translations  | ``fastlane/metadata/android/en-US`` |
+--------------------------------+-------------------------------------+
| File format                    | `App store metadata files`          |
+--------------------------------+-------------------------------------+
