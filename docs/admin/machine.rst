.. _machine-translation-setup:

Configuring automatic suggestions
=================================

.. versionchanged:: 4.13

   Prior to Weblate 4.13, the services were configured in the :ref:`config`.

The support for several machine translation and translation memory services is
built-in. Each service can be turned on by the administrator for whole site or
at the project settings:

.. image:: /screenshots/project-machinery.png

.. note::

   They come subject to their terms of use, so ensure you are allowed to use
   them how you want.

The services translate from the source language as configured at
:ref:`component`, see :ref:`component-source_language`.

.. seealso::

   :ref:`machine-translation`

.. _mt-amagama:

Amagama
-------

:Service ID: ``amagama``
:Configuration: `This service has no configuration.`

Special installation of :ref:`mt-tmserver` run by the authors of Virtaal.

.. seealso::

    :ref:`amagama:installation`,
    :doc:`virtaal:amagama`,
    `amaGama Translation Memory <https://amagama.translatehouse.org/>`_


.. _mt-apertium-apy:

Apertium APy
------------

:Service ID: ``apertium-apy``
:Configuration: +---------+---------+--+
                | ``url`` | API URL |  |
                +---------+---------+--+

A libre software machine translation platform providing translations to
a limited set of languages.

The recommended way to use Apertium is to run your own Apertium-APy server.

.. seealso::

   `Apertium website <https://www.apertium.org/>`_,
   `Apertium APy documentation <https://wiki.apertium.org/wiki/Apertium-apy>`_



.. _mt-aws:

AWS
---

.. versionadded:: 3.1

:Service ID: ``aws``
:Configuration: +------------+----------------+--+
                | ``key``    | Access key ID  |  |
                +------------+----------------+--+
                | ``secret`` | API secret key |  |
                +------------+----------------+--+
                | ``region`` | Region name    |  |
                +------------+----------------+--+

Amazon Translate is a neural machine translation service for translating text
to and from English across a breadth of supported languages.

.. seealso::

    `Amazon Translate Documentation <https://docs.aws.amazon.com/translate/>`_

.. _mt-baidu:

Baidu
-----

.. versionadded:: 3.2

:Service ID: ``baidu``
:Configuration: +------------+---------------+--+
                | ``key``    | Client ID     |  |
                +------------+---------------+--+
                | ``secret`` | Client secret |  |
                +------------+---------------+--+

Machine translation service provided by Baidu.

This service uses an API and you need to obtain an ID and API key from Baidu to use it.

.. seealso::

    `Baidu Translate API <https://api.fanyi.baidu.com/api/trans/product/index>`_

.. _mt-deepl:

DeepL
-----

.. versionadded:: 2.20

:Service ID: ``deepl``
:Configuration: +---------+---------+--+
                | ``url`` | API URL |  |
                +---------+---------+--+
                | ``key`` | API key |  |
                +---------+---------+--+

DeepL is paid service providing good machine translation for a few languages.
You need to purchase :guilabel:`DeepL API` subscription or you can use legacy
:guilabel:`DeepL Pro (classic)` plan.

API URL to use with the DeepL service. At the time of writing, there is the v1 API
as well as a free and a paid version of the v2 API.

``https://api.deepl.com/v2/`` (default in Weblate)
    Is meant for API usage on the paid plan, and the subscription is usage-based.
``https://api-free.deepl.com/v2/``
    Is meant for API usage on the free plan, and the subscription is usage-based.
``https://api.deepl.com/v1/``
    Is meant for CAT tools and is usable with a per-user subscription.

Previously Weblate was classified as a CAT tool by DeepL, so it was supposed to
use the v1 API, but now is supposed to use the v2 API.
Therefore it defaults to v2, and you can change it to v1 in case you have
an existing CAT subscription and want Weblate to use that.

The easiest way to find out which one to use is to open an URL like the
following in your browser:

https://api.deepl.com/v2/translate?text=Hello&target_lang=FR&auth_key=XXX

Replace the XXX with your auth_key. If you receive a JSON object which contains
"Bonjour", you have the correct URL; if not, try the other three.

.. seealso::

    `DeepL website <https://www.deepl.com/>`_,
    `DeepL pricing <https://www.deepl.com/pro>`_,
    `DeepL API documentation <https://www.deepl.com/docs-api.html>`_

.. _mt-glosbe:

Glosbe
------

:Service ID: ``glosbe``
:Configuration: `This service has no configuration.`

Free dictionary and translation memory for almost every living language.

The API is gratis to use, but usage of the translations is subject to the
license of the used data source. There is a limit of calls that may be done
from one IP in a set period of time, to prevent abuse.

.. seealso::

    `Glosbe website <https://glosbe.com/>`_

.. _mt-google-translate:

Google Translate
----------------

:Service ID: ``google-translate``
:Configuration: +---------+---------+--+
                | ``key`` | API key |  |
                +---------+---------+--+

Machine translation service provided by Google.

This service uses the Google Translation API, and you need to obtain an API key and turn on
billing in the Google API console.

.. seealso::

    `Google translate documentation <https://cloud.google.com/translate/docs>`_

.. _mt-google-translate-api-v3:

Google Translate API v3
-----------------------

:Service ID: ``google-translate-api-v3``
:Configuration: +-----------------+---------------------------------------+--+
                | ``credentials`` | Google Translate service account info |  |
                +-----------------+---------------------------------------+--+
                | ``project``     | Google Translate project              |  |
                +-----------------+---------------------------------------+--+
                | ``location``    | Google Translate location             |  |
                +-----------------+---------------------------------------+--+

Machine translation service provided by Google Cloud services.

.. seealso::

    `Google translate documentation <https://cloud.google.com/translate/docs>`_,
    `Getting started with authentication on Google Cloud <https://cloud.google.com/docs/authentication/getting-started>`_,
    `Creating Google Translate project <https://cloud.google.com/appengine/docs/standard/nodejs/building-app/creating-project>`_,
    `Google Cloud App Engine locations <https://cloud.google.com/appengine/docs/locations>`_

.. _mt-libretranslate:

LibreTranslate
--------------

.. versionadded:: 4.7.1

:Service ID: ``libretranslate``
:Configuration: +---------+---------+--+
                | ``url`` | API URL |  |
                +---------+---------+--+
                | ``key`` | API key |  |
                +---------+---------+--+

LibreTranslate is a free and open-source service for machine translations. The
public instance requires an API key, but LibreTranslate can be self-hosted
and there are several mirrors available to use the API for free.

``https://libretranslate.com/`` (official public instance)
    Requires an API key to use outside of the website.

.. seealso::

    `LibreTranslate website <https://libretranslate.com/>`_,
    `LibreTranslate repository <https://github.com/LibreTranslate/LibreTranslate>`_,
    `LibreTranslate mirrors <https://github.com/LibreTranslate/LibreTranslate#user-content-mirrors>`_

.. _mt-microsoft-terminology:

Microsoft Terminology
---------------------

.. versionadded:: 2.19

:Service ID: ``microsoft-terminology``
:Configuration: `This service has no configuration.`

The Microsoft Terminology Service API allows you to programmatically access the
terminology, definitions and user interface (UI) strings available in the
Language Portal through a web service.

.. seealso::

    `Microsoft Terminology Service API <https://www.microsoft.com/en-us/language/Microsoft-Terminology-API>`_


.. _mt-microsoft-translator:

Microsoft Translator
--------------------

.. versionadded:: 2.10

:Service ID: ``microsoft-translator``
:Configuration: +------------------+--------------------------+--------------------------------------------------------------------+
                | ``key``          | API key                  |                                                                    |
                +------------------+--------------------------+--------------------------------------------------------------------+
                | ``endpoint_url`` | Application endpoint URL |                                                                    |
                +------------------+--------------------------+--------------------------------------------------------------------+
                | ``base_url``     | Application base URL     | Available choices:                                                 |
                |                  |                          |                                                                    |
                |                  |                          | ``api.cognitive.microsofttranslator.com`` -- Global (non-regional) |
                |                  |                          |                                                                    |
                |                  |                          | ``api-apc.cognitive.microsofttranslator.com`` -- Asia Pacific      |
                |                  |                          |                                                                    |
                |                  |                          | ``api-eur.cognitive.microsofttranslator.com`` -- Europe            |
                |                  |                          |                                                                    |
                |                  |                          | ``api-nam.cognitive.microsofttranslator.com`` -- North America     |
                |                  |                          |                                                                    |
                |                  |                          | ``api.translator.azure.cn`` -- China                               |
                +------------------+--------------------------+--------------------------------------------------------------------+
                | ``region``       | Application region       |                                                                    |
                +------------------+--------------------------+--------------------------------------------------------------------+

Machine translation service provided by Microsoft in Azure portal as a one of
Cognitive Services.

Weblate implements Translator API V3.

Translator Text API V2
``````````````````````
The key you use with Translator API V2 can be used with API 3.

Translator Text API V3
``````````````````````
You need to register at Azure portal and use the key you obtain there.
With new Azure keys, you also need to set ``region`` to locale of your service.

.. hint::

   For Azure China, please use your endpoint from the Azure Portal.

.. seealso::

   `Cognitive Services - Text Translation API <https://azure.microsoft.com/en-us/services/cognitive-services/translator/>`_,
   `Microsoft Azure Portal <https://portal.azure.com/>`_,
   `Base URLs <https://docs.microsoft.com/en-us/azure/cognitive-services/translator/reference/v3-0-reference#base-urls>`_,
   `"Authenticating with a Multi-service resource" <https://docs.microsoft.com/en-us/azure/cognitive-services/translator/reference/v3-0-reference#authenticating-with-a-multi-service-resource>`_
   `"Authenticating with an access token" section <https://docs.microsoft.com/en-us/azure/cognitive-services/translator/reference/v3-0-reference#authenticating-with-an-access-token>`_

.. _mt-modernmt:

ModernMT
--------

.. versionadded:: 4.2

:Service ID: ``modernmt``
:Configuration: +---------+---------+--+
                | ``url`` | API URL |  |
                +---------+---------+--+
                | ``key`` | API key |  |
                +---------+---------+--+

.. seealso::

    `ModernMT API <https://www.modernmt.com/api/#translation>`_,

.. _mt-mymemory:

MyMemory
--------

:Service ID: ``mymemory``
:Configuration: +--------------+----------------+--+
                | ``email``    | Contact e-mail |  |
                +--------------+----------------+--+
                | ``username`` | Username       |  |
                +--------------+----------------+--+
                | ``key``      | API key        |  |
                +--------------+----------------+--+


Huge translation memory with machine translation.

Free, anonymous usage is currently limited to 100 requests/day, or to 1000
requests/day when you provide a contact e-mail address in ``email``.
You can also ask them for more.


.. seealso::

    `MyMemory website <https://mymemory.translated.net/>`_

.. _mt-netease-sight:

Netease Sight
-------------

.. versionadded:: 3.3

:Service ID: ``netease-sight``
:Configuration: +------------+---------------+--+
                | ``key``    | Client ID     |  |
                +------------+---------------+--+
                | ``secret`` | Client secret |  |
                +------------+---------------+--+

Machine translation service provided by NetEase.

This service uses an API, and you need to obtain key and secret from NetEase.

.. seealso::

    `NetEase Sight Translation Platform <https://sight.youdao.com/>`_

.. _mt-sap-translation-hub:

SAP Translation Hub
-------------------

:Service ID: ``sap-translation-hub``
:Configuration: +---------------+----------------------------+--+
                | ``url``       | API URL                    |  |
                +---------------+----------------------------+--+
                | ``key``       | API key                    |  |
                +---------------+----------------------------+--+
                | ``username``  | SAP username               |  |
                +---------------+----------------------------+--+
                | ``password``  | SAP password               |  |
                +---------------+----------------------------+--+
                | ``enable_mt`` | Enable machine translation |  |
                +---------------+----------------------------+--+

Machine translation service provided by SAP.

You need to have a SAP account (and the SAP Translation Hub enabled in the SAP Cloud
Platform) to use this service.

You can also configure whether to also use machine translation services, in
addition to the term database.

.. note::

    To access the Sandbox API, you need to set ``url``
    and ``key``.

    To access the productive API, you need to set ``url``, ``username`` and ``password``.

.. seealso::

    `SAP Translation Hub API <https://api.sap.com/shell/discover/contentpackage/SAPTranslationHub/api/translationhub>`_

.. _mt-tmserver:

tmserver
--------

:Service ID: ``tmserver``
:Configuration: +---------+---------+--+
                | ``url`` | API URL |  |
                +---------+---------+--+

You can run your own translation memory server by using the one bundled with
Translate-toolkit and let Weblate talk to it. You can also use it with an
amaGama server, which is an enhanced version of tmserver.

1. First you will want to import some data to the translation memory:

.. code-block:: sh

    build_tmdb -d /var/lib/tm/db -s en -t cs locale/cs/LC_MESSAGES/django.po
    build_tmdb -d /var/lib/tm/db -s en -t de locale/de/LC_MESSAGES/django.po
    build_tmdb -d /var/lib/tm/db -s en -t fr locale/fr/LC_MESSAGES/django.po

2. Start tmserver to listen to your requests:

.. code-block:: sh

    tmserver -d /var/lib/tm/db

3. Configure Weblate to talk to it, the default URL is ``http://localhost:8888/tmserver/``.

.. seealso::

    :doc:`tt:commands/tmserver`
    :ref:`amagama:installation`,
    :doc:`virtaal:amagama`,
    `Amagama Translation Memory <https://amagama.translatehouse.org/>`_

.. _mt-weblate:

Weblate
-------

:Service ID: ``weblate``
:Configuration: `This service has no configuration.`


Weblate machine translation service can provide translations for strings that
are already translated inside Weblate. It looks for exact matches in the
existing strings.

.. _mt-weblate-translation-memory:

Weblate Translation Memory
--------------------------

.. versionadded:: 2.20

:Service ID: ``weblate-translation-memory``
:Configuration: `This service has no configuration.`

Use :ref:`translation-memory` as a machine translation service. Any string that
has been translated in past (or uploaded to the translation memory) can be
translated in this way.

.. _mt-yandex:

Yandex
------

:Service ID: ``yandex``
:Configuration: +---------+---------+--+
                | ``key`` | API key |  |
                +---------+---------+--+

Machine translation service provided by Yandex.

This service uses a Translation API, and you need to obtain an API key from Yandex.

.. seealso::

    `Yandex Translate API <https://yandex.com/dev/translate/>`_,
    `Powered by Yandex.Translate <https://translate.yandex.com/>`_

.. _mt-youdao-zhiyun:

Youdao Zhiyun
-------------

.. versionadded:: 3.2

:Service ID: ``youdao-zhiyun``
:Configuration: +------------+---------------+--+
                | ``key``    | Client ID     |  |
                +------------+---------------+--+
                | ``secret`` | Client secret |  |
                +------------+---------------+--+

Machine translation service provided by Youdao.

This service uses an API, and you need to obtain an ID and an API key from Youdao.

.. seealso::

    `Youdao Zhiyun Natural Language Translation Service <https://ai.youdao.com/product-fanyi-text.s>`_

Custom machine translation
--------------------------

You can also implement your own machine translation services using a few lines of
Python code. This example implements machine translation in a fixed list of
languages using ``dictionary`` Python module:

.. literalinclude:: ../../weblate/examples/mt_service.py
    :language: python

You can list your own class in :setting:`WEBLATE_MACHINERY` and Weblate
will start using that.
