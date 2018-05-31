.. _machine-translation-setup:

Machine translation
===================

Weblate has built in support for several machine translation services and it's
up to the administrator to enable them. The services have different terms of use, so
please check whether you are allowed to use them before enabling them in Weblate.
The individual services are enabled using :setting:`MT_SERVICES`.

The source language can be configured at :ref:`project`.

Amagama
-------

Special installation of :ref:`tmserver` run by Virtaal authors.

To enable this service, add ``weblate.machinery.tmserver.AmagamaTranslation`` to
:setting:`MT_SERVICES`.

.. seealso:: 
   
    `Amagama Translation Memory server <http://docs.translatehouse.org/projects/virtaal/en/latest/amagama.html>`_
    `Amagama Translation Memory <http://amagama.translatehouse.org/>`_

.. _apertium:

Apertium
--------

A free/open-source machine translation platform providing translation to
a limited set of languages.

The recommended way to use Apertium is to run your own Apertium APy server.

To enable this service, add ``weblate.machinery.apertium.ApertiumAPYTranslation`` to
:setting:`MT_SERVICES` and set :setting:`MT_APERTIUM_APY`.

.. seealso::

    :setting:`MT_APERTIUM_APY`, `Apertium website <https://www.apertium.org/>`_,
    `Apertium APy documentation <http://wiki.apertium.org/wiki/Apertium-apy>`_

.. _deepl:

DeepL
-----

.. versionadded:: 2.20

DeepL is paid service providing good machine translation for few languages.
According to some benchmark it's currently best available service.

To enable this service, add ``weblate.machinery.deepl.DeepLTranslation`` to
:setting:`MT_SERVICES` and set :setting:`MT_DEEPL_KEY`.

.. seealso::

    :setting:`MT_DEEPL_KEY`, `DeepL website <https://www.deepl.com/>`_,
    `DeepL API documentation <https://www.deepl.com/api.html>`_


.. _glosbe:

Glosbe
------

Free dictionary and translation memory for almost every living language.

API is free to use, but subject to the used data source license. There is a limit
of calls that may be done from one IP in fixed period of time, to prevent
abuse.

To enable this service, add ``weblate.machinery.glosbe.GlosbeTranslation`` to
:setting:`MT_SERVICES`.

.. seealso::

    `Glosbe website <https://glosbe.com/>`_

.. _google-translate:

Google Translate
----------------

Machine translation service provided by Google.

This service uses Translation API and you need to obtain an API key and enable
billing on Google API console.

To enable this service, add ``weblate.machinery.google.GoogleTranslation`` to
:setting:`MT_SERVICES` and set :setting:`MT_GOOGLE_KEY`.

.. seealso::

    :setting:`MT_GOOGLE_KEY`,
    `Google translate documentation <https://cloud.google.com/translate/docs>`_

.. _ms-translate:

Microsoft Translator
--------------------

.. deprecated:: 2.10

.. note::

    This service is deprecated by Microsoft and has been replaced by
    :ref:`ms-cognitive-translate`.

Machine translation service provided by Microsoft, it's known as Bing Translator as well.

You need to register at Azure market and use Client ID and secret from there.

To enable this service, add ``weblate.machinery.microsoft.MicrosoftTranslation`` to
:setting:`MT_SERVICES`.

.. seealso::

    :setting:`MT_MICROSOFT_ID`, :setting:`MT_MICROSOFT_SECRET`,
    `Bing Translator <https://www.bing.com/translator/>`_,
    `Azure datamarket <https://datamarket.azure.com/developer/applications/>`_

.. _ms-cognitive-translate:

Microsoft Cognitive Services Translator
---------------------------------------

.. versionadded:: 2.10

.. note::

    This is replacement service for :ref:`ms-translate`.

Machine transation service provided by Microsoft in Azure portal as a one of
Cognitive Services.

You need to register at Azure portal and use the key you obtain there.

To enable this service, add ``weblate.machinery.microsoft.MicrosoftCognitiveTranslation`` to
:setting:`MT_SERVICES` and set :setting:`MT_MICROSOFT_COGNITIVE_KEY`.

.. seealso::
    
    :setting:`MT_MICROSOFT_COGNITIVE_KEY`,
    `Cognitive Services - Text Translation API <http://docs.microsofttranslator.com/text-translate.html>`_,
    `Microsoft Azure Portal <https://portal.azure.com/>`_

.. _ms-terminology:

Microsoft Terminology Service
-----------------------------

.. versionadded:: 2.19

The Microsoft Terminology Service API allows you to programmatically access the
terminology, definitions and user interface (UI) strings available on the
Language Portal through a web service.

To enable this service, add ``weblate.machinery.microsoft.MicrosoftTerminologyService`` to
:setting:`MT_SERVICES`.

.. seealso::

    `Microsoft Terminology Service API <https://www.microsoft.com/en-us/language/Microsoft-Terminology-API>`_

.. _mymemory:

MyMemory
--------

Huge translation memory with machine translation.

Free, anonymous usage is currently limited to 100 requests/day, or to 1000
requests/day when you provide contact email in :setting:`MT_MYMEMORY_EMAIL`.
You can also ask them for more.

To enable this service, add ``weblate.machinery.mymemory.MyMemoryTranslation`` to
:setting:`MT_SERVICES` and  set :setting:`MT_MYMEMORY_EMAIL`.

.. seealso::

    :setting:`MT_MYMEMORY_EMAIL`,
    :setting:`MT_MYMEMORY_USER`,
    :setting:`MT_MYMEMORY_KEY`,
    `MyMemory website <https://mymemory.translated.net/>`_

.. _tmserver:

tmserver
--------

You can run your own translation memory server which is bundled with
Translate-toolkit and let Weblate talk to it. You can also use it with
amaGama server, which is an enhanced version of tmserver.

First you will want to import some data to the translation memory:

To enable this service, add ``weblate.machinery.tmserver.TMServerTranslation`` to
:setting:`MT_SERVICES`.

.. code-block:: sh

    build_tmdb -d /var/lib/tm/db -s en -t cs locale/cs/LC_MESSAGES/django.po
    build_tmdb -d /var/lib/tm/db -s en -t de locale/de/LC_MESSAGES/django.po
    build_tmdb -d /var/lib/tm/db -s en -t fr locale/fr/LC_MESSAGES/django.po

Now you can start tmserver to listen to your requests:

.. code-block:: sh

    tmserver -d /var/lib/tm/db

And configure Weblate to talk to it:

.. code-block:: python

    MT_TMSERVER = 'http://localhost:8888/tmserver/'

.. seealso::

    :setting:`MT_TMSERVER`,
    :doc:`tt:commands/tmserver`
    `Amagama Translation Memory server <http://docs.translatehouse.org/projects/virtaal/en/latest/amagama.html>`_
    `Amagama Translation Memory <http://amagama.translatehouse.org/>`_

.. _yandex-translate:

Yandex Translate
----------------

Machine translation service provided by Yandex.

This service uses Translation API and you need to obtain API key from Yandex.

To enable this service, add ``weblate.machinery.yandex.YandexTranslation`` to
:setting:`MT_SERVICES` and set :setting:`MT_YANDEX_KEY`.

.. seealso::

    :setting:`MT_YANDEX_KEY`,
    `Yandex Translate API <https://tech.yandex.com/translate/>`_,
    `Powered by Yandex.Translate <http://translate.yandex.com/>`_

Weblate
-------

Weblate can be source of machine translation as well. It is based on the fulltext
engine Whoosh and provides both exact and inexact matches.

To enable these services, add
``weblate.machinery.weblatetm.WeblateTranslation`` to
:setting:`MT_SERVICES`.

.. _weblate-translation-memory:

Weblate Translation Memory
--------------------------

.. versionadded:: 2.20

The :ref:`translation-memory` can use used as source for machine translation
suggestions as well.

To enable these services, add ``weblate.memory.machine.WeblateMemory`` to
the :setting:`MT_SERVICES`. This service is enabled by
default.

.. _saptranslationhub:

SAP Translation Hub
-------------------

Machine translation service provided by SAP.

You need to have a SAP account (and enabled the SAP Translation Hub in the SAP Cloud 
Platform) to use this service.

To enable this service, add
``weblate.machinery.saptranslationhub.SAPTranslationHub`` to
:setting:`MT_SERVICES` and set appropriate access to either
sandbox or productive API.

.. note::

    To access the Sandbox API, you need to set :setting:`MT_SAP_BASE_URL`
    and :setting:`MT_SAP_SANDBOX_APIKEY`.
    
    To access the productive API, you need to set :setting:`MT_SAP_BASE_URL`,
    :setting:`MT_SAP_USERNAME` and :setting:`MT_SAP_PASSWORD`.

.. seealso::

    :setting:`MT_SAP_BASE_URL`,
    :setting:`MT_SAP_SANDBOX_APIKEY`,
    :setting:`MT_SAP_USERNAME`,
    :setting:`MT_SAP_PASSWORD`,
    :setting:`MT_SAP_USE_MT`
    `SAP Translation Hub API <https://api.sap.com/shell/discover/contentpackage/SAPTranslationHub/api/translationhub>`_

Custom machine translation
--------------------------

You can also implement your own machine translation services using a few lines of
Python code. This example implements translation to a fixed list of
languages using ``dictionary`` Python module:

.. literalinclude:: ../../examples/mt_service.py
    :language: python

You can list own class in :setting:`MT_SERVICES` and Weblate
will start using that.
