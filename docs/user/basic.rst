Weblate basics
==============

Project structure
------------------

In Weblate translations are organized into projects and components. Each project
can contain number of components and those contain translations into individual
languages. The component corresponds to one translatable file (for example
:ref:`gettext` or :ref:`aresource`). The projects are there to help you
organize component into logical sets (for example to group all translations
used within one application).

Internally, each project has translations to common strings propagated across
other components within it by default.  This lightens the burden of repetitive
and multi version translation.  Disable it as per :ref:`component`, still
producing errors for seemingly inconsistent resulting translations.
