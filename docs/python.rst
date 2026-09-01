.. index::
    single: Python
    single: API

.. _python:

Weblate's Python API
~~~~~~~~~~~~~~~~~~~~

Installation
============

The Python API is shipped separately as the :pypi:`Weblate Client <wlc>`
package:

.. code-block:: sh

    pip install wlc


:mod:`wlc`
==========

.. module:: wlc
    :synopsis: Weblate API

The :mod:`wlc` module exposes the Weblate API client, API objects returned by
the client, and exceptions raised for common API failures.


:class:`Weblate`
----------------

The :class:`Weblate` class is the main API entry point. Constructing it directly
does not load Weblate Client configuration files or ``WLC_*`` environment
variables; its connection settings come from the supplied arguments:

.. code-block:: python

   from wlc import Weblate

   client = Weblate(
       url="https://hosted.weblate.org/api/",
       key="APIKEY",
   )
   projects = list(client.list_projects())

To use configuration-file and environment discovery, explicitly load
:class:`~wlc.config.WeblateConfig` and pass it to the client:

.. code-block:: python

   from wlc import Weblate
   from wlc.config import WeblateConfig

   config = WeblateConfig()
   config.load()
   client = Weblate(config=config)

The Python client follows the same URL, credential, and transport policy as the
command-line client, see :ref:`wlc-security`. Direct API consumers remain
responsible for safely rendering and storing returned values.

.. autoclass:: Weblate
   :members: get, post, request, raw_request, invoke_request, get_object, get_project, get_component, get_translation, get_unit, list_projects, list_components, list_changes, list_units, list_translations, list_languages, list_categories, add_source_string, create_project, create_component, create_language


Exceptions
----------

.. autoexception:: WeblateException

.. autoexception:: WeblatePermissionError

.. autoexception:: WeblateDeniedError

.. autoexception:: WeblateThrottlingError


API objects
-----------

API objects support attribute and keyed access to their fields, together with
``keys()`` and ``items()``. Accessing a known field that is not loaded yet
fetches the object from the API. ``get_data()`` returns a copy of only the data
currently loaded without fetching missing fields.

Projects, components, and translations share repository operations:
``repository()``, ``commit()``, ``push()``, ``pull()``, ``reset()``, and
``cleanup()``.

.. autoclass:: Project
   :members: get_data, list, statistics, languages, changes, categories, delete, create_component, full_slug, repository, commit, push, pull, reset, cleanup

.. autoclass:: Component
   :members: get_data, full_slug, list, add_translation, statistics, lock, unlock, lock_status, changes, delete, add_source_string, download, patch, repository, commit, push, pull, reset, cleanup

.. autoclass:: Translation
   :members: get_data, list, statistics, changes, download, upload, delete, units, repository, commit, push, pull, reset, cleanup

.. autoclass:: Unit
   :members: get_data, list, patch, put, delete

.. autoclass:: Category
   :members: get_data, full_slug

.. autoclass:: Language
   :members: get_data

.. autoclass:: Change
   :members: get_data

.. autoclass:: Statistics
   :members: get_data, refresh, keys

.. autoclass:: LanguageStats
   :members: get_data, refresh, keys

.. autoclass:: TranslationStatistics
   :members: get_data, refresh, keys

.. autoclass:: ProjectRepository
   :members: get_data, commit, push, pull, reset, cleanup

.. autoclass:: Repository
   :members: get_data, commit, push, pull, reset, cleanup


:mod:`wlc.config`
=================

.. module:: wlc.config
    :synopsis: Configuration parsing

.. autoexception:: WLCConfigurationError

.. autoclass:: WeblateConfig
   :members: find_config, find_project_config, load, validate_url_key, get_url_key, get_request_options, get_allow_insecure_http, get_allow_insecure_ssl
