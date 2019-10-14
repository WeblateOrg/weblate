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

    :doc:`virtaal:amagama`,
    `Amagama Translation Memory <https://amagama.translatehouse.org/>`_

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

.. _aws:

AWS
---

.. versionadded:: 3.1

Amazon Translate is a neural machine translation service for translating text
to and from English across a breadth of supported languages.

To enable this service, add ``weblate.machinery.aws.AWSTranslation`` to
:setting:`MT_SERVICES`, install the `boto3` module and set the settings.

.. seealso::

    :setting:`MT_AWS_REGION`, :setting:`MT_AWS_ACCESS_KEY_ID`, :setting:`MT_AWS_SECRET_ACCESS_KEY`
    `Amazon Translate Documentation <https://docs.aws.amazon.com/translate/>`_

.. _baidu-translate:

Baidu API machine translation
-----------------------------

.. versionadded:: 3.2

Machine translation service provided by Baidu.

This service uses an API and you need to obtain ID and API key from Baidu.

To enable this service, add ``weblate.machinery.baidu.BaiduTranslation`` to
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

.. _ms-cognitive-translate:

Microsoft Cognitive Services Translator
---------------------------------------

.. versionadded:: 2.10

Machine translation service provided by Microsoft in Azure portal as a one of
Cognitive Services.

You need to register at Azure portal and use the key you obtain there.

To enable this service, add ``weblate.machinery.microsoft.MicrosoftCognitiveTranslation`` to
:setting:`MT_SERVICES` and set :setting:`MT_MICROSOFT_COGNITIVE_KEY`.

.. seealso::

    :setting:`MT_MICROSOFT_COGNITIVE_KEY`,
    `Cognitive Services - Text Translation API <https://azure.microsoft.com/services/cognitive-services/translator-text-api/>`_,
    `Microsoft Azure Portal <https://portal.azure.com/>`_

.. _ms-terminology:

Microsoft Terminology Service
-----------------------------

.. versionadded:: 2.19

The Microsoft Terminology Service API allows you to programmatically access the
terminology, definitions and user interface (UI) strings available on the
Language Portal through a web service.

To enable this service, add ``weblate.machinery.microsoftterminology.MicrosoftTerminologyService`` to
:setting:`MT_SERVICES`.

.. seealso::

    `Microsoft Terminology Service API <https://www.microsoft.com/en-us/language/Microsoft-Terminology-API>`_

.. _mymemory:

MyMemory
--------

Huge translation memory with machine translation.

Free, anonymous usage is currently limited to 100 requests/day, or to 1000
requests/day when you provide contact e-mail in :setting:`MT_MYMEMORY_EMAIL`.
You can also ask them for more.

To enable this service, add ``weblate.machinery.mymemory.MyMemoryTranslation`` to
:setting:`MT_SERVICES` and  set :setting:`MT_MYMEMORY_EMAIL`.

.. seealso::

    :setting:`MT_MYMEMORY_EMAIL`,
    :setting:`MT_MYMEMORY_USER`,
    :setting:`MT_MYMEMORY_KEY`,
    `MyMemory website <https://mymemory.translated.net/>`_

.. _netease-translate:

Netease Sight API machine translation
-------------------------------------

.. versionadded:: 3.3

Machine translation service provided by Netease.

This service uses an API and you need to obtain key and secret from Netease.

To enable this service, add ``weblate.machinery.youdao.NeteaseSightTranslation`` to
:setting:`MT_SERVICES` and set :setting:`MT_NETEASE_KEY` and
:setting:`MT_NETEASE_SECRET`.

.. seealso::

    :setting:`MT_NETEASE_KEY`,
    :setting:`MT_NETEASE_SECRET`
    `Netease Sight Translation Platform <https://sight.netease.com/>`_

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
    :doc:`virtaal:amagama`,
    `Amagama Translation Memory <https://amagama.translatehouse.org/>`_


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
    `Powered by Yandex.Translate <https://translate.yandex.com/>`_

.. _youdao-translate:

Youdao Zhiyun API machine translation
-------------------------------------

.. versionadded:: 3.2

Machine translation service provided by Youdao.

This service uses an API and you need to obtain ID and API key from Youdao.

To enable this service, add ``weblate.machinery.youdao.YoudaoTranslation`` to
:setting:`MT_SERVICES` and set :setting:`MT_YOUDAO_ID` and
:setting:`MT_YOUDAO_SECRET`.

.. seealso::

    :setting:`MT_YOUDAO_ID`,
    :setting:`MT_YOUDAO_SECRET`
    `Youdao Zhiyun Natural Language Translation Service <https://ai.youdao.com/product-fanyi.s>`_

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

The :ref:`translation-memory` can be used as source for machine translation
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

.. literalinclude:: ../../weblate/examples/mt_service.py
    :language: python

You can list own class in :setting:`MT_SERVICES` and Weblate
will start using that.
