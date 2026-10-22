.. _machine-translation-setup:

Translation services
====================

.. versionchanged:: 4.13

   Prior to Weblate 4.13, the services were configured in the :ref:`config`.

The support for several machine translation and translation memory services is
built-in. You can install a service more than once with different settings. An
administrator can configure installations for the whole site under
:guilabel:`Translation services` in :ref:`management-interface`. Workspace
administrators can configure installations for their workspace, and project
administrators can configure them for a project:

.. image:: /screenshots/project-machinery.webp

.. note::

   They come subject to their terms of use, so ensure you are allowed to use
   them how you want. Third-party services can receive source strings,
   translations, and related context from Weblate.

The services translate from the source language as configured at
:ref:`component`, see :ref:`component-source_language`.

Installations from the site, workspace, and project are combined for a project.
You can exclude an inherited installation, or all inherited installations of
one service, in workspace or project settings. Pausing an installation keeps
its configuration for later use.

Select a service in the listing to open its details, settings, and controls.
Installed services use their numeric installation ID in the detail-page URL.
The detail page provides selectors to use in Automation workflows. Inherited
services link to their owning scope when you have permission to manage them.
The listing summarizes basic configuration such as the model, source-language
selection, and region, together with the installation ID and slug. Credentials,
API URLs, and free-form prompts are excluded from these summaries.

A :guilabel:`Rate limited` badge indicates that Weblate has temporarily paused
requests after a provider error. The default cooldown is 30 minutes, but its
duration varies by service and provider-supplied retry delays; see
:ref:`cooldown configuration <machinery-rate-limit-window>`. It applies to one
installation, including all projects inheriting it. Separate installations have
independent cooldowns, even when they use the same provider credentials.

Administrators can use :guilabel:`Reset rate limit` on the installation's detail
page at its owning site, workspace, or project scope. This clears Weblate's
translation and rephrasing cooldowns without clearing cached suggestions. It
does not reset the provider's quota; another provider error can apply the
cooldown again. Inherited installations show the status, but their cooldown
cannot be reset from a consuming workspace or project.

Every installation has a numeric ID and can have an optional slug. Select one
installation in automatic translation, Automation, or AI review with
``service:id`` or ``service:slug``. A bare service name is accepted when only
one active installation of that service applies to the project. A non-empty
slug must be unique among all installations visible to a project, including
inherited installations. Separate projects can use the same slug. Saved slug
selectors follow the installation currently using that slug. Services without
configuration settings can be installed once per scope and must not overlap
with enabled inherited installations. Exclude an inherited installation before
enabling another one in a lower scope. Each scope can contain up to 20
installations, including paused ones.

For ``install_machinery --update``, specify a unique ``--slug`` or ``--id``
when more than one site installation of a service exists.

Translation service installations can also be configured via the :ref:`api`.

Configured translation services provide suggestions in the
:guilabel:`Automatic suggestions` tab of the translation editor and can be
selected for :ref:`auto-translation`.

.. seealso::

   :ref:`machine-translation`

.. _mt-translation-services-priority:

Priority of machine translation and translation memory services
---------------------------------------------------------------

:ref:`mt-weblate-translation-memory` matches with 100% score take priority over machine translation services. If 100% match in translation memory is found, no machine translation is performed. If several 100% matches occur, the first one returned by the database is used.

Each machine translation service has a predefined maximum score it can produce. The use of installed translation services is ordered according to their maximum score. For each string with translation score lower than the service's maximum, the service is asked to produce a translation. Translations with a score exceeding the current one are accepted.

For explicit ordering and a separate score threshold for each service, use
:ref:`automation-translation-ordering`. This workflow completes one translation
pass before selecting the strings for the next service.

.. _mt-sources:

Source strings for the machine translation
------------------------------------------

.. versionadded:: 5.11

The origin of source strings for all third-party services can be configured.
This can be used to tweak the service to get the best results. Following choices are available:

:guilabel:`Automatic selection`
   Chooses the best source language automatically.

   This is the default behavior.
:guilabel:`Component source language`
   Uses the component source language.

   This was the behavior before the 5.11 release.
:guilabel:`Secondary language defined in project or component`
   Use project :ref:`project-secondary_language` or component :ref:`component-secondary_language`.

   Falls back to the automatic selection of the source language if the secondary language not configured.

.. _llm-translation-context:

LLM translation context
-----------------------

LLM-based translation services receive additional context about each
translated string, when available. This includes the string context or
monolingual key, additional explanation, configured secondary-language
translation, plural information, failing quality checks, and placeholder
contents. Matching glossary entries are passed with their explanations and
selected flags, so duplicate glossary terms can be disambiguated.

You can add target-language-specific instructions in
:guilabel:`Language-specific instructions` using a JSON object mapping language
codes to text. Language codes have to exist in Weblate and are matched exactly;
whitespace is not ignored. Each instruction can contain up to 1000 characters.
Weblate first looks for the exact target language code and then falls back to
the base language code.

The added metadata is used only to guide the generated suggestion; the returned
translation still has to preserve the source placeholders and markup. Weblate
also sends a short previous chat exchange to LLM services to demonstrate the
expected JSON response format. The exchange uses bundled translated examples
when available for the source and target language pair, or language-neutral
formatting examples otherwise. Existing translations for the same target
language can be appended as additional examples.


.. include:: /snippets/machines-autogenerated.rst

.. _custom-machinery:

Custom machine translation
--------------------------

You can also implement your own machine translation services using a few lines
of Python code. Place the code in a module Weblate can import (see
:ref:`custom-module` or :ref:`docker-python-override`) and add fully qualified
class name to :setting:`WEBLATE_MACHINERY`.

.. _machinery-rate-limit-window:

The ``rate_limit_window`` service class attribute controls the cooldown after
Weblate detects rate limiting or certain service failures. Its default is
1800 seconds. When a service returns a retry delay, Weblate uses it instead:
``retry-after-ms`` takes precedence over ``Retry-After`` (seconds or an HTTP
date), followed by Google ``RetryInfo`` details. Invalid delays are ignored.
Valid delays can be shorter or longer than the service default.

Services with documented short-term throttling can override the default;
for example, add ``rate_limit_window = 60`` to your service class to retry after
one minute. Translation and rephrasing use the same window with separate
cooldown state.

Built-in services use a 60-second cooldown for Alibaba, Amazon Translate,
Anthropic, Baidu, Google Cloud Translation Basic and Advanced, LibreTranslate,
Mistral, OpenAI, and Azure OpenAI. Other services retain the default.

Cooldown expiry permits another request; it does not guarantee that a daily
or billing quota has reset. The window also applies to custom endpoints
configured for a service. Existing cached cooldowns expire at their original
time.

.. literalinclude:: ../../weblate/examples/mt_service.py
    :language: python

.. seealso::

   * :ref:`custom-modules`
   * :ref:`custom-module`
   * :ref:`docker-python-override`
