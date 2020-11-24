.. _machine-translation-setup:

Machine translation
===================

Built-in support for several machine translation services and can be turned on
by the administrator using :setting:`MT_SERVICES` for each one. They come subject
to their terms of use, so ensure you are allowed to use them how you want.

The source language can be configured at :ref:`project`.

amaGama
-------

Special installation of :ref:`tmserver` run by the authors of Virtaal.

Turn on this service by adding ``weblate.machinery.tmserver.AmagamaTranslation`` to
:setting:`MT_SERVICES`.

.. seealso::

    :ref:`amagama:installation`,
    :doc:`virtaal:amagama`,
    `amaGama Translation Memory <https://amagama.translatehouse.org/>`_

.. _apertium:

Apertium
--------

A libre software machine translation platform providing translations to
a limited set of languages.

The recommended way to use Apertium is to run your own Apertium-APy server.

Turn on this service by adding ``weblate.machinery.apertium.ApertiumAPYTranslation`` to
:setting:`MT_SERVICES` and set :setting:`MT_APERTIUM_APY`.

.. seealso::

    :setting:`MT_APERTIUM_APY`, `Apertium website <https://www.apertium.org/>`_,
    `Apertium APy documentation <https://wiki.apertium.org/wiki/Apertium-apy>`_

.. _aws:

AWS
---

.. versionadded:: 3.1

Amazon Translate is a neural machine translation service for translating text
to and from English across a breadth of supported languages.

1. Turn on this service by adding ``weblate.machinery.aws.AWSTranslation`` to
:setting:`MT_SERVICES`.

2. Install the `boto3` module.
3. Configure Weblate.

.. seealso::

    :setting:`MT_AWS_REGION`, :setting:`MT_AWS_ACCESS_KEY_ID`, :setting:`MT_AWS_SECRET_ACCESS_KEY`
    `Amazon Translate Documentation <https://docs.aws.amazon.com/translate/>`_

.. _baidu-translate:

Baidu API machine translation
-----------------------------

.. versionadded:: 3.2

Machine translation service provided by Baidu.

This service uses an API and you need to obtain an ID and API key from Baidu to use it.

Turn on this service by adding ``weblate.machinery.baidu.BaiduTranslation`` to
:setting:`MT_SERVICES` and set :setting:`MT_BAIDU_ID` and
:setting:`MT_BAIDU_SECRET`.

.. seealso::

    :setting:`MT_BAIDU_ID`,
    :setting:`MT_BAIDU_SECRET`
    `Baidu Translate API <https://api.fanyi.baidu.com/api/trans/product/index>`_

.. _deepl:

DeepL
-----

.. versionadded:: 2.20

DeepL is paid service providing good machine translation for a few languages.
You need to purchase :guilabel:`DeepL API` subscription or you can use legacy
:guilabel:`DeepL Pro (classic)` plan.

Turn on this service by adding ``weblate.machinery.deepl.DeepLTranslation`` to
:setting:`MT_SERVICES` and set :setting:`MT_DEEPL_KEY`.

.. hint::

   In case you have subscription for CAT tools, you are supposed to use "v1
   API" instead of default "v2" used by Weblate (it is not really an API
   version in this case). You can toggle this by :setting:`MT_DEEPL_API_VERSION`.

.. seealso::

    :setting:`MT_DEEPL_KEY`,
    :setting:`MT_DEEPL_API_VERSION`,
    `DeepL website <https://www.deepl.com/>`_,
    `DeepL pricing <https://www.deepl.com/pro>`_,
    `DeepL API documentation <https://www.deepl.com/api.html>`_


.. _glosbe:

Glosbe
------

Free dictionary and translation memory for almost every living language.

The API is gratis to use, but subject to the used data source license. There is a limit
of calls that may be done from one IP in a set period of time, to prevent
abuse.

Turn on this service by adding ``weblate.machinery.glosbe.GlosbeTranslation`` to
:setting:`MT_SERVICES`.

.. seealso::

    `Glosbe website <https://glosbe.com/>`_

.. _google-translate:

Google Translate
----------------

Machine translation service provided by Google.

This service uses the Google Translation API, and you need to obtain an API key and turn on
billing in the Google API console.

To turn on this service, add ``weblate.machinery.google.GoogleTranslation`` to
:setting:`MT_SERVICES` and set :setting:`MT_GOOGLE_KEY`.

.. seealso::

    :setting:`MT_GOOGLE_KEY`,
    `Google translate documentation <https://cloud.google.com/translate/docs>`_

.. _google-translate-api3:

Google Translate API V3 (Advanced)
----------------------------------

Machine translation service provided by Google Cloud services.

This service differs from the former one in how it authenticates.
To enable service, add ``weblate.machinery.googlev3.GoogleV3Translation`` to
:setting:`MT_SERVICES` and set

 - :setting:`MT_GOOGLE_CREDENTIALS`
 - :setting:`MT_GOOGLE_PROJECT`

If `location` fails, you may also need to specify :setting:`MT_GOOGLE_LOCATION`.

.. seealso::

    :setting:`MT_GOOGLE_CREDENTIALS`, :setting:`MT_GOOGLE_PROJECT`, :setting:`MT_GOOGLE_LOCATION`
    `Google translate documentation <https://cloud.google.com/translate/docs>`_

.. _ms-cognitive-translate:

Microsoft Cognitive Services Translator
---------------------------------------

.. versionadded:: 2.10

Machine translation service provided by Microsoft in Azure portal as a one of
Cognitive Services.

Weblate implements Translator API V3.

To enable this service, add ``weblate.machinery.microsoft.MicrosoftCognitiveTranslation`` to
:setting:`MT_SERVICES` and set :setting:`MT_MICROSOFT_COGNITIVE_KEY`.

Translator Text API V2
``````````````````````
The key you use with Translator API V2 can be used with API 3.

Translator Text API V3
``````````````````````
You need to register at Azure portal and use the key you obtain there.
With new Azure keys, you also need to set :setting:`MT_MICROSOFT_REGION` to locale of your service.

.. seealso::

    :setting:`MT_MICROSOFT_COGNITIVE_KEY`, :setting:`MT_MICROSOFT_REGION`,
    `Cognitive Services - Text Translation API <https://azure.microsoft.com/en-us/services/cognitive-services/translator/>`_,
    `Microsoft Azure Portal <https://portal.azure.com/>`_

.. _ms-terminology:

Microsoft Terminology Service
-----------------------------

.. versionadded:: 2.19

The Microsoft Terminology Service API allows you to programmatically access the
terminology, definitions and user interface (UI) strings available in the
Language Portal through a web service.

Turn this service on by adding ``weblate.machinery.microsoftterminology.MicrosoftTerminologyService`` to
:setting:`MT_SERVICES`.

.. seealso::

    `Microsoft Terminology Service API <https://www.microsoft.com/en-us/language/Microsoft-Terminology-API>`_

.. _modernmt:

ModernMT
--------

.. versionadded:: 4.2


Turn this service on by adding ``weblate.machinery.modernmt.ModernMTTranslation`` to
:setting:`MT_SERVICES` and configure :setting:`MT_MODERNMT_KEY`.

.. seealso::

    `ModernMT API <https://www.modernmt.com/api/translate/>`_,
    :setting:`MT_MODERNMT_KEY`,
    :setting:`MT_MODERNMT_URL`

.. _mymemory:

MyMemory
--------

Huge translation memory with machine translation.

Free, anonymous usage is currently limited to 100 requests/day, or to 1000
requests/day when you provide a contact e-mail address in :setting:`MT_MYMEMORY_EMAIL`.
You can also ask them for more.

Turn on this service by adding ``weblate.machinery.mymemory.MyMemoryTranslation`` to
:setting:`MT_SERVICES` and  set :setting:`MT_MYMEMORY_EMAIL`.

.. seealso::

    :setting:`MT_MYMEMORY_EMAIL`,
    :setting:`MT_MYMEMORY_USER`,
    :setting:`MT_MYMEMORY_KEY`,
    `MyMemory website <https://mymemory.translated.net/>`_

.. _netease-translate:

NetEase Sight API machine translation
-------------------------------------

.. versionadded:: 3.3

Machine translation service provided by Netease.

This service uses an API, and you need to obtain key and secret from NetEase.

Turn on this service by adding ``weblate.machinery.youdao.NeteaseSightTranslation`` to
:setting:`MT_SERVICES` and set :setting:`MT_NETEASE_KEY` and
:setting:`MT_NETEASE_SECRET`.

.. seealso::

    :setting:`MT_NETEASE_KEY`,
    :setting:`MT_NETEASE_SECRET`
    `Netease Sight Translation Platform <https://sight.youdao.com/>`_

.. _tmserver:

tmserver
--------

You can run your own translation memory server by using the one bundled with
Translate-toolkit and let Weblate talk to it. You can also use it with an
amaGama server, which is an enhanced version of tmserver.

1. First you will want to import some data to the translation memory:

2. Turn on this service by adding ``weblate.machinery.tmserver.TMServerTranslation`` to
:setting:`MT_SERVICES`.

.. code-block:: sh

    build_tmdb -d /var/lib/tm/db -s en -t cs locale/cs/LC_MESSAGES/django.po
    build_tmdb -d /var/lib/tm/db -s en -t de locale/de/LC_MESSAGES/django.po
    build_tmdb -d /var/lib/tm/db -s en -t fr locale/fr/LC_MESSAGES/django.po

3. Start tmserver to listen to your requests:

.. code-block:: sh

    tmserver -d /var/lib/tm/db

4. Configure Weblate to talk to it:

.. code-block:: python

    MT_TMSERVER = "http://localhost:8888/tmserver/"

.. seealso::

    :setting:`MT_TMSERVER`,
    :doc:`tt:commands/tmserver`
    :ref:`amagama:installation`,
    :doc:`virtaal:amagama`,
    `Amagama Translation Memory <https://amagama.translatehouse.org/>`_


.. _yandex-translate:

Yandex Translate
----------------

Machine translation service provided by Yandex.

This service uses a Translation API, and you need to obtain an API key from Yandex.

Turn on this service by adding ``weblate.machinery.yandex.YandexTranslation`` to
:setting:`MT_SERVICES`, and set :setting:`MT_YANDEX_KEY`.

.. seealso::

    :setting:`MT_YANDEX_KEY`,
    `Yandex Translate API <https://yandex.com/dev/translate/>`_,
    `Powered by Yandex.Translate <https://translate.yandex.com/>`_

.. _youdao-translate:

Youdao Zhiyun API machine translation
-------------------------------------

.. versionadded:: 3.2

Machine translation service provided by Youdao.

This service uses an API, and you need to obtain an ID and an API key from Youdao.

Turn on this service by adding ``weblate.machinery.youdao.YoudaoTranslation`` to
:setting:`MT_SERVICES` and set :setting:`MT_YOUDAO_ID` and
:setting:`MT_YOUDAO_SECRET`.

.. seealso::

    :setting:`MT_YOUDAO_ID`,
    :setting:`MT_YOUDAO_SECRET`
    `Youdao Zhiyun Natural Language Translation Service <https://ai.youdao.com/product-fanyi-text.s>`_

Weblate
-------

Weblate can be the source of machine translations as well.
It is based on the Woosh fulltext engine, and provides both exact and inexact matches.

Turn on these services by adding ``weblate.machinery.weblatetm.WeblateTranslation`` to
:setting:`MT_SERVICES`.

.. _weblate-translation-memory:

Weblate Translation Memory
--------------------------

.. versionadded:: 2.20

The :ref:`translation-memory` can be used as a source for machine translation
suggestions as well.

Turn on these services by adding ``weblate.memory.machine.WeblateMemory`` to
the :setting:`MT_SERVICES`. This service is turned on by
default.

.. _saptranslationhub:

SAP Translation Hub
-------------------

Machine translation service provided by SAP.

You need to have a SAP account (and enabled the SAP Translation Hub in the SAP Cloud
Platform) to use this service.

Turn on this service by adding ``weblate.machinery.saptranslationhub.SAPTranslationHub`` to
:setting:`MT_SERVICES` and set the appropriate access to either
sandbox or the productive API.

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
Python code. This example implements machine translation in a fixed list of
languages using ``dictionary`` Python module:

.. literalinclude:: ../../weblate/examples/mt_service.py
    :language: python

You can list own class in :setting:`MT_SERVICES` and Weblate
will start using that.
