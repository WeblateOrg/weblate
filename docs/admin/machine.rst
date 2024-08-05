.. _machine-translation-setup:

Automatic suggestions
=====================

.. versionchanged:: 4.13

   Prior to Weblate 4.13, the services were configured in the :ref:`config`.

The support for several machine translation and translation memory services is
built-in. Each service can be turned on by the administrator for whole site
(under :guilabel:`Automatic suggestions` in :ref:`management-interface`) or at
the project settings:

.. image:: /screenshots/project-machinery.webp

.. note::

   They come subject to their terms of use, so ensure you are allowed to use
   them how you want.

The services translate from the source language as configured at
:ref:`component`, see :ref:`component-source_language`.

.. seealso::

   :ref:`machine-translation`

.. _mt-alibaba:

Alibaba
-------

.. versionadded:: 5.3

:Service ID: ``alibaba``
:Configuration: +------------+-------------------+--+
                | ``key``    | Access key ID     |  |
                +------------+-------------------+--+
                | ``secret`` | Access key secret |  |
                +------------+-------------------+--+
                | ``region`` | Region ID         |  |
                +------------+-------------------+--+

Alibaba Translate is a neural machine translation service for translating text
and it supports up to 214 language pairs.

.. seealso::

    `Alibaba Translate Documentation <https://www.alibabacloud.com/help/en/machine-translation>`_

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

Amazon Translate
----------------

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

.. _mt-cyrtranslit:

Cyrtranslit
-----------

.. versionadded:: 5.7

:Service ID: ``cyrtranslit``
:Configuration: `This service has no configuration.`

Machine translation service using the Cyrtranslit library.

This service converts text between Cyrillic and Latin scripts for languages that have both scripts.

.. seealso::

    `Cyrtranslit repository <https://github.com/opendatakosovo/cyrillic-transliteration>`_

.. _mt-deepl:

DeepL
-----

:Service ID: ``deepl``
:Configuration: +---------------+-----------+-------------------------------------------------------------------------+
                | ``url``       | API URL   |                                                                         |
                +---------------+-----------+-------------------------------------------------------------------------+
                | ``key``       | API key   |                                                                         |
                +---------------+-----------+-------------------------------------------------------------------------+
                | ``formality`` | Formality | Uses the specified formality if language is not specified as (in)formal |
                +---------------+-----------+-------------------------------------------------------------------------+

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

Weblate supports DeepL formality, it will choose matching one based on the
language (for example, there is ``de@formal`` and ``de@informal``).

The service automatically uses :ref:`glossary`, see :ref:`glossary-mt`.

.. seealso::

    `DeepL translator <https://www.deepl.com/translator>`_,
    `DeepL pricing <https://www.deepl.com/pro>`_,
    `DeepL API documentation <https://developers.deepl.com/docs>`_

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

Google Cloud Translation Basic
------------------------------

:Service ID: ``google-translate``
:Configuration: +---------+---------+--+
                | ``key`` | API key |  |
                +---------+---------+--+

Machine translation service provided by the Google Cloud services.

This service uses the Google Translation API v2, and you need to obtain an API key and turn on
billing in the Google API console.

.. seealso::

    `Google translate documentation <https://cloud.google.com/translate/docs>`_

.. _mt-google-translate-api-v3:

Google Cloud Translation Advanced
---------------------------------

:Service ID: ``google-translate-api-v3``
:Configuration: +-----------------+---------------------------------------+----------------------------------------------------------------------------------------------------------+
                | ``credentials`` | Google Translate service account info | Enter a JSON key for the service account.                                                                |
                +-----------------+---------------------------------------+----------------------------------------------------------------------------------------------------------+
                | ``project``     | Google Translate project              | Enter the numeric or alphanumeric ID of your Google Cloud project.                                       |
                +-----------------+---------------------------------------+----------------------------------------------------------------------------------------------------------+
                | ``location``    | Google Translate location             | Choose a Google Cloud Translation region that is used for the Google Cloud project or is closest to you. |
                +-----------------+---------------------------------------+----------------------------------------------------------------------------------------------------------+

Machine translation service provided by the Google Cloud services.

This service uses the Google Translation API v3 and you need credentials in JSON format to access it.

In order to use this service, you first need to go through the following steps:

1. `Select or create a Cloud Platform project.`_
2. `Enable billing for your project.`_
3. `Enable the Cloud Translation.`_
4. `Setup Authentication.`_

.. _Select or create a Cloud Platform project.: https://console.cloud.google.com/project
.. _Enable billing for your project.: https://cloud.google.com/billing/docs/how-to/modify-project#enable_billing_for_a_project
.. _Enable the Cloud Translation.:  https://cloud.google.com/translate/docs/
.. _Setup Authentication.: https://googleapis.dev/python/google-api-core/latest/auth.html

.. seealso::

    `Google translate documentation <https://cloud.google.com/translate/docs>`_,
    `Authenticate to Cloud services using client libraries <https://cloud.google.com/docs/authentication/client-libraries>`_,
    `Creating Google Translate project <https://cloud.google.com/appengine/docs/standard/nodejs/building-app/creating-project>`_,
    `Google Cloud App Engine locations <https://cloud.google.com/appengine/docs/standard/locations>`_

.. _mt-ibm:

IBM Watson Language Translator
------------------------------

.. versionadded:: 4.16

:Service ID: ``ibm``
:Configuration: +---------+---------+--+
                | ``url`` | API URL |  |
                +---------+---------+--+
                | ``key`` | API key |  |
                +---------+---------+--+

.. warning::

   This service is deprecated by vendor and will be withdrawn entirely as of 10 December 2024.

IBM Watson Language Translator translates text from one language to another.
The service offers multiple domain-specific models.

.. seealso::

    `Watson Language Translator <https://www.ibm.com/products/natural-language-processing>`_,
    `IBM Cloud API Docs <https://cloud.ibm.com/apidocs/language-translator>`_

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
    `LibreTranslate repository <https://github.com/LibreTranslate/LibreTranslate>`_

.. _mt-microsoft-translator:

Azure AI Translator
-------------------

:Service ID: ``microsoft-translator``
:Configuration: +------------------+-------------------------------+---------------------------------------------------------------------------+
                | ``key``          | API key                       |                                                                           |
                +------------------+-------------------------------+---------------------------------------------------------------------------+
                | ``base_url``     | Application base URL          | Available choices:                                                        |
                |                  |                               |                                                                           |
                |                  |                               | ``api.cognitive.microsofttranslator.com`` -- Global (non-regional)        |
                |                  |                               |                                                                           |
                |                  |                               | ``api-apc.cognitive.microsofttranslator.com`` -- Asia Pacific             |
                |                  |                               |                                                                           |
                |                  |                               | ``api-eur.cognitive.microsofttranslator.com`` -- Europe                   |
                |                  |                               |                                                                           |
                |                  |                               | ``api-nam.cognitive.microsofttranslator.com`` -- North America            |
                |                  |                               |                                                                           |
                |                  |                               | ``api.translator.azure.cn`` -- China                                      |
                |                  |                               |                                                                           |
                |                  |                               | ``api.cognitive.microsofttranslator.us`` -- Azure US Government cloud     |
                +------------------+-------------------------------+---------------------------------------------------------------------------+
                | ``endpoint_url`` | Authentication service URL    | Regional or multi-service can be specified using region field below.      |
                |                  |                               |                                                                           |
                |                  |                               | Available choices:                                                        |
                |                  |                               |                                                                           |
                |                  |                               | ``api.cognitive.microsoft.com`` -- Global                                 |
                |                  |                               |                                                                           |
                |                  |                               | ``api.cognitive.azure.cn`` -- China                                       |
                |                  |                               |                                                                           |
                |                  |                               | ``api.cognitive.microsoft.us`` -- Azure US Government cloud               |
                +------------------+-------------------------------+---------------------------------------------------------------------------+
                | ``region``       | Authentication service region |                                                                           |
                +------------------+-------------------------------+---------------------------------------------------------------------------+
                | ``category``     | Category                      | Specify a customized system category ID to use it instead of general one. |
                +------------------+-------------------------------+---------------------------------------------------------------------------+

Machine translation service provided by Microsoft in Azure portal as a one of
Cognitive Services.

Weblate implements Translator API V3.

The service automatically uses :ref:`glossary` via `dynamic dictionary <https://learn.microsoft.com/en-us/azure/ai-services/translator/dynamic-dictionary>`_, see :ref:`glossary-mt`.

Translator Text API V2
``````````````````````
The key you use with Translator API V2 can be used with API 3.

Translator Text API V3
``````````````````````
You need to register at Azure portal and use the key you obtain there.
With new Azure keys, you also need to set ``region`` to locale of your service.

You can also specify a custom category to use `custom translator <https://learn.microsoft.com/en-gb/azure/ai-services/Translator/custom-translator/concepts/customization>`_.

.. hint::

   For Azure China, please use your endpoint from the Azure Portal.

.. seealso::

   `Cognitive Services - Text Translation API <https://azure.microsoft.com/en-us/products/ai-services/ai-translator>`_,
   `Microsoft Azure Portal <https://portal.azure.com/>`_,
   `Base URLs <https://learn.microsoft.com/en-us/azure/ai-services/translator/reference/v3-0-reference#base-urls>`_,
   `"Authenticating with a Multi-service resource" <https://learn.microsoft.com/en-us/azure/ai-services/translator/reference/v3-0-reference#authenticating-with-a-multi-service-resource>`_
   `"Authenticating with an access token" section <https://learn.microsoft.com/en-us/azure/ai-services/translator/reference/v3-0-reference#authenticating-with-an-access-token>`_

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

    `ModernMT API <https://www.modernmt.com/api/#translation>`_

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

.. _mt-openai:

OpenAI
------

.. versionadded:: 5.3

:Service ID: ``openai``
:Configuration: +------------------+---------------------+---------------------------------------------------------------------------------------------------------------------------+
                | ``key``          | API key             |                                                                                                                           |
                +------------------+---------------------+---------------------------------------------------------------------------------------------------------------------------+
                | ``base_url``     | OpenAI API base URL | Base URL of the OpenAI API, if it differs from the OpenAI default URL                                                     |
                +------------------+---------------------+---------------------------------------------------------------------------------------------------------------------------+
                | ``model``        | OpenAI model        | Available choices:                                                                                                        |
                |                  |                     |                                                                                                                           |
                |                  |                     | ``auto`` -- Automatic selection                                                                                           |
                |                  |                     |                                                                                                                           |
                |                  |                     | ``gpt-4o`` -- GPT-4o                                                                                                      |
                |                  |                     |                                                                                                                           |
                |                  |                     | ``gpt-4-1106-preview`` -- GPT-4 Turbo                                                                                     |
                |                  |                     |                                                                                                                           |
                |                  |                     | ``gpt-4`` -- GPT-4                                                                                                        |
                |                  |                     |                                                                                                                           |
                |                  |                     | ``gpt-3.5-turbo-1106`` -- Updated GPT 3.5 Turbo                                                                           |
                |                  |                     |                                                                                                                           |
                |                  |                     | ``gpt-3.5-turbo`` -- GPT-3.5 Turbo                                                                                        |
                |                  |                     |                                                                                                                           |
                |                  |                     | ``custom`` -- Custom model                                                                                                |
                +------------------+---------------------+---------------------------------------------------------------------------------------------------------------------------+
                | ``custom_model`` | Custom model name   | Only needed when model is set to 'Custom model'                                                                           |
                +------------------+---------------------+---------------------------------------------------------------------------------------------------------------------------+
                | ``persona``      | Translator persona  | Describe the persona of translator to improve the accuracy of the translation. For example: “You are a squirrel breeder.” |
                +------------------+---------------------+---------------------------------------------------------------------------------------------------------------------------+
                | ``style``        | Translator style    | Describe the style of translation. For example: “Use informal language.”                                                  |
                +------------------+---------------------+---------------------------------------------------------------------------------------------------------------------------+

Performs translation using `OpenAI`_.

The OpenAI API is powered by a diverse set of models with different
capabilities and price points. Automatic selection chooses the best model
available, but you might want to choose a specific model that matches your needs.

Use persona and style fields to further fine-tune translations. These will be
used in a prompt for OpenAI and allow you to change the style of the
translations.

The service automatically uses :ref:`glossary`, see :ref:`glossary-mt`.

.. versionchanged:: 5.7

   Support for custom model and base URL was added.

.. seealso::

   `OpenAI models <https://platform.openai.com/docs/models>`_,
   `OpenAI API keys <https://platform.openai.com/api-keys>`_

.. _OpenAI: https://openai.com/

.. _mt-sap-translation-hub:

SAP Translation Hub
-------------------

:Service ID: ``sap-translation-hub``
:Configuration: +---------------+----------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------+
                | ``url``       | API URL                    |                                                                                                                                                 |
                +---------------+----------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------+
                | ``key``       | API key                    |                                                                                                                                                 |
                +---------------+----------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------+
                | ``username``  | SAP username               |                                                                                                                                                 |
                +---------------+----------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------+
                | ``password``  | SAP password               |                                                                                                                                                 |
                +---------------+----------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------+
                | ``enable_mt`` | Enable machine translation |                                                                                                                                                 |
                +---------------+----------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------+
                | ``domain``    | Translation domain         | The ID of a translation domain, for example, BC. If you do not specify a domain, the method searches for translations in all available domains. |
                +---------------+----------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------+

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

    `SAP Translation Hub API <https://api.sap.com/shell/discover/contentpackage/SAPTranslationHub/api/translationhub>`_,
    `Building the Base URL of SAP Translation Hub <https://help.sap.com/docs/SAP_TRANSLATION_HUB/ed6ce7a29bdd42169f5f0d7868bce6eb/3a011fba82644259a2cc3c919863f4b4.html>`_

.. _mt-systran:

Systran
-------

:Service ID: ``systran``
:Configuration: +---------+---------+--+
                | ``key`` | API key |  |
                +---------+---------+--+


Machine translation service provided by Systran.

This service uses an API, and you need to obtain API key at <https://translate.systran.net/en/account>.

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

    :doc:`tt:commands/tmserver`,
    :ref:`amagama:installation`,
    :doc:`virtaal:amagama`,
    `Amagama Translation Memory <https://amagama.translatehouse.org/>`_


.. _mt-weblate:

Weblate
-------

:Service ID: ``weblate``
:Configuration: `This service has no configuration.`


Weblate machine translation service can provide translations based
on the exact matches of a string in the currently existing strings
in a  :guilabel:`Translated`, :guilabel:`Approved`,
or :guilabel:`Read-only` :ref:`states <states>` inside Weblate.

.. _mt-weblate-translation-memory:

Weblate Translation Memory
--------------------------

:Service ID: ``weblate-translation-memory``
:Configuration: `This service has no configuration.`

Use :ref:`translation-memory` as a machine translation service.
Any string that has been translated before (or uploaded to the
translation memory) can be translated in this way.
This suggestion source works with fuzzy matching.

.. note::

   Recreating :ref:`translation-memory` reduces capabilities of this TM source.

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

.. _mt-yandex-v2:

Yandex v2
---------

.. versionadded:: 5.1

:Service ID: ``yandex-v2``
:Configuration: +---------+---------+--+
                | ``key`` | API key |  |
                +---------+---------+--+

Machine translation service provided by Yandex.

This service uses a Translation API, and you need to obtain an API key from Yandex Cloud.

.. seealso::

    `Yandex Translate API v2 <https://cloud.yandex.com/en/docs/translate/api-ref/authentication>`_,
    `Powered by Yandex.Cloud <https://cloud.yandex.com/en/services/translate>`_

.. _mt-youdao-zhiyun:

Youdao Zhiyun
-------------

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
