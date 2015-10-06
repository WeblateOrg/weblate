.. _languages:

Language definitions
====================

In order to properly present different translation Weblate needs to know some
information about used languages. Currently it comes with definitions for
about 200 languages and the definition include language name, text direction,
plural definitions and language code.

Parsing language codes
----------------------

While parsing translations, Weblate attempts to map language code (usually ISO
639-1 one) to existing language object. If it can not find exact match, it
tries to find best fit in existing languages (eg. it ignores default country
code for given language - choosing ``cs`` instead of ``cs_CZ``). Should this
fail as well, it will create new language definition using the defaults (left
to right text direction, one plural) and naming the language 
:guilabel:``xx_XX (generated)``. You might want to change this in the admin
interface (see :ref:`changing-languages`) and report it to our issue tracker
(see :ref:`contributing`).

.. _changing-languages:

Changing language defintions
----------------------------

You can change language definitions in the admin interface (see
:ref:`admin-interface`). The :guilabel:`Weblate languages` section 
allows you to change or add language definitions. While editing make sure that
all fields are correct (especially plurals and text direction), otherwise the
translators won't be able to properly edit those translations.
