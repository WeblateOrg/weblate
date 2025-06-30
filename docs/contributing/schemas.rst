Data schemas
============

Weblate uses `JSON Schema <https://json-schema.org/>`_ to define layout of external JSON files.

.. only:: not gettext

   .. _schema-memory:

   .. jsonschema:: ../specs/schemas/weblate-memory.schema.json

.. seealso::

    :ref:`translation-memory`,
    :wladmin:`dump_memory`,
    :wladmin:`import_memory`


.. only:: not gettext

   .. _schema-userdata:

   .. jsonschema:: ../specs/schemas/weblate-userdata.schema.json

.. seealso::

    :ref:`user-profile`,
    :wladmin:`dumpuserdata`



.. only:: not gettext

   .. _schema-messaging:

   .. jsonschema:: ../specs/schemas/weblate-messaging.schema.json

.. seealso::

    :ref:`fedora-messaging`,
    :ref:`addon-weblate.webhook.webhook`
