Machine translation
===================

.. _machine-translation-setup:

Machine translation setup
-------------------------

Weblate has builtin support for several machine translation services and it's
up to administrator to enable them. The services have different terms of use, so
please check whether you are allowed to use them before enabling in Weblate.
The individual services are enabled using :setting:`MACHINE_TRANSLATION_SERVICES`.

The source langauge can be configured by :setting:`SOURCE_LANGUAGE` and is
shared for all translations within Weblate.

Amagama
+++++++

Special installation of :ref:`tmserver` run by Virtaal authors.

To enable this service, add ``trans.machine.tmserver.AmagamaTranslation`` to
:setting:`MACHINE_TRANSLATION_SERVICES`.

.. seealso:: http://docs.translatehouse.org/projects/virtaal/en/latest/amagama.html

.. _apertium:

Apertium
++++++++

A free/open-source machine translation platform providing translation to
limited set of languages.

You should get API key from them, otherwise number of requests is rate limited.

To enable this service, add ``trans.machine.apertium.ApertiumTranslation`` to
:setting:`MACHINE_TRANSLATION_SERVICES`.

.. seealso::

    :setting:`MT_APERTIUM_KEY`, https://www.apertium.org/

Glosbe
++++++

Free dictionary and translation memory for almost every living language.

API is free to use, regarding indicated data source license. There is a limit
of call that may be done from one IP in fixed period of time, to prevent from
abuse.

To enable this service, add ``trans.machine.glosbe.GlosbeTranslation`` to
:setting:`MACHINE_TRANSLATION_SERVICES`.

.. seealso::

    https://glosbe.com/

.. _google-translate:

Google Translate
++++++++++++++++

Machine translation service provided by Google.

This service uses Translation API and you need to obtain API key and enable
billing on Google API console.

To enable this service, add ``trans.machine.google.GoogleTranslation`` to
:setting:`MACHINE_TRANSLATION_SERVICES`.

.. seealso::

    :setting:`MT_GOOGLE_KEY`,
    https://cloud.google.com/translate/docs

Google Web Translate
++++++++++++++++++++

Machine translation service provided by Google.

Please note that this does not use official Translation API but rather web
based translation interface.

To enable this service, add ``trans.machine.google.GoogleWebTranslation`` to
:setting:`MACHINE_TRANSLATION_SERVICES`.

.. seealso::

    https://translate.google.com/

.. _ms-translate:

Microsoft Translator
++++++++++++++++++++

Machine translation service provided by Microsoft.

You need to register at Azure market and use Client ID and secret from there.

To enable this service, add ``trans.machine.microsoft.MicrosoftTranslation`` to
:setting:`MACHINE_TRANSLATION_SERVICES`.

.. seealso::

    :setting:`MT_MICROSOFT_ID`, :setting:`MT_MICROSOFT_SECRET`, 
    http://www.bing.com/translator/,
    https://datamarket.azure.com/developer/applications/

.. _mymemory:

MyMemory
++++++++

Huge translation memory with machine translation.

Free, anonymous usage is currently limited to 100 requests/day, or to 1000
requests/day when you provide contact email in :setting:`MT_MYMEMORY_EMAIL`.
you can also ask them for more.

To enable this service, add ``trans.machine.mymemory.MyMemoryTranslation`` to
:setting:`MACHINE_TRANSLATION_SERVICES`.

.. seealso::

    :setting:`MT_MYMEMORY_EMAIL`,
    :setting:`MT_MYMEMORY_USER`,
    :setting:`MT_MYMEMORY_KEY`,
    http://mymemory.translated.net/

.. _tmserver:

tmserver
++++++++

You can run your own translation memory server which is bundled with
Translate-toolkit and let Weblate talk to it. You can also use it with 
amaGama server, which is enhanced version of tmserver.

First you will want to import some data to the translation memory:

To enable this service, add ``trans.machine.tmserver.TMServerTranslation`` to
:setting:`MACHINE_TRANSLATION_SERVICES`.

.. code-block:: sh

    build_tmdb -d /var/lib/tm/db -s en -t cs locale/cs/LC_MESSAGES/django.po
    build_tmdb -d /var/lib/tm/db -s en -t de locale/de/LC_MESSAGES/django.po
    build_tmdb -d /var/lib/tm/db -s en -t fr locale/fr/LC_MESSAGES/django.po

Now you can start tmserver to listen to your requests:

.. code-block:: sh

    tmserver -d /var/lib/tm/db

And configure Weblate to talk to it:

.. code-block:: python

    MT_TMSERVER = 'http://localhost:8888/'

.. seealso::

    :setting:`MT_TMSERVER`, 
    http://docs.translatehouse.org/projects/translate-toolkit/en/latest/commands/tmserver.html, 
    http://amagama.translatehouse.org/

Weblate
+++++++

Weblate can be source of machine translation as well. There are two services to
provide you results - one does exact search for string, the other one finds all
similar strings.

First one is useful for full string translations, the second one for finding
individual phrases or words to keep the translation consistent.

To enable these services, add
``trans.machine.weblatetm.WeblateSimilarTranslation`` (for similar string
matching) and/or ``trans.machine.weblatetm.WeblateTranslation`` (for exact
string matching) to :setting:`MACHINE_TRANSLATION_SERVICES`.

.. note:: 

    For similarity matching, it is recommended to have Whoosh 2.5.2 or later,
    earlier versions can cause infinite looks under some occasions.

Custom machine translation
--------------------------

You can also implement own machine translation services using few lines of
Python code. Following example implements translation to fixed list of
languages using ``dictionary`` Python module:

.. literalinclude:: ../../examples/mt_service.py
    :language: python

You can list own class in :setting:`MACHINE_TRANSLATION_SERVICES` and Weblate
will start using that.
